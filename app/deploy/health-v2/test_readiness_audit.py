"""Synthetic, offline tests for the non-mutating Health V2 staging evidence gate."""
import json
import tempfile
import unittest
from pathlib import Path

from readiness_audit import EvidenceBlocked, main, review, reviewed_flyway_version

SHA = "a" * 40


def synthetic():
    return {
        "schema": "health-v2-stage-readiness-v1",
        "stage": {
            "kind": "dedicated-health-v2",
            "public_host": "health-v2-stage.example.net",
            "oidc_host": "auth-health-v2-stage.example.net",
            "gateway_port": 18084,
            "database_name": "prp_health_v2_stage",
            "db_isolated": True,
            "oidc_isolated": True,
            "test_identities_only": True,
            "owner_approved": True,
            "production_mounts_present": False,
            "production_data_used": False,
            "shared_v2_modified": False,
        },
        "observed": {
            "source_sha": SHA,
            "backend_source_sha": SHA,
            "web_source_sha": SHA,
            "backend_image_digest": "sha256:" + "1" * 64,
            "web_image_digest": "sha256:" + "2" * 64,
            "flyway_version": 31,
            "flyway_failed_count": 0,
            "https_hostname_verified": True,
            "oidc_issuer_host": "auth-health-v2-stage.example.net",
            "write_enabled": False,
            "actual_runtime_observation": True,
        },
    }


