"""Offline OpenSSL CMS transport fixtures; no PRP server, SSH, or production key.

A successful AES-GCM roundtrip demonstrates ciphertext integrity, NOT sender
authentication or independent proof that ChatGPT obtained user approval.
"""
import subprocess
import hashlib
import base64
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import RejectedRequest, root_filesystem_usage
from security_contract import (encode_result, parse_result, verify_consent_fixture,
                               result_binding_fixture, verify_signed_result_fixture,
                               ReplayLedger, ReceiptLedger, claim_bound_execution_fixture,
                               consume_signed_result_fixture)


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
        cls.server_signer = cls.folder / "server-sign.key"
        cls.server_public = cls.folder / "server-sign.pub"
        for key, public in ((cls.signer, cls.public), (cls.other, cls.other_public),
                            (cls.server_signer, cls.server_public)):
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
        cls.recipient_cert = cert
        cls.recipient_key = key
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

    def verify(self, data, signature, public=None):
        # The trusted test provider selects the public key, not the claim.
        with tempfile.TemporaryDirectory() as directory:
            message = Path(directory) / "message"
            sig = Path(directory) / "signature"
            message.write_bytes(data)
            sig.write_bytes(signature)
            result = _run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin",
                           "-inkey", str(public or self.public), "-in", str(message),
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



    def response_context(self):
        raw = self.canonical()
        digest = verify_consent_fixture(raw, self.sign(raw), **self.context)
        return dict(consent_digest=digest, job_id=self.job,
                    operation=self.request["operation"], nonce=self.request["nonce"],
                    target_instance=self.instance, generation=self.generation,
                    issue_number=9002, challenge_comment_id=5555,
                    execution_comment_id=5556, server_key_id="synthetic-server-ed25519",
                    issued_at=self.now, expires_at=self.request["expiresAt"],
                    now=self.now + 1)

    def verify_server(self, data, signature):
        return self.verify(data, signature, self.server_public)

    def synthetic_result(self):
        return encode_result(self.job, self.request["operation"], self.now,
                             data={"totalBytes": 1000, "usedBytes": 600,
                                   "freeBytes": 300, "usagePercent": 60.0})

    def test_valid_signed_response_from_separate_server_key(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        signature = self.sign(binding, self.server_signer)
        self.assertEqual(verify_signed_result_fixture(
            raw, binding, signature, verify_signature=self.verify_server,
            **context)["data"]["usedBytes"], 600)

    def test_response_wrong_key_and_tampering_rejected(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        signature = self.sign(binding, self.server_signer)
        changed = encode_result(self.job, self.request["operation"], self.now,
                                data={"totalBytes": 1000, "usedBytes": 200,
                                      "freeBytes": 300, "usagePercent": 20.0})
        for data, metadata, sig in (
            (raw, binding, self.sign(binding)),  # consent key != server key
            (raw, binding, self.sign(binding, self.other)),
            (changed, binding, signature),
            (raw, binding + b" ", signature),
            (raw, binding, signature[:-1]),
        ):
            with self.subTest(data=data, metadata=metadata, size=len(sig)), self.assertRaises(RejectedRequest):
                verify_signed_result_fixture(data, metadata, sig,
                                             verify_signature=self.verify_server, **context)

    def test_signed_response_context_substitution_rejected(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        signature = self.sign(binding, self.server_signer)
        changes = {"consent_digest": "0" * 64, "nonce": "b" * 32,
                   "job_id": str(uuid.uuid4()), "operation": "prp_app_health",
                   "generation": str(uuid.uuid4()), "target_instance": str(uuid.uuid4()),
                   "issue_number": 9003, "challenge_comment_id": 5554,
                   "execution_comment_id": 5557, "server_key_id": "other",
                   "expires_at": self.now + 121}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(RejectedRequest):
                verify_signed_result_fixture(raw, binding, signature,
                    verify_signature=self.verify_server, **dict(context, **{field: value}))

    def test_signed_noncanonical_response_metadata_rejected(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        for altered in (binding + b" ", b'{"version":1,' + binding[1:],
                        binding[:-1] + b',"algorithm":"none"}'):
            with self.subTest(altered=altered), self.assertRaises(RejectedRequest):
                verify_signed_result_fixture(raw, altered, self.sign(altered, self.server_signer),
                                             verify_signature=self.verify_server, **context)

    def test_response_observation_and_expiry_bounds(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        sig = self.sign(binding, self.server_signer)
        for now in (self.now - 1, self.request["expiresAt"]):
            with self.subTest(now=now), self.assertRaises(RejectedRequest):
                verify_signed_result_fixture(raw, binding, sig,
                    verify_signature=self.verify_server, **dict(context, now=now))
        for observed in (self.now - 1, self.now + 2):
            future = encode_result(self.job, self.request["operation"], observed,
                                   error_code="METRIC_UNAVAILABLE")
            with self.subTest(observed=observed), self.assertRaises(RejectedRequest):
                result_binding_fixture(future, **context)

    def test_response_error_is_signed_and_schema_validated(self):
        context = self.response_context()
        raw = encode_result(self.job, self.request["operation"], self.now,
                            error_code="METRIC_UNAVAILABLE")
        binding = result_binding_fixture(raw, **context)
        value = verify_signed_result_fixture(raw, binding, self.sign(binding, self.server_signer),
                                             verify_signature=self.verify_server, **context)
        self.assertFalse(value["ok"])
        self.assertEqual(value["data"], {})
        with self.assertRaises(RejectedRequest):
            result_binding_fixture(raw, **dict(context, execution_comment_id=5555))

    def test_response_faulting_provider_fails_closed(self):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        signature = self.sign(binding, self.server_signer)
        def fault(*args):
            raise RuntimeError("fixture verifier failure")
        for provider in (None, fault, lambda *args: 1, lambda *args: False):
            with self.subTest(provider=provider), self.assertRaisesRegex(
                    RejectedRequest, "^response rejected$"):
                verify_signed_result_fixture(raw, binding, signature,
                                             verify_signature=provider, **context)

    def test_signed_consent_claim_synthetic_projection_signed_encrypted_response(self):
        # The adapter's event and certificate validation are simulated;
        # OpenSSL signatures and encryption and SQLite claim are real.
        context = self.response_context()  # actual consent signature checked
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger.initialize(Path(directory) / "claims.sqlite", self.generation)
            self.assertTrue(ledger.claim(self.job, self.request["nonce"],
                                         self.request["expiresAt"], self.now))
            with self.assertRaises(RejectedRequest):
                ledger.claim(self.job, self.request["nonce"], self.request["expiresAt"], self.now)
            seen = []
            stat = SimpleNamespace(f_frsize=1024, f_blocks=100, f_bfree=40, f_bavail=25)
            data = root_filesystem_usage(lambda path: (seen.append(path), stat)[1])
            self.assertEqual(seen, ["/"])  # synthetic counters, no real disk access
            raw = encode_result(self.job, self.request["operation"], self.now, data=data)
            binding = result_binding_fixture(raw, **context)
            sig = self.sign(binding, self.server_signer)
            # Fixture-only framing; not a production envelope or transport parser.
            envelope = json.dumps([base64.b64encode(x).decode("ascii")
                                   for x in (raw, binding, sig)]).encode("ascii")
            cipher = _run(["openssl", "cms", "-encrypt", "-binary", "-aes-256-gcm",
                           "-outform", "DER", str(self.recipient_cert)], envelope)
            self.assertEqual(cipher.returncode, 0)
            self.assertNotIn(b"usagePercent", cipher.stdout)
            received = _run(["openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                             "-inkey", str(self.recipient_key), "-recip",
                             str(self.recipient_cert)], cipher.stdout)
            self.assertEqual(received.returncode, 0)
            response, metadata, signature = [base64.b64decode(x, validate=True)
                                             for x in json.loads(received.stdout)]
            value = verify_signed_result_fixture(response, metadata, signature,
                                                 verify_signature=self.verify_server, **context)
            self.assertEqual(value["data"]["usedBytes"], 61440)
            self.assertEqual(value["data"]["freeBytes"], 25600)



    def bound_execution_args(self, ledger):
        raw_claim = self.canonical()
        raw_request = self.context["raw_request"]
        token = base64.urlsafe_b64encode(b"synthetic ciphertext").decode().rstrip("=")
        owner = {"login": "micor-cjj-spec", "type": "User", "id": 123868412}
        event = {"action": "created", "repository": {"full_name": "micor-cjj-spec/matrix-prp",
                 "id": 1261866723}, "issue": {"number": 9002}, "sender": owner,
                 "comment": {"id": 5556, "user": owner,
                             "body": f"/prp-readonly-v2 {self.job} {token}"}}
        runtime = {"event_name": "issue_comment", "ref": "refs/heads/main",
                   "repository": "micor-cjj-spec/matrix-prp", "repository_id": 1261866723,
                   "actor": "micor-cjj-spec", "actor_id": 123868412}
        mapping = {"purpose": "prp-readonly-v2-execution-mapping",
                   "repoId": 1261866723, "issueNumber": 9002, "actorId": 123868412,
                   "jobId": self.job, "nonce": self.request["nonce"],
                   "consentDigest": hashlib.sha256(raw_claim).hexdigest(),
                   "challengeCommentId": 5555, "executionCommentId": 5556,
                   "audience": self.instance, "generation": self.generation,
                   "ciphertextDigest": hashlib.sha256(token.encode("ascii")).hexdigest(),
                   "requestDigest": hashlib.sha256(raw_request).hexdigest()}
        context = {k: v for k, v in self.context.items()
                   if k not in ("raw_request", "public_job_id")}
        return dict(event=event, trusted_runtime=runtime, raw_request=raw_request,
                    raw_claim=raw_claim, signature=self.sign(raw_claim),
                    trusted_mapping=self.canonical(mapping), consent_context=context,
                    active_check=lambda scope: True, ledger=ledger)

    def test_bound_execution_valid_and_replayed_event_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger.initialize(Path(directory) / "claims.sqlite", self.generation)
            args = self.bound_execution_args(ledger)
            digest = claim_bound_execution_fixture(**args)
            self.assertEqual(digest, hashlib.sha256(self.canonical()).hexdigest())
            with self.assertRaises(RejectedRequest):
                claim_bound_execution_fixture(**args)

    def test_execution_mapping_mismatch_and_edited_event_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger.initialize(Path(directory) / "claims.sqlite", self.generation)
            args = self.bound_execution_args(ledger)
            for change in ({"trusted_mapping": args["trusted_mapping"] + b" "},
                           {"event": dict(args["event"], action="edited")},
                           {"raw_request": args["raw_request"] + b" "},
                           {"event": dict(args["event"], comment=dict(args["event"]["comment"], id=5557))}):
                with self.subTest(fields=list(change)), self.assertRaises(RejectedRequest):
                    claim_bound_execution_fixture(**dict(args, **change))
            # Rejected requests did not consume the valid grant.
            self.assertEqual(claim_bound_execution_fixture(**args),
                             hashlib.sha256(self.canonical()).hexdigest())

    def test_revocation_before_claim_denies_without_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger.initialize(Path(directory) / "claims.sqlite", self.generation)
            args = self.bound_execution_args(ledger)
            for provider in (None, lambda _: False, lambda _: 1):
                with self.subTest(provider=provider), self.assertRaises(RejectedRequest):
                    claim_bound_execution_fixture(**dict(args, active_check=provider))
            self.assertEqual(claim_bound_execution_fixture(**args),
                             hashlib.sha256(self.canonical()).hexdigest())

    def test_revocation_after_claim_burns_execution_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger.initialize(Path(directory) / "claims.sqlite", self.generation)
            args = self.bound_execution_args(ledger)
            decisions = iter((True, False))
            with self.assertRaises(RejectedRequest):
                claim_bound_execution_fixture(**dict(args, active_check=lambda _: next(decisions)))
            with self.assertRaises(RejectedRequest):
                claim_bound_execution_fixture(**args)

    def receipt_args(self, ledger):
        context = self.response_context()
        raw = self.synthetic_result()
        binding = result_binding_fixture(raw, **context)
        return dict(raw_result=raw, raw_binding=binding,
                    signature=self.sign(binding, self.server_signer),
                    receipt_ledger=ledger, active_check=lambda _: True,
                    verify_signature=self.verify_server, response_context=context)

    def test_response_receipt_is_one_time_and_separate_from_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            execution = ReplayLedger.initialize(folder / "execution.sqlite", self.generation)
            claim_bound_execution_fixture(**self.bound_execution_args(execution))
            receipt = ReceiptLedger.initialize(folder / "receipt.sqlite", self.generation)
            args = self.receipt_args(receipt)
            self.assertEqual(consume_signed_result_fixture(**args)["data"]["usedBytes"], 600)
            reopened = ReceiptLedger(folder / "receipt.sqlite", self.generation)
            with self.assertRaises(RejectedRequest):
                consume_signed_result_fixture(**dict(args, receipt_ledger=reopened))

    def test_receipt_rejects_execution_ledger_and_wrong_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            execution = ReplayLedger.initialize(folder / "execution.sqlite", self.generation)
            receipt = ReceiptLedger.initialize(folder / "receipt.sqlite", str(uuid.uuid4()))
            args = self.receipt_args(receipt)
            for wrong in (execution, ReceiptLedger(folder / "execution.sqlite", self.generation), receipt):
                with self.subTest(wrong=wrong), self.assertRaises(RejectedRequest):
                    consume_signed_result_fixture(**dict(args, receipt_ledger=wrong))

    def test_receipt_rejected_signature_or_revocation_does_not_consume(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = ReceiptLedger.initialize(Path(directory) / "receipt.sqlite", self.generation)
            args = self.receipt_args(receipt)
            for change in ({"signature": bytes(64)}, {"active_check": lambda _: False}):
                with self.subTest(fields=list(change)), self.assertRaises(RejectedRequest):
                    consume_signed_result_fixture(**dict(args, **change))
            self.assertTrue(consume_signed_result_fixture(**args)["ok"])

    def test_receipt_revocation_after_claim_burns_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = ReceiptLedger.initialize(Path(directory) / "receipt.sqlite", self.generation)
            args = self.receipt_args(receipt)
            decisions = iter((True, False))
            with self.assertRaises(RejectedRequest):
                consume_signed_result_fixture(**dict(args, active_check=lambda _: next(decisions)))
            with self.assertRaises(RejectedRequest):
                consume_signed_result_fixture(**args)


if __name__ == "__main__":
    unittest.main()
