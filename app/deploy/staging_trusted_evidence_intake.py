"""P3.7.1 offline evidence intake contract.

This module validates bounded, caller-supplied evidence claims for review.
It performs no GitHub/API/host access, signature verification, credential use,
database access, workflow dispatch, approval, deployment, or readiness promotion.
"""
import re

REPOSITORY = "micor-cjj-spec/matrix-prp"
REPOSITORY_ID = 1261866723
ISSUE = 396
ENVIRONMENT = "prp-unified-396"
MAX_RECORDS = 32
MAX_JOBS = 100
WORKFLOWS = {
    ".github/workflows/ci.yml",
    ".github/workflows/unified-staging-uat.yml",
    ".github/workflows/unified-staging-read-smoke.yml",
}
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
HEX = re.compile(r"[0-9a-f]{64}")
EVIDENCE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,31}")
SOURCE_REF = {
    "github_run": re.compile(r"actions-run:([1-9][0-9]{0,19})"),
    "artifact_witness": re.compile(r"artifact:([1-9][0-9]{0,19})"),
    "runtime_cutover": re.compile(r"issue-comment:([1-9][0-9]{0,19})"),
    "read_smoke": re.compile(r"issue-comment:([1-9][0-9]{0,19})"),
    "business_uat": re.compile(r"issue-comment:([1-9][0-9]{0,19})"),
    "device_uat": re.compile(r"issue-comment:([1-9][0-9]{0,19})"),
    "backup_restore": re.compile(r"issue-comment:([1-9][0-9]{0,19})"),
}
PROVENANCE = {
    "github_run": {"github_metadata_claim"},
    "artifact_witness": {"github_metadata_claim", "artifact_bytes_review_claim"},
    "runtime_cutover": {"operator_receipt_claim"},
    "read_smoke": {"operator_receipt_claim", "p36_projection_claim"},
    "business_uat": {"owner_uat_claim"},
    "device_uat": {"owner_uat_claim"},
    "backup_restore": {"operator_receipt_claim"},
}
MAX_AGE_SECONDS = {
    "github_run": 86400,
    "artifact_witness": 86400,
    "runtime_cutover": 900,
    "read_smoke": 900,
    "business_uat": 86400,
    "device_uat": 86400,
    "backup_restore": 86400,
}
REQUIRED_KINDS = set(PROVENANCE)
STATUSES = {"pass", "fail", "pending", "skipped", "blocked"}
CONCLUSIONS = {"success", "failure", "cancelled", "skipped", None}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _exact(value, expected, label):
    _require(type(value) is dict and set(value) == set(expected), "INVALID_FIELDS:" + label)


def _positive(value):
    return type(value) is int and value > 0


def _nonnegative(value):
    return type(value) is int and value >= 0


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _digest(value):
    return type(value) is str and DIGEST.fullmatch(value) is not None


def _timestamp(value):
    return _positive(value)


def _one_of(value, allowed):
    return type(value) is str and value in allowed


def _candidate(value):
    _exact(value, {
        "source_sha", "source_tree", "schema", "backend_image", "gateway_image",
        "artifact_id", "archive_digest", "witness_run_id", "witness_attempt", "witness_sha",
    }, "candidate")
    _require(_sha(value["source_sha"]) and _sha(value["source_tree"]) and
             _positive(value["schema"]) and value["schema"] <= 1000000 and
             _digest(value["backend_image"]) and _digest(value["gateway_image"]) and
             _positive(value["artifact_id"]) and _digest(value["archive_digest"]) and
             _positive(value["witness_run_id"]) and _positive(value["witness_attempt"]) and
             _sha(value["witness_sha"]), "INVALID_CANDIDATE")
    return value


def _binding(value, candidate):
    _exact(value, {"source_sha", "source_tree", "schema"}, "candidate_binding")
    _require(_sha(value["source_sha"]) and _sha(value["source_tree"]) and
             _positive(value["schema"]), "INVALID_CANDIDATE_BINDING")
    return (value["source_sha"], value["source_tree"], value["schema"]) == (
        candidate["source_sha"], candidate["source_tree"], candidate["schema"])


