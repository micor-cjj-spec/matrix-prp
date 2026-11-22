"""Synthetic offline-only negative and projection tests for V2."""
import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import (RejectedRequest, parse_decrypted_request,
                          root_filesystem_usage, project_health_liveness)


class ReadonlyV2Tests(unittest.TestCase):
    def setUp(self):
        self.now = 1795320000
        self.job = str(uuid.uuid4())
        self.body = {
            "version": 2, "jobId": self.job, "target": "prp-readonly",
            "actor": "micor-cjj-spec", "operation": "host_root_fs_usage",
            "parameters": {}, "issuedAt": self.now, "expiresAt": self.now + 180,
            "nonce": "a" * 32,
            "answerCertificate": "-----BEGIN CERTIFICATE-----\n" +
                                 "A" * 64 + "\n-----END CERTIFICATE-----\n",
        }

    def validate(self, body=None, now=None):
        raw = json.dumps(self.body if body is None else body, ensure_ascii=False).encode()
        return parse_decrypted_request(raw, self.job, self.now if now is None else now)

    def test_valid_fixed_disk_request(self):
        self.assertEqual(self.validate()["operation"], "host_root_fs_usage")

    def test_valid_fixed_health_request(self):
        self.body["operation"] = "prp_app_health"
        self.assertEqual(self.validate()["operation"], "prp_app_health")

    def test_reject_arbitrary_shell(self):
        self.body["operation"] = "bash"
        with self.assertRaises(RejectedRequest):
            self.validate()

    def test_reject_dynamic_parameters(self):
        for value in ({"path": "/etc/shadow"}, {"url": "https://example.com"},
                      {"sql": "SELECT 1"}, {"command": "id"}, None, [], "x"):
            with self.subTest(value=value), self.assertRaises(RejectedRequest):
                self.validate(dict(self.body, parameters=value))

    def test_reject_extra_command_field(self):
        with self.assertRaises(RejectedRequest):
            self.validate(dict(self.body, command="id"))

    def test_reject_wrong_actor_and_target(self):
        for key, value in (("actor", "attacker"), ("target", "prp-production")):
            with self.subTest(key=key), self.assertRaises(RejectedRequest):
                self.validate(dict(self.body, **{key: value}))

    def test_reject_uuid_mismatch(self):
        with self.assertRaises(RejectedRequest):
            self.validate(dict(self.body, jobId=str(uuid.uuid4())))

    def test_reject_noncanonical_uuid(self):
        self.job = self.job.upper()
        self.body["jobId"] = self.job
        with self.assertRaises(RejectedRequest):
            self.validate()

    def test_reject_nonce(self):
        for nonce in ("A" * 32, "zz" * 16, "a" * 33, 13):
            with self.subTest(nonce=nonce), self.assertRaises(RejectedRequest):
                self.validate(dict(self.body, nonce=nonce))

    def test_reject_ttl_and_expiry(self):
        for issued, expires in (
            (self.now, self.now + 181), (self.now - 200, self.now - 20),
            (self.now + 16, self.now + 100), (self.now, self.now),
            (self.now, self.now - 1), (True, self.now + 10)):
            with self.subTest(issued=issued, expires=expires), self.assertRaises(RejectedRequest):
                self.validate(dict(self.body, issuedAt=issued, expiresAt=expires))

    def test_reject_boolean_version(self):
        with self.assertRaises(RejectedRequest):
            self.validate(dict(self.body, version=True))

    def test_reject_invalid_certificate_shape(self):
        with self.assertRaises(RejectedRequest):
            self.validate(dict(self.body, answerCertificate="FAKE"))

    def test_reject_duplicate_json_keys(self):
        with self.assertRaises(RejectedRequest):
            parse_decrypted_request(b'{"version":2,"version":2}', self.job, self.now)

    def test_reject_nan_and_invalid_utf8(self):
        for raw in (b'{"version":NaN}', b'\xff', b'[]', b''):
            with self.subTest(raw=raw), self.assertRaises(RejectedRequest):
                parse_decrypted_request(raw, self.job, self.now)

    def test_reject_oversized_payload(self):
        with self.assertRaises(RejectedRequest):
            parse_decrypted_request(b"x" * 8193, self.job, self.now)

    def test_root_disk_fixed_path_and_bounded_fields(self):
        seen = []
        fake = SimpleNamespace(f_frsize=1024, f_blocks=100, f_bfree=30, f_bavail=20)
        out = root_filesystem_usage(lambda path: (seen.append(path), fake)[1])
        self.assertEqual(seen, ["/"])
        self.assertEqual(out, {
            "totalBytes": 102400, "usedBytes": 71680,
            "freeBytes": 20480, "usagePercent": 70.0,
        })

    def test_root_disk_invalid_counters_fail_closed(self):
        fake = SimpleNamespace(f_frsize=0, f_blocks=10, f_bfree=20, f_bavail=100)
        with self.assertRaises(RejectedRequest):
            root_filesystem_usage(lambda _: fake)

    def test_health_liveness_minimized_and_no_sensitive_echo(self):
        raw = json.dumps({"code": "SUCCESS", "data": {"status": "UP", "service": "matrix-prp-backend",
                                   "knowledgeRoot": "/internal/secret",
                                   "activeProfiles": ["production"]}}).encode()
        result = project_health_liveness(200, raw)
        self.assertEqual(result, {"liveness": "reachable", "readiness": "unknown"})
        self.assertNotIn("knowledgeRoot", str(result))
        self.assertNotIn("production", str(result))

    def test_health_http200_not_sufficient(self):
        for raw in (b"{}", b'{"code":"SUCCESS","data":{"status":"DOWN"}}',
                    b'{"code":"SUCCESS","data":{"status":"UP","service":"other"}}',
                    b'{"code":"ERROR","data":{"status":"UP","service":"matrix-prp-backend"}}',
                    b'{"data":{"status":"UP","service":"matrix-prp-backend"}}',
                    b"invalid json", b"\\xff"):
            with self.subTest(raw=raw):
                self.assertEqual(project_health_liveness(200, raw)["liveness"], "unknown")

    def test_health_error_no_body_disclosure(self):
        self.assertEqual(project_health_liveness(503, b"secret internal error"),
                         {"liveness": "unreachable", "readiness": "unknown"})
        self.assertEqual(project_health_liveness(200, b"x" * 2049)["liveness"], "unknown")


if __name__ == "__main__":
    unittest.main()