class ReadinessTests(unittest.TestCase):
    def assert_blocked(self, mutate, code):
        doc = synthetic()
        mutate(doc)
        with self.assertRaises(EvidenceBlocked) as ex:
            review(doc, SHA)
        self.assertEqual(str(ex.exception), code)

    def test_consistency_cannot_certify_real_environment(self):
        self.assertEqual(review(synthetic(), SHA), "DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED")

    def test_shared_v2_port(self):
        self.assert_blocked(lambda d: d["stage"].update(gateway_port=18082), "GATEWAY_PORT_COLLISION")

    def test_production_port(self):
        self.assert_blocked(lambda d: d["stage"].update(gateway_port=11000), "GATEWAY_PORT_COLLISION")

    def test_shared_v2_hostname(self):
        self.assert_blocked(lambda d: d["stage"].update(public_host="prp-test.micor.top"), "SHARED_OR_PRODUCTION_HOST")

    def test_numeric_ip_public_host_not_a_separate_stage_hostname(self):
        # IPv4 and shortened numeric forms must not stand in for an observed
        # DNS / HTTPS stage name. These declarations are not live-host checks.
        for hostname in ("127.0.0.1", "127.1", "192.0.2.55", "8.8.8.8"):
            with self.subTest(hostname=hostname):
                self.assert_blocked(
                    lambda d, host=hostname: d["stage"].update(public_host=host),
                    "IP_LITERAL_HOST_FORBIDDEN",
                )

    def test_numeric_ip_oidc_host_not_a_separate_issuer_hostname(self):
        for hostname in ("127.0.0.2", "192.0.2.2"):
            with self.subTest(hostname=hostname):
                self.assert_blocked(
                    lambda d, host=hostname: d["stage"].update(oidc_host=host),
                    "IP_LITERAL_HOST_FORBIDDEN",
                )

    def test_production_database(self):
        self.assert_blocked(lambda d: d["stage"].update(database_name="matrix_prp"), "SHARED_OR_PRODUCTION_DB")

    def test_shared_v2_database_is_not_a_dedicated_health_stage(self):
        self.assert_blocked(lambda d: d["stage"].update(database_name="matrix_prp_mcp_stage_v2"), "SHARED_OR_PRODUCTION_DB")
        self.assert_blocked(lambda d: d["stage"].update(database_name="matrix_prp_mcp_stage_v2_clone"), "SHARED_OR_PRODUCTION_DB")

    def test_real_data_forbidden(self):
        self.assert_blocked(lambda d: d["stage"].update(production_data_used=True), "UNSAFE_PRODUCTION_DATA_USED")

    def test_shared_stack_mutation_forbidden(self):
        self.assert_blocked(lambda d: d["stage"].update(shared_v2_modified=True), "UNSAFE_SHARED_V2_MODIFIED")

    def test_missing_owner_authorization(self):
        self.assert_blocked(lambda d: d["stage"].update(owner_approved=False), "STAGE_GUARD_OWNER_APPROVED")

    def test_mismatched_runtime_code(self):
        self.assert_blocked(lambda d: d["observed"].update(web_source_sha="b" * 40), "SOURCE_SHA_MISMATCH")

    def test_build_digest_missing(self):
        self.assert_blocked(lambda d: d["observed"].update(backend_image_digest="missing"), "IMAGE_DIGEST_UNVERIFIED")

    def test_v29_does_not_prove_complete_reviewed_candidate(self):
        self.assert_blocked(lambda d: d["observed"].update(flyway_version=29),
                            "FLYWAY_REVIEWED_VERSION_NOT_VERIFIED")

    def test_v30_only_is_incomplete_when_reviewed_candidate_includes_v31(self):
        self.assertEqual(reviewed_flyway_version(), 31)
        self.assert_blocked(lambda d: d["observed"].update(flyway_version=30),
                            "FLYWAY_REVIEWED_VERSION_NOT_VERIFIED")

    def test_true_bool_is_not_an_accepted_flyway_version(self):
        self.assert_blocked(lambda d: d["observed"].update(flyway_version=True),
                            "FLYWAY_REVIEWED_VERSION_NOT_VERIFIED")

    def test_health_only_reviewed_policy_still_accepts_v30(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "migration-policy.json"
            source = json.loads(
                (Path(__file__).resolve().parent.parent / "migration-policy.json").read_text()
            )
            source["rules"] = [r for r in source["rules"] if r["version"] <= 30]
            policy.write_text(json.dumps(source), encoding="utf-8")
            doc = synthetic()
            doc["observed"]["flyway_version"] = 30
            self.assertEqual(reviewed_flyway_version(policy), 30)
            self.assertEqual(review(doc, SHA, policy_path=policy),
                             "DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED")
            doc["observed"]["flyway_version"] = 31
            with self.assertRaisesRegex(EvidenceBlocked, "FLYWAY_REVIEWED_VERSION_NOT_VERIFIED"):
                review(doc, SHA, policy_path=policy)

    def test_duplicate_or_missing_migration_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "migration-policy.json"
            with self.assertRaisesRegex(EvidenceBlocked, "MIGRATION_POLICY_UNVERIFIED"):
                reviewed_flyway_version(policy)
            data = json.loads(
                (Path(__file__).resolve().parent.parent / "migration-policy.json").read_text()
            )
            original_rules = data["rules"]
            data["rules"] = original_rules + [dict(original_rules[-1])]
            policy.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceBlocked, "MIGRATION_POLICY_UNVERIFIED"):
                reviewed_flyway_version(policy)
            data["rules"] = [r for r in original_rules if r["version"] != 30]
            policy.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceBlocked, "MIGRATION_POLICY_UNVERIFIED"):
                reviewed_flyway_version(policy)

    def test_source_file_not_runtime(self):
        self.assert_blocked(lambda d: d["observed"].update(actual_runtime_observation=False), "SOURCE_ONLY_NOT_RUNTIME_EVIDENCE")

    def test_writes_disabled_before_auth(self):
        self.assert_blocked(lambda d: d["observed"].update(write_enabled=True), "WRITES_MUST_REMAIN_DISABLED_BEFORE_UAT_APPROVAL")

    def test_sensitive_field_rejected_without_echo(self):
        self.assert_blocked(lambda d: d["stage"].update(DB_PASSWORD="do-not-log"), "SENSITIVE_FIELD_FORBIDDEN")

    def test_invalid_type_for_port(self):
        self.assert_blocked(lambda d: d["stage"].update(gateway_port=True), "GATEWAY_PORT_COLLISION")

    def test_unrecognized_root_field_is_blocked(self):
        self.assert_blocked(lambda d: d.update(approval_note="not independently checked"), "UNRECOGNIZED_ROOT_FIELDS")

    def test_unrecognized_stage_field_is_blocked(self):
        self.assert_blocked(lambda d: d["stage"].update(trusted_extra=True), "UNRECOGNIZED_STAGE_FIELDS")

    def test_unrecognized_observation_field_is_blocked(self):
        self.assert_blocked(lambda d: d["observed"].update(flyway_checksum_verified=True), "UNRECOGNIZED_OBSERVED_FIELDS")

    def test_duplicated_json_evidence_key_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            raw = json.dumps(synthetic())
            self.assertIn('"owner_approved": true', raw)
            path.write_text(raw.replace(
                '"owner_approved": true',
                '"owner_approved": false, "owner_approved": true',
            ), encoding="utf-8")
            self.assertEqual(main(["--evidence", str(path), "--expected-sha", SHA]), 2)

    def test_no_shell_execution_and_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["--evidence", str(Path(tmp) / "missing.json"), "--expected-sha", SHA]), 2)
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(synthetic()), encoding="utf-8")
            self.assertEqual(main(["--evidence", str(path), "--expected-sha", SHA]), 0)


if __name__ == "__main__":
    unittest.main()