def _job_list(value, run):
    _require(type(value) is list and 1 <= len(value) <= MAX_JOBS, "INVALID_JOB_INVENTORY")
    ids, names = set(), set()
    findings = []
    for job in value:
        _exact(job, {"job_id", "name", "run_id", "attempt", "head_sha", "status", "conclusion"}, "job")
        _require(_positive(job["job_id"]) and _positive(job["run_id"]) and
                 _positive(job["attempt"]) and type(job["name"]) is str and
                 re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()/,+:-]{0,199}", job["name"]) is not None and
                 _sha(job["head_sha"]) and _one_of(job["status"], {"completed", "in_progress", "queued"}) and
                 (job["conclusion"] is None or _one_of(job["conclusion"], {"success", "failure", "cancelled", "skipped"})), "INVALID_JOB")
        _require(job["job_id"] not in ids and job["name"] not in names, "DUPLICATE_JOB")
        ids.add(job["job_id"])
        names.add(job["name"])
        if (job["run_id"], job["attempt"], job["head_sha"]) != (
                run["run_id"], run["attempt"], run["head_sha"]):
            findings.append("JOB_RUN_BINDING_MISMATCH")
        if job["status"] != "completed" or job["conclusion"] != "success":
            findings.append("JOB_NOT_SUCCESS")
    return findings


