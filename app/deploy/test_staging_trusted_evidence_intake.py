import copy
import unittest

from staging_trusted_evidence_intake import validate_bundle
from staging_trusted_evidence_adapter import adapt_p36_read_smoke


NOW = 2_000_000
CANDIDATE = {
    "source_sha": "a" * 40,
    "source_tree": "b" * 40,
    "schema": 31,
    "backend_image": "sha256:" + "1" * 64,
    "gateway_image": "sha256:" + "2" * 64,
    "artifact_id": 900,
    "archive_digest": "sha256:" + "3" * 64,
    "witness_run_id": 901,
    "witness_attempt": 1,
    "witness_sha": "c" * 40,
}
BINDING = {"source_sha": CANDIDATE["source_sha"],
           "source_tree": CANDIDATE["source_tree"], "schema": CANDIDATE["schema"]}


def record(evidence_id, kind, source_class, source_ref, facts, observed_at=NOW - 10):
    return {
        "evidence_id": evidence_id, "kind": kind, "source_class": source_class,
        "source_ref": source_ref, "observed_at": observed_at,
        "binding": dict(BINDING), "facts": facts,
    }


def github_run():
    run_id = 800
    jobs = []
    for job_id, name in ((1, "backend-tests"), (2, "web-build")):
        jobs.append({
            "job_id": job_id, "name": name, "run_id": run_id, "attempt": 1,
            "head_sha": CANDIDATE["source_sha"], "status": "completed", "conclusion": "success",
        })
    return record("github-run", "github_run", "github_metadata_claim", "actions-run:800", {
        "workflow_path": ".github/workflows/ci.yml", "workflow_sha": "d" * 40,
        "run_id": run_id, "attempt": 1, "latest_attempt": 1, "total_count": len(jobs),
        "head_sha": CANDIDATE["source_sha"], "tree_sha": CANDIDATE["source_tree"],
        "event": "pull_request", "status": "completed", "conclusion": "success", "jobs": jobs,
    })


def artifact_witness():
    return record("artifact", "artifact_witness", "artifact_bytes_review_claim", "artifact:900", {
        "artifact_id": 900, "witness_run_id": 901, "witness_attempt": 1,
        "witness_sha": CANDIDATE["witness_sha"], "source_sha": CANDIDATE["source_sha"],
        "source_tree": CANDIDATE["source_tree"], "archive_digest": CANDIDATE["archive_digest"],
        "expires_at": NOW + 3600, "byte_review_status": "claimed_pass",
        "archive_bytes_sha256": "e" * 64, "manifest_sha256": "f" * 64,
        "files_checked": 4, "files_expected": 4,
    })


def runtime_cutover():
    return record("runtime", "runtime_cutover", "operator_receipt_claim", "issue-comment:1001", {
        "backend_image": CANDIDATE["backend_image"], "gateway_image": CANDIDATE["gateway_image"],
        "mysql_before_image": "sha256:" + "4" * 64,
        "mysql_after_image": "sha256:" + "4" * 64, "schema": 31,
        "fresh_backup_digest": "sha256:" + "5" * 64, "preflight_status": "pass",
        "health_status": "pass", "rollback_status": "pass", "production_targeted": False,
    })


def read_smoke():
    return record("smoke", "read_smoke", "operator_receipt_claim", "issue-comment:1002", {
        "cases_passed": 9, "cases_total": 9, "checks_passed": 11, "checks_total": 11,
        "existing_account_reused": True, "account_created": False, "ordinary_non_admin": True,
        "credential_permissions_checked": True, "mcp_grant_rows": 0, "login_method": "password_login",
        "live_verified": False, "deployment_authorized": False, "production_authorized": False,
    })


def business_uat():
    return record("business", "business_uat", "owner_uat_claim", "issue-comment:1003", {
        "suite": "health", "write_scope": "synthetic_write", "cleanup_status": "pass",
        "owner_aliases": ["owner_a", "owner_b"],
        "case_results": [
            {"case_id": "H01", "status": "pass", "owner_alias": "owner_a"},
            {"case_id": "H02", "status": "pass", "owner_alias": "owner_b"},
        ],
    })


