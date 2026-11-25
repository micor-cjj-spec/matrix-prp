"""Offline OpenSSL CMS transport fixtures; no PRP server, SSH, or production key.

A successful AES-GCM roundtrip demonstrates ciphertext integrity, NOT sender
authentication or independent proof that ChatGPT obtained user approval.
"""
import subprocess
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import RejectedRequest
from security_contract import encode_result, parse_result, verify_consent_fixture


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


class OfflineConsentSignatureTests(unittest.TestCase):
    """Real Ed25519 signature roundtrip, only disposable local identities."""

    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.folder = Path(temp.name)
        cls.signer = cls.folder / "consent.key"
        cls.public = cls.folder / "consent.pub"
        cls.other = cls.folder / "other.key"
        cls.other_public = cls.folder / "other.pub"
        for key, public in ((cls.signer, cls.public), (cls.other, cls.other_public)):
            if _run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)]).returncode:
                raise RuntimeError("fixture key generation failed")
            key.chmod(0o600)
            if _run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(public)]).returncode:
                raise RuntimeError("fixture public key export failed")
        cert = cls.folder / "recipient.pem"
        key = cls.folder / "recipient.key"
        if _run(["openssl", "req", "-new", "-x509", "-nodes", "-newkey", "rsa:2048",
                 "-days", "1", "-subj", "/CN=synthetic-recipient",
                 "-keyout", str(key), "-out", str(cert)]).returncode:
            raise RuntimeError("fixture recipient generation failed")
        key.chmod(0o600)
        cls.pem = cert.read_text()
        converted = _run(["openssl", "x509", "-in", str(cert), "-outform", "DER"])
        if converted.returncode:
            raise RuntimeError("fixture recipient conversion failed")
        cls.der = converted.stdout

    def setUp(self):
        self.now = 1795320000
        self.job = str(uuid.uuid4())
        self.instance = str(uuid.uuid4())
        self.generation = str(uuid.uuid4())
        self.request = {
            "version": 2, "target": "prp-readonly", "actor": "micor-cjj-spec",
            "jobId": self.job, "operation": "host_root_fs_usage", "parameters": {},
            "nonce": "a" * 32, "issuedAt": self.now, "expiresAt": self.now + 120,
            "answerCertificate": self.pem,
        }
        self.claim = {
            "version": 1, "purpose": "prp-readonly-v2-consent",
            "issuer": "synthetic-issuer", "keyId": "synthetic-ed25519-v1",
            "subject": "synthetic-user", "audience": self.instance,
            "generation": self.generation, "repoId": 1261866723,
            "issueNumber": 9002, "challengeCommentId": 5555,
            "jobId": self.job, "operation": "host_root_fs_usage", "parameters": {},
            "nonce": "a" * 32, "issuedAt": self.now, "expiresAt": self.now + 120,
            "answerCertificateFingerprint": hashlib.sha256(self.der).hexdigest(),
        }
        self.context = dict(
            raw_request=json.dumps(self.request).encode(), public_job_id=self.job,
            issuer="synthetic-issuer", key_id="synthetic-ed25519-v1",
            subject="synthetic-user", target_instance=self.instance,
            generation=self.generation, issue_number=9002,
            challenge_comment_id=5555, verified_answer_der=self.der,
            verify_signature=self.verify, now=self.now,
        )

    def canonical(self, claim=None):
        return json.dumps(self.claim if claim is None else claim,
                          sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii")

    def sign(self, data, key=None):
        with tempfile.TemporaryDirectory() as directory:
            message = Path(directory) / "message"
            message.write_bytes(data)
            result = _run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey",
                           str(key or self.signer), "-in", str(message)])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout), 64)
        return result.stdout

    def verify(self, data, signature):
        # The trusted test provider selects the public key, not the claim.
        with tempfile.TemporaryDirectory() as directory:
            message = Path(directory) / "message"
            sig = Path(directory) / "signature"
            message.write_bytes(data)
            sig.write_bytes(signature)
            result = _run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin",
                           "-inkey", str(self.public), "-in", str(message),
                           "-sigfile", str(sig)])
        return result.returncode == 0

    def test_valid_signature_and_exact_context(self):
        raw = self.canonical()
        self.assertEqual(verify_consent_fixture(raw, self.sign(raw), **self.context),
                         hashlib.sha256(raw).hexdigest())

    def test_wrong_key_and_tampered_signature_rejected(self):
        raw = self.canonical()
        bad = bytearray(self.sign(raw))
        bad[0] ^= 1
        for sig in (self.sign(raw, self.other), bytes(bad), b""):
            with self.subTest(length=len(sig)), self.assertRaises(RejectedRequest):
                verify_consent_fixture(raw, sig, **self.context)

    def test_valid_signature_on_wrong_context_is_rejected(self):
        changes = {
            "purpose": "prp-readonly-v2-result", "issuer": "other", "keyId": "other",
            "subject": "other", "audience": str(uuid.uuid4()), "generation": str(uuid.uuid4()),
            "repoId": 1, "issueNumber": 9003, "challengeCommentId": 5556,
            "jobId": str(uuid.uuid4()), "operation": "prp_app_health",
            "parameters": {"path": "/"}, "nonce": "b" * 32,
            "issuedAt": self.now - 1, "expiresAt": self.now + 121,
            "answerCertificateFingerprint": "0" * 64, "version": True,
        }
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(RejectedRequest):
                raw = self.canonical(dict(self.claim, **{field: value}))
                verify_consent_fixture(raw, self.sign(raw), **self.context)

    def test_signed_noncanonical_duplicate_and_algorithm_fields_rejected(self):
        raw = self.canonical()
        variants = (
            raw + b" ",
            b'{"version":1,' + raw[1:],
            self.canonical(dict(self.claim, algorithm="none")),
        )
        for item in variants:
            with self.subTest(length=len(item)), self.assertRaises(RejectedRequest):
                verify_consent_fixture(item, self.sign(item), **self.context)

    def test_wrong_epoch_and_challenge_context_rejected(self):
        raw = self.canonical()
        sig = self.sign(raw)
        for changes in ({"generation": str(uuid.uuid4())},
                        {"challenge_comment_id": 5556},
                        {"issue_number": True}, {"target_instance": str(uuid.uuid4())}):
            with self.subTest(changes=changes), self.assertRaises(RejectedRequest):
                verify_consent_fixture(raw, sig, **dict(self.context, **changes))

    def test_expired_and_future_request_rejected(self):
        raw = self.canonical()
        sig = self.sign(raw)
        for instant in (self.request["expiresAt"], self.now - 1):
            with self.subTest(instant=instant), self.assertRaises(RejectedRequest):
                verify_consent_fixture(raw, sig, **dict(self.context, now=instant))

    def test_request_and_validated_certificate_must_match(self):
        raw = self.canonical()
        sig = self.sign(raw)
        wrong_request = dict(self.request, operation="prp_app_health")
        for changes in (
            {"verified_answer_der": b"other-certificate"},
            {"raw_request": json.dumps(wrong_request).encode()},
            {"public_job_id": str(uuid.uuid4())},
        ):
            with self.subTest(fields=list(changes)), self.assertRaises(RejectedRequest):
                verify_consent_fixture(raw, sig, **dict(self.context, **changes))

    def test_missing_or_faulting_verifier_fails_closed(self):
        raw = self.canonical()
        sig = self.sign(raw)
        def fault(*args):
            raise RuntimeError("synthetic provider unavailable")
        for verifier in (None, fault, lambda *args: 1, lambda *args: False):
            with self.subTest(verifier=verifier), self.assertRaisesRegex(
                    RejectedRequest, "^authorization rejected$"):
                verify_consent_fixture(raw, sig, **dict(self.context, verify_signature=verifier))


if __name__ == "__main__":
    unittest.main()