def _facts(kind, facts, candidate, now):
    findings = []
    if kind == "github_run":
        _exact(facts, {"run_role", "workflow_path", "workflow_sha", "run_id", "attempt", "latest_attempt", "total_count",
                       "head_sha", "tree_sha", "event", "status", "conclusion", "jobs"}, kind)
        _require(_one_of(facts["run_role"], {"candidate_ci", "artifact_witness"}) and
                 _one_of(facts["workflow_path"], WORKFLOWS) and _sha(facts["workflow_sha"]) and
                 _positive(facts["run_id"]) and _positive(facts["attempt"]) and
                 _positive(facts["latest_attempt"]) and _positive(facts["total_count"]) and
                 facts["total_count"] <= MAX_JOBS and _sha(facts["head_sha"]) and
                 _sha(facts["tree_sha"]) and _one_of(facts["event"], {"pull_request", "push", "workflow_dispatch", "issue_comment"}) and
                 _one_of(facts["status"], {"completed", "in_progress", "queued"}) and
                 (facts["conclusion"] is None or _one_of(facts["conclusion"], {"success", "failure", "cancelled", "skipped"})), "INVALID_GITHUB_RUN")
        findings.extend(_job_list(facts["jobs"], facts))
        if len(facts["jobs"]) != facts["total_count"]:
            findings.append("JOB_INVENTORY_INCOMPLETE")
        if facts["run_role"] == "candidate_ci" and (facts["head_sha"], facts["tree_sha"]) != (
                candidate["source_sha"], candidate["source_tree"]):
            findings.append("RUN_CANDIDATE_OR_TREE_MISMATCH")
        if facts["run_role"] == "artifact_witness" and (
                facts["run_id"], facts["attempt"], facts["head_sha"]) != (
                candidate["witness_run_id"], candidate["witness_attempt"], candidate["witness_sha"]):
            findings.append("WITNESS_RUN_BINDING_MISMATCH")
        if facts["attempt"] != facts["latest_attempt"]:
            findings.append("RUN_ATTEMPT_SUPERSEDED")
        if facts["status"] != "completed" or facts["conclusion"] != "success":
            findings.append("RUN_NOT_SUCCESS")
    elif kind == "artifact_witness":
        _exact(facts, {"artifact_id", "witness_run_id", "witness_attempt", "witness_sha",
                       "source_sha", "source_tree", "archive_digest", "backend_image", "gateway_image", "expires_at",
                       "byte_review_status", "archive_bytes_sha256", "manifest_sha256",
                       "files_checked", "files_expected"}, kind)
        _require(_positive(facts["artifact_id"]) and _positive(facts["witness_run_id"]) and
                 _positive(facts["witness_attempt"]) and _sha(facts["witness_sha"]) and
                 _sha(facts["source_sha"]) and _sha(facts["source_tree"]) and
                 _digest(facts["archive_digest"]) and _digest(facts["backend_image"]) and
                 _digest(facts["gateway_image"]) and _timestamp(facts["expires_at"]) and
                 _one_of(facts["byte_review_status"], {"not_reviewed", "claimed_pass", "failed"}) and
                 (facts["archive_bytes_sha256"] is None or
                  type(facts["archive_bytes_sha256"]) is str and HEX.fullmatch(facts["archive_bytes_sha256"])) and
                 (facts["manifest_sha256"] is None or
                  type(facts["manifest_sha256"]) is str and HEX.fullmatch(facts["manifest_sha256"])) and
                 _nonnegative(facts["files_checked"]) and _nonnegative(facts["files_expected"]),
                 "INVALID_ARTIFACT_WITNESS")
        if (facts["artifact_id"], facts["witness_run_id"], facts["witness_attempt"],
                facts["witness_sha"], facts["source_sha"], facts["source_tree"],
                facts["archive_digest"], facts["backend_image"], facts["gateway_image"]) != (
                candidate["artifact_id"], candidate["witness_run_id"], candidate["witness_attempt"],
                candidate["witness_sha"], candidate["source_sha"], candidate["source_tree"],
                candidate["archive_digest"], candidate["backend_image"], candidate["gateway_image"]):
            findings.append("ARTIFACT_CANDIDATE_OR_WITNESS_MISMATCH")
        if facts["expires_at"] <= now:
            findings.append("ARTIFACT_EXPIRED")
        if facts["byte_review_status"] == "claimed_pass":
            if (not facts["archive_bytes_sha256"] or not facts["manifest_sha256"] or
                    facts["files_expected"] <= 0 or facts["files_checked"] != facts["files_expected"]):
                findings.append("ARTIFACT_BYTE_REVIEW_INCOMPLETE")
        elif facts["byte_review_status"] == "failed":
            findings.append("ARTIFACT_BYTE_REVIEW_FAILED")
        else:
            findings.append("ARTIFACT_BYTES_NOT_REVIEWED")
    elif kind == "runtime_cutover":
        _exact(facts, {"backend_image", "gateway_image", "mysql_before_image", "mysql_after_image",
                       "schema", "fresh_backup_digest", "preflight_status", "health_status",
                       "rollback_status", "production_targeted"}, kind)
        _require(all(_digest(facts[k]) for k in ("backend_image", "gateway_image", "mysql_before_image", "mysql_after_image",
                                                  "fresh_backup_digest")) and
                 _positive(facts["schema"]) and
                 all(_one_of(facts[k], STATUSES) for k in ("preflight_status", "health_status", "rollback_status")) and
                 type(facts["production_targeted"]) is bool, "INVALID_RUNTIME_CUTOVER")
        if facts["backend_image"] != candidate["backend_image"]:
            findings.append("BACKEND_IMAGE_MISMATCH")
        if facts["gateway_image"] != candidate["gateway_image"]:
            findings.append("GATEWAY_IMAGE_MISMATCH")
        if facts["schema"] != candidate["schema"]:
            findings.append("RUNTIME_SCHEMA_MISMATCH")
        if facts["mysql_before_image"] != facts["mysql_after_image"]:
            findings.append("MYSQL_IMAGE_CHANGED")
        for key in ("preflight_status", "health_status", "rollback_status"):
            if facts[key] != "pass":
                findings.append(key.upper() + "_NOT_PASS")
        if facts["production_targeted"]:
            findings.append("PRODUCTION_TARGET_REPORTED")
    elif kind == "read_smoke":
        _exact(facts, {"cases_passed", "cases_total", "checks_passed", "checks_total",
                       "existing_account_reused", "account_created", "ordinary_non_admin",
                       "credential_permissions_checked", "mcp_grant_rows", "login_method",
                       "live_verified", "deployment_authorized", "production_authorized"}, kind)
        _require(all(_nonnegative(facts[k]) for k in (
                    "cases_passed", "cases_total", "checks_passed", "checks_total", "mcp_grant_rows")) and
                 facts["cases_total"] > 0 and facts["checks_total"] > 0 and
                 facts["cases_passed"] <= facts["cases_total"] and
                 facts["checks_passed"] <= facts["checks_total"] and
                 all(type(facts[k]) is bool for k in (
                    "existing_account_reused", "account_created", "ordinary_non_admin",
                    "credential_permissions_checked", "live_verified", "deployment_authorized",
                    "production_authorized")) and
                 _one_of(facts["login_method"], {"password_login", "oauth_pkce"}), "INVALID_READ_SMOKE")
        if facts["cases_passed"] != facts["cases_total"] or facts["checks_passed"] != facts["checks_total"]:
            findings.append("READ_SMOKE_INCOMPLETE")
        if not facts["existing_account_reused"] or facts["account_created"]:
            findings.append("TEST_ACCOUNT_LIFECYCLE_UNEXPECTED")
        if not facts["ordinary_non_admin"] or not facts["credential_permissions_checked"]:
            findings.append("TEST_IDENTITY_OR_CREDENTIAL_CHECK_INCOMPLETE")
        if facts["mcp_grant_rows"] != 0:
            findings.append("MCP_GRANTS_PRESENT")
        if any(facts[k] for k in ("live_verified", "deployment_authorized", "production_authorized")):
            findings.append("UNTRUSTED_POSITIVE_AUTHORIZATION")
    elif kind == "business_uat":
        _exact(facts, {"suite", "write_scope", "cleanup_status", "case_results", "owner_aliases"}, kind)
        _require(_one_of(facts["suite"], {"health", "personal_os", "finance", "learning", "chat", "cross_module"}) and
                 _one_of(facts["write_scope"], {"read_only", "synthetic_write"}) and
                 _one_of(facts["cleanup_status"], STATUSES) and type(facts["case_results"]) is list and
                 1 <= len(facts["case_results"]) <= 100 and type(facts["owner_aliases"]) is list and
                 1 <= len(facts["owner_aliases"]) <= 2 and
                 all(type(a) is str and ALIAS.fullmatch(a) for a in facts["owner_aliases"]) and
                 len(set(facts["owner_aliases"])) == len(facts["owner_aliases"]), "INVALID_BUSINESS_UAT")
        case_ids = set()
        for row in facts["case_results"]:
            _exact(row, {"case_id", "status", "owner_alias"}, "business_uat_case")
            _require(type(row["case_id"]) is str and re.fullmatch(r"[A-Z][A-Z0-9_-]{1,31}", row["case_id"]) and
                     _one_of(row["status"], STATUSES) and row["owner_alias"] in facts["owner_aliases"],
                     "INVALID_BUSINESS_UAT_CASE")
            _require(row["case_id"] not in case_ids, "DUPLICATE_UAT_CASE")
            case_ids.add(row["case_id"])
            if row["status"] != "pass":
                findings.append("BUSINESS_UAT_CASE_NOT_PASS")
        if facts["write_scope"] == "synthetic_write" and facts["cleanup_status"] != "pass":
            findings.append("SYNTHETIC_WRITE_CLEANUP_NOT_PASS")
        if facts["suite"] == "cross_module" and len(facts["owner_aliases"]) != 2:
            findings.append("TWO_OWNER_EVIDENCE_MISSING")
    elif kind == "device_uat":
        _exact(facts, {"device_alias", "platform_version", "browser_version", "case_results"}, kind)
        _require(type(facts["device_alias"]) is str and ALIAS.fullmatch(facts["device_alias"]) and
                 type(facts["platform_version"]) is str and
                 re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,63}", facts["platform_version"]) and
                 type(facts["browser_version"]) is str and
                 re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,63}", facts["browser_version"]) and
                 type(facts["case_results"]) is list and 1 <= len(facts["case_results"]) <= 100,
                 "INVALID_DEVICE_UAT")
        case_ids = set()
        for row in facts["case_results"]:
            _exact(row, {"case_id", "device_class", "status"}, "device_uat_case")
            _require(type(row["case_id"]) is str and re.fullmatch(r"[A-Z][A-Z0-9_-]{1,31}", row["case_id"]) and
                     _one_of(row["device_class"], {"desktop", "iphone_safari", "iphone_pwa", "android_chrome"}) and
                     _one_of(row["status"], STATUSES), "INVALID_DEVICE_UAT_CASE")
            _require(row["case_id"] not in case_ids, "DUPLICATE_DEVICE_CASE")
            case_ids.add(row["case_id"])
            if row["status"] != "pass":
                findings.append("DEVICE_UAT_CASE_NOT_PASS")
        if facts["platform_version"] == "not_recorded" or facts["browser_version"] == "not_recorded":
            findings.append("DEVICE_VERSION_METADATA_MISSING")
    elif kind == "backup_restore":
        _exact(facts, {"backup_digest", "source_instance_digest", "restore_target_digest",
                       "restored_schema", "history_digest", "data_digest", "validation_status",
                       "isolated", "created_at", "restored_at"}, kind)
        _require(all(_digest(facts[k]) for k in (
                    "backup_digest", "source_instance_digest", "restore_target_digest",
                    "history_digest", "data_digest")) and
                 _positive(facts["restored_schema"]) and _one_of(facts["validation_status"], STATUSES) and
                 type(facts["isolated"]) is bool and _timestamp(facts["created_at"]) and
                 _timestamp(facts["restored_at"]) and facts["created_at"] <= facts["restored_at"],
                 "INVALID_BACKUP_RESTORE")
        if facts["restored_schema"] != candidate["schema"]:
            findings.append("RESTORE_SCHEMA_MISMATCH")
        if facts["source_instance_digest"] == facts["restore_target_digest"] or not facts["isolated"]:
            findings.append("RESTORE_TARGET_NOT_ISOLATED")
        if facts["validation_status"] != "pass":
            findings.append("RESTORE_VALIDATION_NOT_PASS")
    else:
        raise ValueError("UNKNOWN_EVIDENCE_KIND")
    return findings