def device_uat():
    return record("device", "device_uat", "owner_uat_claim", "issue-comment:1004", {
        "device_alias": "iphone_qa", "platform_version": "iOS 18.1", "browser_version": "Safari 18.1",
        "case_results": [
            {"case_id": "UI01", "device_class": "desktop", "status": "pass"},
            {"case_id": "UI04", "device_class": "iphone_safari", "status": "pass"},
            {"case_id": "UI06", "device_class": "iphone_pwa", "status": "pass"},
        ],
    })


def backup_restore():
    return record("restore", "backup_restore", "operator_receipt_claim", "issue-comment:1005", {
        "backup_digest": "sha256:" + "6" * 64, "source_instance_digest": "sha256:" + "7" * 64,
        "restore_target_digest": "sha256:" + "8" * 64, "restored_schema": 31,
        "history_digest": "sha256:" + "9" * 64, "data_digest": "sha256:" + "a" * 64,
        "validation_status": "pass", "isolated": True, "created_at": NOW - 500, "restored_at": NOW - 400,
    })


def bundle():
    return {
        "schema_version": 1, "repository": "micor-cjj-spec/matrix-prp",
        "repository_id": 1261866723, "issue": 396, "environment": "prp-unified-396",
        "candidate": dict(CANDIDATE),
        "evidence": [github_run(), artifact_witness(), runtime_cutover(), read_smoke(),
                     business_uat(), device_uat(), backup_restore()],
    }


def p36_case_report():
    counts = {"U01": 1, "U02": 1, "U03": 1, "U04": 2, "U05": 1,
              "U06": 2, "U07": 1, "U08": 1, "U09": 1}
    return {
        "state": "API_SMOKE_PASS",
        "cases": [{"id": case_id, "state": "API_PASS",
                   "checks": [{"check": i, "result": "OK"} for i in range(1, count + 1)]}
                  for case_id, count in counts.items()],
    }


def p36_adapter_inputs():
    expected = {"requestCommentId": 2001, "runId": "2002", "runAttempt": 1,
                "workflowSha": "d" * 40}
    receipt = {
        "schemaVersion": 1, "kind": "PRP_STAGING_READ_SMOKE_RECEIPT",
        "source": "github_task_candidate", "repository": "micor-cjj-spec/matrix-prp",
        "issue": 396, "requestCommentId": 2001, "runId": "2002", "runAttempt": 1,
        "workflowSha": "d" * 40, "operation": "READ_SMOKE_ONLY", "state": "API_SMOKE_PASS",
        "report": p36_case_report(), "apiPassed": 9, "checksExecuted": 11,
        "liveVerified": False, "deploymentAuthorized": False, "productionAuthorized": False,
    }
    projection = {
        "schemaVersion": 1, "source": "offline_unverified_staging_review", "state": "BLOCKED",
        "candidate": {"commit": CANDIDATE["source_sha"],
                      "artifactDigest": CANDIDATE["archive_digest"], "schema": 31},
        "bindingDigest": "sha256:" + "b" * 64, "readSmoke": "API_SMOKE_PASS",
        "apiPassed": 9, "checksExecuted": 11, "identityCorrelation": "CLAIMED_MATCH_ONLY",
        "findings": ["SOURCE_AUTHENTICITY_NOT_ESTABLISHED", "BUSINESS_UAT_NOT_ESTABLISHED"],
        "deploymentAuthorized": False, "productionAuthorized": False,
        "releaseEligible": False, "liveVerified": False,
    }
    identity = {
        "existing_account_reused": True, "account_created": False, "ordinary_non_admin": True,
        "credential_permissions_checked": True, "mcp_grant_rows": 0, "login_method": "password_login",
    }
    return projection, receipt, expected, identity


