"""Offline OpenSSL CMS transport fixtures; no PRP server, SSH, or production key.

A successful AES-GCM roundtrip demonstrates ciphertext integrity, NOT sender
authentication or independent proof that ChatGPT obtained user approval.
"""
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import RejectedRequest
from security_contract import encode_result, parse_result


def _run(args, input_data=None):
    return subprocess.run(args, input=input_data, capture_output=True,
                          timeout=20, check=False)


class OfflineCmsFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.key = self.path / "answer.key"
        self.cert = self.path / "answer.crt"
        self.other_key = self.path / "unrelated.key"
        self.other_cert = self.path / "unrelated.crt"
        for key, cert, name in ((self.key, self.cert, "fixture-A"),
                                (self.other_key, self.other_cert, "fixture-B")):
            result = _run([
                "openssl", "req", "-new", "-x509", "-nodes",
                "-newkey", "rsa:3072", "-days", "1",
                "-subj", "/CN=PRP-readonly-V2-" + name,
                "-keyout", str(key), "-out", str(cert),
            ])
            if result.returncode:
                self.fail("Could not generate disposable CMS test identity")
            key.chmod(0o600)

    def encrypt(self, payload):
        result = _run([
            "openssl", "cms", "-encrypt", "-binary", "-aes-256-gcm",
            "-outform", "DER", str(self.cert),
        ], payload)
        self.assertEqual(result.returncode, 0, "fixture encryption failed")
        self.assertNotEqual(result.stdout, payload)
        return result.stdout

    def decrypt(self, blob, key=None, cert=None):
        return _run([
            "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
            "-inkey", str(key or self.key), "-recip", str(cert or self.cert),
        ], blob)

    def test_encrypted_result_roundtrip_with_job_and_operation_binding(self):
        job = str(uuid.uuid4())
        plaintext = encode_result(job, "prp_app_health", 1795320000,
                                  data={"liveness": "reachable",
                                        "readiness": "unknown"})
        ciphertext = self.encrypt(plaintext)
        self.assertNotIn(b"reachable", ciphertext)
        result = self.decrypt(ciphertext)
        self.assertEqual(result.returncode, 0, "fixture decryption failed")
        self.assertEqual(parse_result(result.stdout, job, "prp_app_health")["data"],
                         {"liveness": "reachable", "readiness": "unknown"})
        with self.assertRaises(RejectedRequest):
            parse_result(result.stdout, str(uuid.uuid4()), "prp_app_health")
        with self.assertRaises(RejectedRequest):
            parse_result(result.stdout, job, "host_root_fs_usage")

    def test_bit_flip_rejected_by_authenticated_cms(self):
        job = str(uuid.uuid4())
        ciphertext = bytearray(self.encrypt(encode_result(
            job, "prp_app_health", 1795320000,
            error_code="PROBE_UNAVAILABLE",
        )))
        ciphertext[-8] ^= 0x40
        self.assertNotEqual(self.decrypt(bytes(ciphertext)).returncode, 0)

    def test_wrong_recipient_cannot_decrypt(self):
        job = str(uuid.uuid4())
        ciphertext = self.encrypt(encode_result(
            job, "prp_app_health", 1795320000,
            error_code="PROBE_UNAVAILABLE",
        ))
        self.assertNotEqual(
            self.decrypt(ciphertext, self.other_key, self.other_cert).returncode,
            0,
        )


if __name__ == "__main__":
    unittest.main()