def validate_bundle(bundle, now):
    """Validate a redacted offline evidence bundle; never authenticates it."""
    _exact(bundle, {"schema_version", "repository", "repository_id", "issue",
                    "environment", "candidate", "evidence"}, "bundle")
    _require(type(bundle["schema_version"]) is int and bundle["schema_version"] == 1 and
             bundle["repository"] == REPOSITORY and bundle["repository_id"] == REPOSITORY_ID and
             type(bundle["issue"]) is int and bundle["issue"] == ISSUE and
             bundle["environment"] == ENVIRONMENT and _timestamp(now), "INVALID_BUNDLE_CONTEXT")
    candidate = _candidate(bundle["candidate"])
    records = bundle["evidence"]
    _require(type(records) is list and len(records) <= MAX_RECORDS, "INVALID_EVIDENCE_LIST")
    ids, refs, kinds = set(), set(), set()
    output = []
    github_runs = []
    all_findings = []
    for record in records:
        _exact(record, {"evidence_id", "kind", "source_class", "source_ref",
                        "observed_at", "binding", "facts"}, "evidence_record")
        kind = record["kind"]
        _require(type(kind) is str and kind in PROVENANCE, "UNKNOWN_EVIDENCE_KIND")
        _require(type(record["evidence_id"]) is str and EVIDENCE_ID.fullmatch(record["evidence_id"]) and
                 type(record["source_class"]) is str and record["source_class"] in PROVENANCE[kind] and
                 type(record["source_ref"]) is str and _timestamp(record["observed_at"]),
                 "INVALID_EVIDENCE_METADATA")
        _require(record["evidence_id"] not in ids and (kind, record["source_ref"]) not in refs and
                 (kind == "github_run" or kind not in kinds), "DUPLICATE_OR_CONFLICTING_EVIDENCE")
        ids.add(record["evidence_id"])
        refs.add((kind, record["source_ref"]))
        kinds.add(kind)
        match = _binding(record["binding"], candidate)
        match_ref = SOURCE_REF[kind].fullmatch(record["source_ref"])
        _require(match_ref is not None, "INVALID_EVIDENCE_REFERENCE")
        facts_findings = _facts(kind, record["facts"], candidate, now)
        findings = list(facts_findings)
        if kind == "github_run":
            github_runs.append(record["facts"])
        if kind == "artifact_witness":
            byte_review_reported = record["facts"]["byte_review_status"] != "not_reviewed"
            if byte_review_reported != (record["source_class"] == "artifact_bytes_review_claim"):
                findings.append("ARTIFACT_PROVENANCE_CLASS_MISMATCH")
        if not match:
            findings.append("CANDIDATE_BINDING_MISMATCH")
        if record["observed_at"] > now:
            findings.append("EVIDENCE_FROM_FUTURE")
        elif now - record["observed_at"] > MAX_AGE_SECONDS[kind]:
            findings.append("EVIDENCE_STALE")
        if kind == "github_run" and int(match_ref.group(1)) != record["facts"]["run_id"]:
            findings.append("GITHUB_RUN_REFERENCE_MISMATCH")
        if kind == "artifact_witness" and int(match_ref.group(1)) != record["facts"]["artifact_id"]:
            findings.append("ARTIFACT_REFERENCE_MISMATCH")
        if findings:
            all_findings.extend(kind + ":" + item for item in findings)
        output.append({
            "evidence_id": record["evidence_id"],
            "kind": kind,
            "source_class": record["source_class"],
            "source_ref": record["source_ref"],
            "observed_at": record["observed_at"],
            "candidate_binding": "MATCH" if match else "MISMATCH",
            "assessment": "REVIEW_REQUIRED" if findings else "CLAIMS_CONSISTENT",
            "findings": sorted(set(findings)),
            "authenticity": "NOT_ESTABLISHED_OFFLINE",
        })
    for kind in sorted(REQUIRED_KINDS - kinds):
        all_findings.append("MISSING_REQUIRED_EVIDENCE:" + kind)
    candidate_runs = [run for run in github_runs if run["run_role"] == "candidate_ci"]
    witness_runs = [run for run in github_runs if run["run_role"] == "artifact_witness"]
    if len(candidate_runs) != 1:
        all_findings.append("CANDIDATE_CI_RUN_MISSING_OR_CONFLICTING")
    if len(witness_runs) != 1:
        all_findings.append("ARTIFACT_WITNESS_RUN_MISSING_OR_CONFLICTING")
    if len(candidate_runs) == 1 and len(witness_runs) == 1:
        if candidate_runs[0]["run_id"] == witness_runs[0]["run_id"]:
            all_findings.append("CANDIDATE_AND_WITNESS_RUN_CONFLATED")
        if (witness_runs[0]["run_id"], witness_runs[0]["attempt"], witness_runs[0]["head_sha"]) != (
                candidate["witness_run_id"], candidate["witness_attempt"], candidate["witness_sha"]):
            all_findings.append("ARTIFACT_WITNESS_RUN_METADATA_MISMATCH")
    all_findings = sorted(set(all_findings))
    return {
        "schema_version": 1,
        "issue": ISSUE,
        "repository": REPOSITORY,
        "environment": ENVIRONMENT,
        "intake_state": "VALIDATED_FOR_REVIEW" if not all_findings else "REVIEW_REQUIRED",
        "evidence_trust": "UNAUTHENTICATED_CALLER_ASSERTIONS",
        "candidate": dict(candidate),
        "summary": {
            "records_received": len(output),
            "records_consistent": sum(1 for row in output if row["assessment"] == "CLAIMS_CONSISTENT"),
            "records_review_required": sum(1 for row in output if row["assessment"] == "REVIEW_REQUIRED"),
            "evidence_kinds_received": sorted(kinds),
            "evidence_kinds_missing": sorted(REQUIRED_KINDS - kinds),
        },
        "records": output,
        "findings": all_findings,
        "source_authenticity": "NOT_ESTABLISHED",
        "artifact_bytes_independently_verified": False,
        "runtime_identity_independently_verified": False,
        "human_authority_independently_verified": False,
        "readiness": "NOT_ESTABLISHED",
        "stage_deployment_authorized": False,
        "executor_activation_authorized": False,
        "credential_migration_authorized": False,
        "oauth_mcp_authorized": False,
        "production_authorized": False,
        "live_verified": False,
    }