class TrustedEvidenceIntakeTests(unittest.TestCase):
    def test_complete_bundle_is_only_validated_for_review(self):
        result = validate_bundle(bundle(), NOW)
        self.assertEqual(result["intake_state"], "VALIDATED_FOR_REVIEW")
        self.assertEqual(result["summary"]["records_received"], 7)
        self.assertEqual(result["evidence_trust"], "UNAUTHENTICATED_CALLER_ASSERTIONS")
        self.assertFalse(result["artifact_bytes_independently_verified"])
        self.assertFalse(result["runtime_identity_independently_verified"])
        self.assertFalse(result["human_authority_independently_verified"])
        self.assertFalse(result["stage_deployment_authorized"])
        self.assertFalse(result["executor_activation_authorized"])
        self.assertFalse(result["credential_migration_authorized"])
        self.assertFalse(result["oauth_mcp_authorized"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["live_verified"])

    def test_missing_evidence_kind_stays_review_required(self):
        data = bundle()
        data["evidence"].pop()
        result = validate_bundle(data, NOW)
        self.assertEqual(result["intake_state"], "REVIEW_REQUIRED")
        self.assertIn("MISSING_REQUIRED_EVIDENCE:backup_restore", result["findings"])

    def test_stale_runtime_is_not_accepted(self):
        data = bundle()
        data["evidence"][2]["observed_at"] = NOW - 901
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:EVIDENCE_STALE", result["findings"])

    def test_future_evidence_is_not_accepted(self):
        data = bundle()
        data["evidence"][2]["observed_at"] = NOW + 1
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:EVIDENCE_FROM_FUTURE", result["findings"])

    def test_candidate_binding_mismatch_is_visible(self):
        data = bundle()
        data["evidence"][2]["binding"]["source_sha"] = "f" * 40
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:CANDIDATE_BINDING_MISMATCH", result["findings"])

    def test_backend_image_mismatch_is_visible(self):
        data = bundle()
        data["evidence"][2]["facts"]["backend_image"] = "sha256:" + "f" * 64
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:BACKEND_IMAGE_MISMATCH", result["findings"])

    def test_mysql_mutation_is_visible(self):
        data = bundle()
        data["evidence"][2]["facts"]["mysql_after_image"] = "sha256:" + "f" * 64
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:MYSQL_IMAGE_CHANGED", result["findings"])

    def test_production_target_report_is_visible(self):
        data = bundle()
        data["evidence"][2]["facts"]["production_targeted"] = True
        result = validate_bundle(data, NOW)
        self.assertIn("runtime_cutover:PRODUCTION_TARGET_REPORTED", result["findings"])

    def test_artifact_witness_cannot_confuse_witness_and_source_sha(self):
        data = bundle()
        data["evidence"][1]["facts"]["witness_sha"] = CANDIDATE["source_sha"]
        result = validate_bundle(data, NOW)
        self.assertIn("artifact_witness:ARTIFACT_CANDIDATE_OR_WITNESS_MISMATCH", result["findings"])

    def test_expired_artifact_is_visible(self):
        data = bundle()
        data["evidence"][1]["facts"]["expires_at"] = NOW - 1
        result = validate_bundle(data, NOW)
        self.assertIn("artifact_witness:ARTIFACT_EXPIRED", result["findings"])

    def test_archive_bytes_claim_requires_manifest_and_complete_file_count(self):
        data = bundle()
        data["evidence"][1]["facts"]["files_checked"] = 3
        result = validate_bundle(data, NOW)
        self.assertIn("artifact_witness:ARTIFACT_BYTE_REVIEW_INCOMPLETE", result["findings"])

    def test_github_rerun_attempt_is_not_latest(self):
        data = bundle()
        data["evidence"][0]["facts"]["latest_attempt"] = 2
        result = validate_bundle(data, NOW)
        self.assertIn("github_run:RUN_ATTEMPT_SUPERSEDED", result["findings"])

    def test_github_job_must_bind_to_same_run_attempt_and_head(self):
        data = bundle()
        data["evidence"][0]["facts"]["jobs"][0]["run_id"] = 999
        result = validate_bundle(data, NOW)
        self.assertIn("github_run:JOB_RUN_BINDING_MISMATCH", result["findings"])

    def test_github_job_inventory_count_must_be_complete(self):
        data = bundle()
        data["evidence"][0]["facts"]["total_count"] = 3
        result = validate_bundle(data, NOW)
        self.assertIn("github_run:JOB_INVENTORY_INCOMPLETE", result["findings"])

    def test_unallowlisted_workflow_is_rejected(self):
        data = bundle()
        data["evidence"][0]["facts"]["workflow_path"] = ".github/workflows/deploy-prp.yml"
        with self.assertRaises(ValueError):
            validate_bundle(data, NOW)

    def test_duplicate_evidence_kind_is_rejected(self):
        data = bundle()
        data["evidence"].append(copy.deepcopy(data["evidence"][0]))
        with self.assertRaises(ValueError):
            validate_bundle(data, NOW)

    def test_extra_fields_are_rejected(self):
        data = bundle()
        data["evidence"][3]["facts"]["password"] = "not-a-real-secret"
        with self.assertRaises(ValueError):
            validate_bundle(data, NOW)

    def test_positive_live_flag_is_never_accepted(self):
        data = bundle()
        data["evidence"][3]["facts"]["live_verified"] = True
        result = validate_bundle(data, NOW)
        self.assertIn("read_smoke:UNTRUSTED_POSITIVE_AUTHORIZATION", result["findings"])
        self.assertFalse(result["live_verified"])

    def test_synthetic_write_requires_cleanup_claim(self):
        data = bundle()
        data["evidence"][4]["facts"]["cleanup_status"] = "pending"
        result = validate_bundle(data, NOW)
        self.assertIn("business_uat:SYNTHETIC_WRITE_CLEANUP_NOT_PASS", result["findings"])

    def test_cross_module_requires_two_owner_aliases(self):
        data = bundle()
        data["evidence"][4]["facts"]["suite"] = "cross_module"
        data["evidence"][4]["facts"]["owner_aliases"] = ["owner_a"]
        data["evidence"][4]["facts"]["case_results"][1]["owner_alias"] = "owner_a"
        result = validate_bundle(data, NOW)
        self.assertIn("business_uat:TWO_OWNER_EVIDENCE_MISSING", result["findings"])

    def test_device_versions_missing_is_visible(self):
        data = bundle()
        data["evidence"][5]["facts"]["platform_version"] = "not_recorded"
        result = validate_bundle(data, NOW)
        self.assertIn("device_uat:DEVICE_VERSION_METADATA_MISSING", result["findings"])

    def test_restore_must_be_isolated_and_same_candidate_schema(self):
        data = bundle()
        data["evidence"][6]["facts"]["restore_target_digest"] = data["evidence"][6]["facts"]["source_instance_digest"]
        result = validate_bundle(data, NOW)
        self.assertIn("backup_restore:RESTORE_TARGET_NOT_ISOLATED", result["findings"])

    def test_malformed_enum_type_is_rejected_as_value_error(self):
        data = bundle()
        data["evidence"][0]["facts"]["status"] = []
        with self.assertRaises(ValueError):
            validate_bundle(data, NOW)

    def test_adapter_maps_p36_without_promoting_authority(self):
        projection, receipt, expected, identity = p36_adapter_inputs()
        evidence = adapt_p36_read_smoke(
            projection, receipt, expected, identity, BINDING,
            "adapted-smoke", "issue-comment:2001", NOW - 5,
        )
        self.assertEqual(evidence["kind"], "read_smoke")
        self.assertEqual(evidence["source_class"], "p36_projection_claim")
        data = bundle()
        data["evidence"][3] = evidence
        result = validate_bundle(data, NOW)
        self.assertEqual(result["intake_state"], "VALIDATED_FOR_REVIEW")
        self.assertFalse(result["live_verified"])

    def test_adapter_rejects_mismatched_run_context(self):
        projection, receipt, expected, identity = p36_adapter_inputs()
        expected["runId"] = "9999"
        with self.assertRaises(ValueError):
            adapt_p36_read_smoke(
                projection, receipt, expected, identity, BINDING,
                "adapted-smoke", "issue-comment:2001", NOW - 5,
            )

    def test_adapter_rejects_positive_authorization_claim(self):
        projection, receipt, expected, identity = p36_adapter_inputs()
        projection["liveVerified"] = True
        with self.assertRaises(ValueError):
            adapt_p36_read_smoke(
                projection, receipt, expected, identity, BINDING,
                "adapted-smoke", "issue-comment:2001", NOW - 5,
            )

    def test_adapter_rejects_wrong_case_inventory(self):
        projection, receipt, expected, identity = p36_adapter_inputs()
        receipt["report"]["cases"].pop()
        with self.assertRaises(ValueError):
            adapt_p36_read_smoke(
                projection, receipt, expected, identity, BINDING,
                "adapted-smoke", "issue-comment:2001", NOW - 5,
            )


if __name__ == "__main__":
    unittest.main()
