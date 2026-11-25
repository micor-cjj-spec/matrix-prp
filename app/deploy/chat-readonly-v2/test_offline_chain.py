"""Single synthetic V2 request -> claim -> fixed metric -> encrypted reply test.

This test does NOT involve ChatGPT approval, actual GitHub events, network, SSH,
real server disk, production host keys, or protected branches. CMS encryption
protects confidentiality/integrity for a recipient; it does not authenticate
that an end user approved a command in ChatGPT.
"""
import base64
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import (RejectedRequest, parse_decrypted_request,
                          root_filesystem_usage)
from security_contract import (parse_event_fixture, ReplayLedger,
                               encode_result, parse_result)

GENERATION = "12345678-1234-4234-8234-123456789abc"
ISSUE_FIXTURE = 9002
NOW = 1795320000
REPO_NAME = "micor-cjj-spec/matrix-prp"
OWNER = "micor-cjj-spec"


def _run(args, stdin=None):
    return subprocess.run(args, input=stdin, capture_output=True,
                          timeout=20, check=False)


class V2OfflineChainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.server_key = self.folder / "synthetic-recipient.key"
        self.server_cert = self.folder / "synthetic-recipient.crt"
        self.answer_key = self.folder / "synthetic-answer.key"
        self.answer_cert = self.folder / "synthetic-answer.crt"
        for key, cert, cn in (
            (self.server_key, self.server_cert, "offline-v2-recipient"),
            (self.answer_key, self.answer_cert, "offline-v2-answer"),
        ):
            p = _run(["openssl", "req", "-new", "-x509", "-nodes",
                      "-newkey", "rsa:3072", "-days", "1",
                      "-subj", f"/CN={cn}",
                      "-keyout", str(key), "-out", str(cert)])
            if p.returncode != 0:
                self.fail("disposable CMS fixture key generation failed")
            key.chmod(0o600)
        self.job = str(uuid.uuid4())
        self.request = {
            "version": 2,
            "jobId": self.job, "target": "prp-readonly",
            "actor": OWNER, "operation": "host_root_fs_usage",
            "parameters": {}, "issuedAt": NOW, "expiresAt": NOW + 120,
            "nonce": "b" * 32,
            "answerCertificate": self.answer_cert.read_text(),
        }
        self.runtime = {
            "event_name": "issue_comment", "ref": "refs/heads/main",
            "repository": REPO_NAME, "repository_id": 1261866723,
            "actor": OWNER, "actor_id": 123868412,
        }
        owner = {"login": OWNER, "type": "User", "id": 123868412}
        self.event = {
            "action": "created",
            "repository": {"full_name": REPO_NAME, "id": 1261866723},
            "issue": {"number": ISSUE_FIXTURE},
            "sender": dict(owner),
            "comment": {"id": 87654, "user": dict(owner)},
        }

    def _encrypt(self, body, certificate):
        p = _run(["openssl", "cms", "-encrypt", "-binary", "-aes-256-gcm",
                  "-outform", "DER", str(certificate)], stdin=body)
        self.assertEqual(p.returncode, 0, "synthetic CMS encryption failed")
        return p.stdout

    def _decrypt(self, ciphertext, key, certificate):
        return _run(["openssl", "cms", "-decrypt", "-binary",
                     "-inform", "DER", "-inkey", str(key),
                     "-recip", str(certificate)], stdin=ciphertext)

    def _event_with_encrypted_request(self):
        body = json.dumps(self.request, separators=(",", ":")).encode()
        cipher = self._encrypt(body, self.server_cert)
        self.event["comment"]["body"] = (
            f"/prp-readonly-v2 {self.job} " +
            base64.urlsafe_b64encode(cipher).decode().rstrip("=")
        )
        return cipher

    def test_synthetic_request_response_claim_and_replay(self):
        original_cipher = self._event_with_encrypted_request()
        entry = parse_event_fixture(self.event, self.runtime, ISSUE_FIXTURE)
        self.assertEqual(entry["jobId"], self.job)
        parsed_cipher = base64.urlsafe_b64decode(
            entry["ciphertextB64"] + "=" * (-len(entry["ciphertextB64"]) % 4)
        )
        self.assertEqual(parsed_cipher, original_cipher)
        decrypted = self._decrypt(parsed_cipher, self.server_key, self.server_cert)
        self.assertEqual(decrypted.returncode, 0)
        request = parse_decrypted_request(decrypted.stdout, self.job, now=NOW)

        ledger = ReplayLedger.initialize(self.folder / "synthetic-claims.sqlite", GENERATION)
        self.assertTrue(ledger.claim(request["jobId"], request["nonce"],
                                     request["expiresAt"], now=NOW))
        with self.assertRaisesRegex(RejectedRequest, "already claimed"):
            ReplayLedger(self.folder / "synthetic-claims.sqlite", GENERATION).claim(
                request["jobId"], request["nonce"], request["expiresAt"], now=NOW)

        # Fake counters only. The test never queries the CI runner's real disk.
        stat = SimpleNamespace(f_frsize=1024, f_blocks=100,
                               f_bfree=40, f_bavail=25)
        seen = []
        fixed_data = root_filesystem_usage(
            lambda path: (seen.append(path), stat)[1]
        )
        self.assertEqual(seen, ["/"])
        result_plain = encode_result(self.job, request["operation"], NOW,
                                     data=fixed_data)
        result_cipher = self._encrypt(result_plain, self.answer_cert)
        self.assertNotIn(b"usagePercent", result_cipher)
        received = self._decrypt(result_cipher, self.answer_key, self.answer_cert)
        self.assertEqual(received.returncode, 0)
        result = parse_result(received.stdout, self.job, "host_root_fs_usage")
        self.assertEqual(result["data"]["usedBytes"], 61440)
        self.assertEqual(result["data"]["freeBytes"], 25600)

    def test_wrong_request_recipient_and_ciphertext_tampering_rejected(self):
        cipher = self._event_with_encrypted_request()
        self.assertNotEqual(
            self._decrypt(cipher, self.answer_key, self.answer_cert).returncode, 0
        )
        altered = bytearray(cipher)
        altered[-8] ^= 0x40
        self.assertNotEqual(
            self._decrypt(bytes(altered), self.server_key, self.server_cert).returncode,
            0,
        )


if __name__ == "__main__":
    unittest.main()
