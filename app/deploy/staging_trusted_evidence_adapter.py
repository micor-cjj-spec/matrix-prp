"""P3.7.1 pure adapter from P3.6 read-smoke projection to intake evidence.

All inputs remain caller assertions. This adapter does not fetch GitHub data,
authenticate the receipt, or promote the result to a trusted/live state.
"""
import re

from staging_trusted_evidence_intake import _exact, _positive, _sha, _digest, _timestamp

REPOSITORY = "micor-cjj-spec/matrix-prp"
EXPECTED_CASE_CHECKS = {
    "U01": 1, "U02": 1, "U03": 1, "U04": 2, "U05": 1,
    "U06": 2, "U07": 1, "U08": 1, "U09": 1,
}
FINDING = re.compile(r"[A-Z0-9_:-]{1,80}")


def adapt_p36_read_smoke(projection, receipt, expected_run, identity, binding,
                         evidence_id, source_ref, observed_at):
    """Create one normalized read_smoke evidence record without trusting it."""
    _exact(projection, {
        "schemaVersion", "source", "state", "candidate", "bindingDigest", "readSmoke",
        "apiPassed", "checksExecuted", "identityCorrelation", "findings",
        "deploymentAuthorized", "productionAuthorized", "releaseEligible", "liveVerified",
    }, "p36_projection")
    _exact(projection["candidate"], {"commit", "artifactDigest", "schema"}, "p36_candidate")
    _exact(receipt, {
        "schemaVersion", "kind", "source", "repository", "issue", "requestCommentId",
        "runId", "runAttempt", "workflowSha", "operation", "state", "report",
        "apiPassed", "checksExecuted", "liveVerified", "deploymentAuthorized",
        "productionAuthorized",
    }, "p36_receipt")
    _exact(expected_run, {"requestCommentId", "runId", "runAttempt", "workflowSha"}, "expected_run")
    _exact(identity, {
        "existing_account_reused", "account_created", "ordinary_non_admin",
        "credential_permissions_checked", "mcp_grant_rows", "login_method",
    }, "identity_assertion")
    _exact(binding, {"source_sha", "source_tree", "schema"}, "candidate_binding")

    _exact(projection["report"] if "report" in projection else {}, set(), "projection_has_no_report")
    if (type(projection["schemaVersion"]) is not int or projection["schemaVersion"] != 1 or
            projection["source"] != "offline_unverified_staging_review" or
            projection["state"] != "BLOCKED" or
            projection["deploymentAuthorized"] is not False or
            projection["productionAuthorized"] is not False or
            projection["releaseEligible"] is not False or
            projection["liveVerified"] is not False or
            type(projection["bindingDigest"]) is not str or
            not _digest(projection["bindingDigest"]) or
            projection["readSmoke"] not in {"API_SMOKE_PASS", "API_SMOKE_INCOMPLETE", "BLOCKED_RUNNER"} or
            type(projection["apiPassed"]) is not int or projection["apiPassed"] < 0 or
            type(projection["checksExecuted"]) is not int or projection["checksExecuted"] < 0 or
            projection["identityCorrelation"] not in {"CLAIMED_MATCH_ONLY", "INCOMPLETE"} or
            type(projection["findings"]) is not list or len(projection["findings"]) > 128 or
            any(type(x) is not str or FINDING.fullmatch(x) is None for x in projection["findings"])):
        raise ValueError("INVALID_P36_PROJECTION")
    if (type(receipt["schemaVersion"]) is not int or receipt["schemaVersion"] != 1 or
            receipt["kind"] != "PRP_STAGING_READ_SMOKE_RECEIPT" or
            receipt["source"] != "github_task_candidate" or receipt["repository"] != REPOSITORY or
            receipt["issue"] != 396 or receipt["operation"] != "READ_SMOKE_ONLY" or
            receipt["liveVerified"] is not False or receipt["deploymentAuthorized"] is not False or
            receipt["productionAuthorized"] is not False):
        raise ValueError("INVALID_P36_RECEIPT")
    if (type(expected_run["requestCommentId"]) is not int or not _positive(expected_run["requestCommentId"]) or
            type(expected_run["runId"]) is not str or
            re.fullmatch(r"[1-9][0-9]{0,19}", expected_run["runId"]) is None or
            type(expected_run["runAttempt"]) is not int or expected_run["runAttempt"] != 1 or
            not _sha(expected_run["workflowSha"])):
        raise ValueError("INVALID_EXPECTED_RUN")
    if (receipt["requestCommentId"], receipt["runId"], receipt["runAttempt"], receipt["workflowSha"]) != (
            expected_run["requestCommentId"], expected_run["runId"],
            expected_run["runAttempt"], expected_run["workflowSha"]):
        raise ValueError("P36_RUN_CONTEXT_MISMATCH")
    if (receipt["state"] != projection["readSmoke"] or
            receipt["apiPassed"] != projection["apiPassed"] or
            receipt["checksExecuted"] != projection["checksExecuted"]):
        raise ValueError("P36_PROJECTION_RECEIPT_MISMATCH")

    _exact(receipt["report"], {"state", "cases"}, "p36_smoke_report")
    if receipt["report"]["state"] not in {"API_SMOKE_PASS", "API_SMOKE_INCOMPLETE"}:
        raise ValueError("INVALID_P36_REPORT_STATE")
    cases = receipt["report"]["cases"]
    if type(cases) is not list or len(cases) != len(EXPECTED_CASE_CHECKS):
        raise ValueError("INVALID_P36_CASES")
    seen = set()
    passed_cases = 0
    passed_checks = 0
    executed_checks = 0
    all_pass = True
    for case in cases:
        _exact(case, {"id", "state", "checks"}, "p36_case")
        case_id = case["id"]
        if (type(case_id) is not str or case_id not in EXPECTED_CASE_CHECKS or
                case_id in seen or case["state"] not in {"API_PASS", "REVIEW_REQUIRED", "PENDING"} or
                type(case["checks"]) is not list or
                len(case["checks"]) > EXPECTED_CASE_CHECKS.get(case_id, 0)):
            raise ValueError("INVALID_P36_CASE")
        seen.add(case_id)
        if case["state"] == "API_PASS":
            if len(case["checks"]) != EXPECTED_CASE_CHECKS[case_id]:
                raise ValueError("P36_CASE_CHECK_COUNT_MISMATCH")
            passed_cases += 1
        else:
            all_pass = False
        for index, check in enumerate(case["checks"], start=1):
            _exact(check, {"check", "result"}, "p36_check")
            if type(check["check"]) is not int or check["check"] != index:
                raise ValueError("P36_CHECK_SEQUENCE_MISMATCH")
            if type(check["result"]) is not str or re.fullmatch(r"[A-Z0-9_:-]{1,64}", check["result"]) is None:
                raise ValueError("INVALID_P36_CHECK_RESULT")
            executed_checks += 1
            if check["result"] == "OK":
                passed_checks += 1
            else:
                all_pass = False
    if seen != set(EXPECTED_CASE_CHECKS):
        raise ValueError("P36_CASE_INVENTORY_MISMATCH")
    if (passed_cases, executed_checks) != (projection["apiPassed"], projection["checksExecuted"]):
        raise ValueError("P36_AGGREGATE_MISMATCH")
    if all_pass != (projection["readSmoke"] == "API_SMOKE_PASS"):
        raise ValueError("P36_STATE_MISMATCH")

    if (projection["candidate"]["commit"] != binding["source_sha"] or
            projection["candidate"]["schema"] != binding["schema"] or
            not _sha(binding["source_tree"]) or
            not _sha(projection["candidate"]["commit"]) or
            not _digest(projection["candidate"]["artifactDigest"]) or
            type(projection["candidate"]["schema"]) is not int or projection["candidate"]["schema"] <= 0):
        raise ValueError("P36_CANDIDATE_BINDING_MISMATCH")
    if (type(identity["existing_account_reused"]) is not bool or
            type(identity["account_created"]) is not bool or
            type(identity["ordinary_non_admin"]) is not bool or
            type(identity["credential_permissions_checked"]) is not bool or
            type(identity["mcp_grant_rows"]) is not int or identity["mcp_grant_rows"] < 0 or
            identity["login_method"] not in {"password_login", "oauth_pkce"}):
        raise ValueError("INVALID_IDENTITY_ASSERTION")

    expected_ref = "issue-comment:" + str(expected_run["requestCommentId"])
    if source_ref != expected_ref or type(evidence_id) is not str or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", evidence_id) is None:
        raise ValueError("INVALID_EVIDENCE_REFERENCE")
    if type(observed_at) is not int or observed_at <= 0:
        raise ValueError("INVALID_OBSERVATION_TIME")

    return {
        "evidence_id": evidence_id,
        "kind": "read_smoke",
        "source_class": "p36_projection_claim",
        "source_ref": source_ref,
        "observed_at": observed_at,
        "binding": dict(binding),
        "facts": {
            "cases_passed": passed_cases,
            "cases_total": len(EXPECTED_CASE_CHECKS),
            "checks_passed": passed_checks,
            "checks_total": sum(EXPECTED_CASE_CHECKS.values()),
            "existing_account_reused": identity["existing_account_reused"],
            "account_created": identity["account_created"],
            "ordinary_non_admin": identity["ordinary_non_admin"],
            "credential_permissions_checked": identity["credential_permissions_checked"],
            "mcp_grant_rows": identity["mcp_grant_rows"],
            "login_method": identity["login_method"],
            "live_verified": receipt["liveVerified"],
            "deployment_authorized": receipt["deploymentAuthorized"],
            "production_authorized": receipt["productionAuthorized"],
        },
    }
