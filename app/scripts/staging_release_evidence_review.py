"""P3.6 offline advisory report; never a trusted collector or authorization gate."""
from release_evidence import inventory, exact, digest, sha, schema
from staging_build_evidence import assess_build
from staging_runtime_evidence import assess_runtime

FIELDS = {"schemaVersion", "source", "state", "candidate", "bindingDigest",
          "readSmoke", "apiPassed", "checksExecuted", "identityCorrelation",
          "findings", "deploymentAuthorized", "productionAuthorized",
          "releaseEligible", "liveVerified"}
REQUIRED_FINDINGS = {"SOURCE_AUTHENTICITY_NOT_ESTABLISHED",
                     "BUSINESS_UAT_NOT_ESTABLISHED",
                     "ARTIFACT_BYTES_NOT_VERIFIED_HERE",
                     "BACKUP_RESTORE_NOT_ESTABLISHED", "HOLD_AND_RISK_NOT_REVIEWED",
                     "INDEPENDENT_HUMAN_PROOF_NOT_ESTABLISHED"}
OPTIONAL_FINDINGS = {"READ_SMOKE_NOT_PASS", "STAGE_IDENTITY_MISSING",
                     "STAGE_IDENTITY_MISMATCH", "STALE_OR_UNBRACKETED_OBSERVATION",
                     "STALE_SMOKE"}
SMOKE_STATES = {"API_SMOKE_PASS", "API_SMOKE_INCOMPLETE", "BLOCKED_RUNNER",
                "BLOCKED_NO_SESSION", "BLOCKED_WRONG_ORIGIN",
                "BLOCKED_TEST_IDENTITY_NOT_CONFIRMED"}


def build_review(bundle, projection, *, build_snapshot=None, expected_jobs=None, now=None,
                 runtime_snapshot=None, runtime_now=None):
    """Combine existing inventory and untrusted projection without promoting any gate."""
    report = inventory(bundle)
    exact(projection, FIELDS, "offline staging projection")
    p = projection
    if (type(p["schemaVersion"]) is not int or p["schemaVersion"] != 1 or
            p["source"] != "offline_unverified_staging_review" or p["state"] != "BLOCKED" or
            any(p[k] is not False for k in ("deploymentAuthorized", "productionAuthorized",
                                            "releaseEligible", "liveVerified")) or
            not digest(p["bindingDigest"])):
        raise ValueError("Invalid offline projection")
    c = p["candidate"]
    exact(c, {"commit", "artifactDigest", "schema"}, "projection candidate")
    if not sha(c["commit"]) or not digest(c["artifactDigest"]) or not schema(c["schema"]):
        raise ValueError("Invalid projection candidate")
    findings = p["findings"]
    if (type(findings) is not list or len(findings) > 11 or
            any(type(f) is not str for f in findings) or
            len(set(findings)) != len(findings) or
            not REQUIRED_FINDINGS <= set(findings) <= REQUIRED_FINDINGS | OPTIONAL_FINDINGS):
        raise ValueError("Invalid projection findings")
    smoke, passed, checks = p["readSmoke"], p["apiPassed"], p["checksExecuted"]
    if (type(smoke) is not str or smoke not in SMOKE_STATES or
            type(passed) is not int or type(checks) is not int or
            not 0 <= passed <= 9 or not passed <= checks <= 11 or
            (smoke == "API_SMOKE_PASS") != (passed == 9 and checks == 11) or
            (smoke.startswith("BLOCKED_") and (passed or checks)) or
            ("READ_SMOKE_NOT_PASS" in findings) != (smoke != "API_SMOKE_PASS") or
            p["identityCorrelation"] != ("INCOMPLETE" if set(findings) & OPTIONAL_FINDINGS
                                         else "CLAIMED_MATCH_ONLY")):
        raise ValueError("Inconsistent offline projection")
    candidate = report["candidate"]
    matched = (candidate["commit"] == c["commit"] and
               candidate["artifact_digest"] == c["artifactDigest"] and
               candidate["schema"] == c["schema"])
    # Inventory remains an inventory of claims, not a source of authenticated facts.
    # Do not transform read smoke, even on exact identity, into a staging pass.
    stage = next(row for row in report["gates"] if row["gate"] == "staging")
    stage["underlying_claimed_status"] = stage["status"]
    stage["underlying_claimed_reason"] = stage["reason"]
    if stage["status"] == "pass":
        stage.update(status="pending", reason="OFFLINE_READ_SMOKE_NOT_UAT")
    blockers = list(report["blockers"])
    blockers.append("staging:OFFLINE_READ_SMOKE_NOT_UAT")
    if not matched:
        blockers.append("staging:PROJECTION_CANDIDATE_MISMATCH")
    report["blockers"] = blockers
    report["state"] = "HELD" if report["hold_state"] == "active" else "BLOCKED"
    report["production_authorized"] = False
    report["offline_staging_projection"] = {
        "source": "unverified_caller_assertions", "candidate_match_claimed": matched,
        "binding_digest_claimed": p["bindingDigest"], "read_smoke_claimed": smoke,
        "api_passed_claimed": passed, "checks_executed_claimed": checks,
        "identity_correlation_claimed": p["identityCorrelation"],
        "findings": sorted(findings), "ci_artifact_run_binding_verified": False,
    }
    if build_snapshot is not None:
        build = assess_build(candidate, build_snapshot, expected_jobs, now)
        claimed_ci = bundle["evidence"].get("ci")
        if (claimed_ci is None or
                (claimed_ci["run_id"], claimed_ci["run_attempt"]) !=
                (build["ci_run_id_claimed"], build["ci_attempt_claimed"])):
            blockers.append("build:INVENTORY_CI_RUN_MISMATCH")
        blockers.extend("build:" + f for f in build["findings"])
        report["offline_build_review"] = build
    elif expected_jobs is not None or now is not None:
        raise ValueError("Incomplete build snapshot parameters")
    if runtime_snapshot is not None:
        runtime = assess_runtime(candidate, p, runtime_snapshot, runtime_now)
        blockers.extend("runtime:" + f for f in runtime["findings"])
        report["offline_runtime_review"] = runtime
    elif runtime_now is not None:
        raise ValueError("Incomplete runtime snapshot parameters")
    return report
