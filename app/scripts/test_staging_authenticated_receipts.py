import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import staging_authenticated_receipts as auth
from test_release_evidence import fixture, D
from test_staging_release_evidence_review import projection
from test_staging_runtime_evidence import runtime, NOW
from test_staging_database_evidence import database


class SignedReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="prp-p372-test-")
        cls.root = Path(cls.temp.name)
        cls.keys = {}
        for index, (receipt_type, role) in enumerate(auth.RECEIPT_ROLES.items()):
            key_id = "synthetic-" + str(index)
            private = cls.root / (key_id + ".private.pem")
            public = cls.root / (key_id + ".public.pem")
            subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                            "-out", str(private)], check=True, capture_output=True, timeout=5)
            subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout",
                            "-out", str(public)], check=True, capture_output=True, timeout=5)
            os.chmod(private, 0o600)
            os.chmod(public, 0o600)
            cls.keys[receipt_type] = {
                "key_id": key_id, "private": private,
                "trusted": {"role": role, "environment": auth.ENV,
                            "public_key_pem": public.read_text(encoding="ascii"),
                            "not_before": NOW - 1000, "not_after": NOW + 1000},
            }
        cls.trust_store = {value["key_id"]: value["trusted"] for value in cls.keys.values()}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def signed(self, receipt_type, payload, issued_at=NOW - 5, expires_at=NOW + 300, nonce=None):
        key = self.keys[receipt_type]
        envelope = {
            "schema_version": 1, "receipt_type": receipt_type, "environment": auth.ENV,
            "key_id": key["key_id"], "issued_at": issued_at, "expires_at": expires_at,
            "nonce": nonce or ("nonce-" + receipt_type.replace("_", "-") + "-0001"),
            "payload": payload, "signature": "",
        }
        message = auth._signing_message(envelope)
        message_file = self.root / "message.bin"
        signature_file = self.root / "signature.bin"
        message_file.write_bytes(message)
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key["private"]),
                        "-rawin", "-in", str(message_file), "-out", str(signature_file)],
                       check=True, capture_output=True, timeout=5)
        envelope["signature"] = base64.b64encode(signature_file.read_bytes()).decode("ascii")
        return envelope

    def bundle(self, no_migration=False):
        candidate = fixture()["candidate"]
        p = projection()
        r = runtime()
        r["uat"] = None
        r["before"]["observed_at"] = NOW - 50
        r["after"]["observed_at"] = NOW - 10
        db = database()
        if no_migration:
            db["baseline_schema"] = candidate["schema"]
            db["expected_migrations"] = []
            db["migration"].update(before_schema=candidate["schema"],
                                   before_history=db["baseline_history"],
                                   after_history=db["baseline_history"], applied=[])
            db["backup"]["baseline_schema"] = candidate["schema"]
            db["restore"]["restored_schema"] = candidate["schema"]
            db["restore"]["rehearsal"]["target_schema"] = candidate["schema"]
            db["restore"]["rehearsal"]["applied"] = []
            db["risk"]["classification"] = "NO_RUNTIME_CHANGE"
        context = {key: db[key] for key in (
            "baseline_schema", "baseline_history", "baseline_data_digest",
            "source_instance", "policy_digest", "expected_migrations")}
        context_hash = auth.database_context_digest(candidate, context)
        runtime_payload = {
            "candidate": candidate, "environment": auth.ENV,
            "projection_digest": auth.sha256(auth.canonical_bytes(p)),
            "snapshot": r,
            "rollback_readiness": {"status": "pass", "plan_digest": D},
        }
        runtime_env = self.signed("runtime_observation", runtime_payload,
                                  nonce="nonce-runtime-00000001")
        runtime_hash = auth.envelope_digest(runtime_env)
        migration_payload = {
            "candidate": candidate, "environment": auth.ENV, "context": context,
            "migration_mode": "no_schema_change" if no_migration else "apply_migrations",
            "migration": db["migration"],
        }
        backup_payload = {
            "candidate": candidate, "environment": auth.ENV,
            "context_digest": context_hash, "backup": db["backup"], "restore": db["restore"],
        }
        risk_payload = {
            "candidate": candidate, "environment": auth.ENV,
            "context_digest": context_hash, "risk": db["risk"],
        }
        health_cases = dict.fromkeys(auth.HEALTH_CASES, "pass")
        health_payload = {
            "module": "health_v2", "candidate": candidate, "environment": auth.ENV,
            "started_at": NOW - 30, "finished_at": NOW - 15,
            "runtime_receipt_digest": runtime_hash, "database_context_digest": context_hash,
            "cases": health_cases,
            "evidence_digests": {key: D for key in health_cases},
            "identity": {
                "owner_a_subject_digest": "sha256:" + "a" * 64,
                "owner_b_subject_digest": "sha256:" + "b" * 64,
                "owner_a_enabled": True, "owner_b_enabled": True,
                "owner_a_admin": False, "owner_b_admin": False,
                "owner_a_mcp_grants": 0, "owner_b_mcp_grants": 0,
            },
            "cleanup": {"scope": "owner_created_meals_only", "created_count": 2,
                        "deleted_count": 2, "remaining_count": 0, "unsupported_resource_writes": 0},
            "device_observations": None,
        }
        ui_cases = dict.fromkeys(auth.UI_CASES, "pass")
        ui_payload = {
            "module": "ui_v2", "candidate": candidate, "environment": auth.ENV,
            "started_at": NOW - 25, "finished_at": NOW - 12,
            "runtime_receipt_digest": runtime_hash, "database_context_digest": context_hash,
            "cases": ui_cases,
            "evidence_digests": {key: D for key in ui_cases},
            "identity": {"ordinary_user_subject_digest": "sha256:" + "c" * 64,
                         "ordinary_user_enabled": True, "ordinary_user_admin": False,
                         "mcp_grant_rows": 0},
            "cleanup": None,
            "device_observations": [
                {"device": "desktop", "os_version": "Windows 11", "browser": "Edge",
                 "browser_version": "stable", "viewport": "1280x800", "observed_at": NOW - 18,
                 "evidence_digest": D},
                {"device": "iphone", "os_version": "iOS 26", "browser": "Safari",
                 "browser_version": "stable", "viewport": "390x844", "observed_at": NOW - 13,
                 "evidence_digest": D},
            ],
        }
        return candidate, p, {
            "runtime_observation": runtime_env,
            "database_migration": self.signed("database_migration", migration_payload,
                                               nonce="nonce-migration-000001"),
            "backup_restore": self.signed("backup_restore", backup_payload,
                                          nonce="nonce-backup-restore-0001"),
            "risk_review": self.signed("risk_review", risk_payload,
                                       nonce="nonce-risk-review-000001"),
            "module_uat": {
                "health_v2": self.signed("health_v2_uat", health_payload,
                                         nonce="nonce-health-owner-000001"),
                "ui_v2": self.signed("ui_v2_uat", ui_payload,
                                     nonce="nonce-ui-owner-00000001"),
            },
        }

    def assess(self, bundle=None, no_migration=False):
        candidate, p, receipts = bundle or self.bundle(no_migration=no_migration)
        with patch.dict(auth.TRUSTED_SIGNERS, self.trust_store, clear=True):
            report = auth.assess_receipt_bundle(candidate, p, receipts, NOW)
        return report, candidate, p, receipts

    def resign(self, receipt_type, envelope):
        key = self.keys[receipt_type]
        envelope["signature"] = ""
        message_file = self.root / "message.bin"
        signature_file = self.root / "signature.bin"
        message_file.write_bytes(auth._signing_message(envelope))
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key["private"]),
                        "-rawin", "-in", str(message_file), "-out", str(signature_file)],
                       check=True, capture_output=True, timeout=5)
        envelope["signature"] = base64.b64encode(signature_file.read_bytes()).decode("ascii")

    def test_valid_synthetic_signatures_correlate_but_never_authorize(self):
        report, _, _, _ = self.assess()
        self.assertTrue(all(report["signature_checks"].values()))
        self.assertTrue(report["cryptographic_signatures_valid_against_configured_keys"])
        self.assertTrue(report["runtime_correlation_claimed"])
        self.assertTrue(report["database_correlation_claimed"])
        self.assertEqual(report["module_uat_claimed"], {"health_v2": True, "ui_v2": True})
        self.assertEqual(report["state"], "BLOCKED")
        for key in ("source_authenticated", "trusted_key_provenance_verified",
                    "independent_host_attestation", "trusted_clock", "durable_replay_protection",
                    "business_uat_verified", "migration_verified", "restore_verified", "risk_verified",
                    "current_review_satisfied", "release_eligible", "deployment_authorized",
                    "production_authorized", "live_verified"):
            self.assertIs(report[key], False)

    def test_public_path_has_no_trust_anchor(self):
        candidate, p, receipts = self.bundle()
        report = auth.assess_receipt_bundle(candidate, p, receipts, NOW)
        self.assertEqual(len(auth.TRUSTED_SIGNERS), 0)
        self.assertFalse(report["cryptographic_signatures_valid_against_configured_keys"])
        self.assertIn("TRUST_ANCHOR_NOT_PROVISIONED", report["findings"])
        self.assertFalse(report["source_authenticated"])
        self.assertEqual(report["state"], "BLOCKED")

    def test_payload_tampering_invalidates_signature(self):
        candidate, p, receipts = self.bundle()
        receipts["runtime_observation"]["payload"]["rollback_readiness"]["status"] = "fail"
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["signature_checks"]["runtime_observation"])
        self.assertIn("RUNTIME_OBSERVATION:SIGNATURE_INVALID", report["findings"])

    def test_wrong_role_key_is_rejected_even_with_valid_signature(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        wrong_key = self.keys["database_migration"]
        env["key_id"] = wrong_key["key_id"]
        env["signature"] = ""
        message_file, signature_file = self.root / "message.bin", self.root / "signature.bin"
        message_file.write_bytes(auth._signing_message(env))
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(wrong_key["private"]),
                        "-rawin", "-in", str(message_file), "-out", str(signature_file)],
                       check=True, capture_output=True, timeout=5)
        env["signature"] = base64.b64encode(signature_file.read_bytes()).decode("ascii")
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["signature_checks"]["risk_review"])
        self.assertIn("RISK_REVIEW:SIGNER_ROLE_ENVIRONMENT_OR_VALIDITY_MISMATCH", report["findings"])

    def test_expired_and_future_receipts_block(self):
        for issued, expires in ((NOW - 1000, NOW - 1), (NOW + 1, NOW + 200)):
            candidate, p, receipts = self.bundle()
            env = receipts["risk_review"]
            env["issued_at"], env["expires_at"] = issued, expires
            self.resign("risk_review", env)
            report, _, _, _ = self.assess((candidate, p, receipts))
            self.assertFalse(report["signature_checks"]["risk_review"])
            self.assertTrue(any("RECEIPT_EXPIRED_FUTURE_OR_TTL_INVALID" in x for x in report["findings"]))

    def test_receipt_ttl_is_bounded(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        env["expires_at"] = env["issued_at"] + auth.MAX_RECEIPT_TTL + 1
        self.resign("risk_review", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["signature_checks"]["risk_review"])

    def test_reused_signer_key_across_roles_is_detected(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        wrong_key = self.keys["database_migration"]
        env["key_id"] = wrong_key["key_id"]
        self.resign("risk_review", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("SIGNER_KEY_REUSED_ACROSS_ROLES", report["findings"])

    def test_nonce_replay_within_bundle_is_detected(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        env["nonce"] = receipts["database_migration"]["nonce"]
        self.resign("risk_review", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("RECEIPT_NONCE_REPLAY_WITHIN_BUNDLE", report["findings"])

    def test_no_schema_change_is_explicit_and_still_requires_backup_restore(self):
        report, _, _, _ = self.assess(no_migration=True)
        self.assertTrue(report["database_correlation_claimed"])
        self.assertTrue(report["signature_checks"]["backup_restore"])
        self.assertTrue(report["signature_checks"]["database_migration"])
        self.assertIn("DURABLE_REPLAY_PROTECTION_NOT_ESTABLISHED", report["findings"])
        self.assertFalse(report["restore_verified"])

    def test_no_migration_mode_cannot_hide_schema_change(self):
        candidate, p, receipts = self.bundle()
        env = receipts["database_migration"]
        env["payload"]["migration_mode"] = "no_schema_change"
        self.resign("database_migration", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("NO_MIGRATION_MODE_CONFLICT", report["findings"])

    def test_backup_digest_must_match_restore(self):
        candidate, p, receipts = self.bundle()
        env = receipts["backup_restore"]
        env["payload"]["restore"]["backup_digest"] = "sha256:" + "f" * 64
        self.resign("backup_restore", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["database_correlation_claimed"])
        self.assertTrue(any("RESTORE_BACKUP_OR_CANDIDATE_MISMATCH" in x for x in report["findings"]))

    def test_health_requires_distinct_ordinary_owners_and_zero_grants(self):
        candidate, p, receipts = self.bundle()
        env = receipts["module_uat"]["health_v2"]
        env["payload"]["identity"]["owner_b_subject_digest"] = env["payload"]["identity"]["owner_a_subject_digest"]
        self.resign("health_v2_uat", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["module_uat_claimed"]["health_v2"])
        self.assertTrue(any("HEALTH_TWO_OWNER_IDENTITY_OR_PRIVILEGE_CHECK_FAILED" in x
                            for x in report["findings"]))

    def test_health_cleanup_must_be_supported_and_complete(self):
        candidate, p, receipts = self.bundle()
        env = receipts["module_uat"]["health_v2"]
        env["payload"]["cleanup"]["remaining_count"] = 1
        self.resign("health_v2_uat", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["module_uat_claimed"]["health_v2"])
        self.assertIn("HEALTH_V2:HEALTH_CLEANUP_NOT_PROVEN", report["findings"])

    def test_ui_requires_desktop_and_iphone_safari_observations(self):
        candidate, p, receipts = self.bundle()
        env = receipts["module_uat"]["ui_v2"]
        env["payload"]["device_observations"] = env["payload"]["device_observations"][:1]
        self.resign("ui_v2_uat", env)
        with self.assertRaises(ValueError):
            self.assess((candidate, p, receipts))

    def test_ui_requires_evidence_digest_for_every_case(self):
        candidate, p, receipts = self.bundle()
        env = receipts["module_uat"]["ui_v2"]
        env["payload"]["evidence_digests"].pop("iphone_safari")
        self.resign("ui_v2_uat", env)
        with self.assertRaises(ValueError):
            self.assess((candidate, p, receipts))

    def test_module_uat_must_bind_to_exact_runtime_and_database_context(self):
        candidate, p, receipts = self.bundle()
        env = receipts["module_uat"]["ui_v2"]
        env["payload"]["runtime_receipt_digest"] = "sha256:" + "f" * 64
        self.resign("ui_v2_uat", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["module_uat_claimed"]["ui_v2"])
        self.assertIn("UI_V2:UAT_CANDIDATE_RUNTIME_OR_DATABASE_BINDING_MISMATCH", report["findings"])

    def test_database_receipts_must_share_exact_context_digest(self):
        candidate, p, receipts = self.bundle()
        env = receipts["backup_restore"]
        env["payload"]["context_digest"] = "sha256:" + "f" * 64
        self.resign("backup_restore", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("DATABASE_CONTEXT_OR_CANDIDATE_MISMATCH", report["findings"])

    def test_candidate_mismatch_in_receipt_is_not_silently_rebound(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        env["payload"]["candidate"] = dict(candidate, commit="f" * 40)
        self.resign("risk_review", env)
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("DATABASE_CONTEXT_OR_CANDIDATE_MISMATCH", report["findings"])

    def test_missing_module_receipt_blocks(self):
        candidate, p, receipts = self.bundle()
        receipts["module_uat"]["health_v2"] = None
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertIn("HEALTH_V2_UAT_MISSING", report["findings"])
        self.assertFalse(report["module_uat_claimed"]["health_v2"])

    def test_unknown_receipt_fields_rejected(self):
        candidate, p, receipts = self.bundle()
        receipts["risk_review"]["payload"]["raw_user_data"] = "not allowed"
        self.resign("risk_review", receipts["risk_review"])
        with self.assertRaises(ValueError):
            self.assess((candidate, p, receipts))

    def test_untrusted_key_is_rejected(self):
        candidate, p, receipts = self.bundle()
        env = receipts["risk_review"]
        env["key_id"] = "unknown-key"
        env["signature"] = ""
        message_file, signature_file = self.root / "message.bin", self.root / "signature.bin"
        message_file.write_bytes(auth._signing_message(env))
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey",
                        str(self.keys["risk_review"]["private"]), "-rawin",
                        "-in", str(message_file), "-out", str(signature_file)],
                       check=True, capture_output=True, timeout=5)
        env["signature"] = base64.b64encode(signature_file.read_bytes()).decode("ascii")
        report, _, _, _ = self.assess((candidate, p, receipts))
        self.assertFalse(report["signature_checks"]["risk_review"])
        self.assertIn("RISK_REVIEW:SIGNER_KEY_NOT_TRUSTED", report["findings"])


if __name__ == "__main__":
    unittest.main()
