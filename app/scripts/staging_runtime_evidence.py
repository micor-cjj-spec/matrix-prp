"""Offline runtime and UAT assertion review; no host access or trusted authority."""
from release_evidence import exact, sha, digest, schema, REPO
from staging_build_evidence import positive

SERVICES = {"backend", "gateway", "mysql"}
# Proposed common acceptance floor. Module-specific cases must be reviewed separately.
CORE_UAT = {"api_read", "business_write", "owner_isolation", "browser_pwa", "rollback_readiness"}
STATUS = {"pass", "fail", "pending", "skipped"}


def assess_runtime(candidate, projection, snapshot, now):
    exact(candidate, {"repository", "commit", "artifact_digest", "schema"}, "candidate")
    if (candidate["repository"] != REPO or not sha(candidate["commit"]) or
            not digest(candidate["artifact_digest"]) or not schema(candidate["schema"]) or
            not positive(now)):
        raise ValueError("Invalid runtime candidate")
    exact(snapshot, {"environment", "expected_images", "before", "after", "uat"}, "runtime")
    if snapshot["environment"] != "prp-unified-396":
        raise ValueError("Invalid stage environment")
    expected = snapshot["expected_images"]
    exact(expected, SERVICES, "expected images")
    if not all(digest(v) for v in expected.values()):
        raise ValueError("Invalid expected images")
    findings = []
    pc = projection["candidate"]
    if (pc["commit"], pc["artifactDigest"], pc["schema"]) != (
            candidate["commit"], candidate["artifact_digest"], candidate["schema"]):
        findings.append("UAT_SMOKE_CANDIDATE_MISMATCH")
    before, after, uat = snapshot["before"], snapshot["after"], snapshot["uat"]
    for observation in (before, after):
        if observation is None:
            continue
        exact(observation, {"commit", "artifact_digest", "schema", "observed_at",
                            "services", "flyway_failed", "compose_match"}, "observation")
        if (not sha(observation["commit"]) or not digest(observation["artifact_digest"]) or
                not schema(observation["schema"]) or not positive(observation["observed_at"]) or
                type(observation["flyway_failed"]) is not int or observation["flyway_failed"] < 0 or
                type(observation["compose_match"]) is not bool):
            raise ValueError("Invalid runtime observation")
        exact(observation["services"], SERVICES, "runtime services")
        for service in observation["services"].values():
            exact(service, {"image", "config_digest"}, "runtime service")
            if not all(digest(v) for v in service.values()):
                raise ValueError("Invalid runtime service digest")
        if any(observation[k] != candidate[k] for k in ("commit", "artifact_digest", "schema")):
            findings.append("RUNTIME_CANDIDATE_MISMATCH")
        if any(observation["services"][k]["image"] != expected[k] for k in SERVICES):
            findings.append("RUNTIME_IMAGE_MISMATCH")
        if not observation["compose_match"]:
            findings.append("COMPOSE_SOURCE_MISMATCH")
        if observation["flyway_failed"]:
            findings.append("FLYWAY_FAILURE_REPORTED")
        if observation["observed_at"] > now or now - observation["observed_at"] > 900:
            findings.append("RUNTIME_OBSERVATION_STALE_OR_FUTURE")
    if before is None or after is None:
        findings.append("RUNTIME_OBSERVATION_MISSING")
    elif (before["services"] != after["services"] or
          before["observed_at"] > after["observed_at"]):
        findings.append("RUNTIME_CHANGED_DURING_UAT")
    if uat is None:
        findings.append("BUSINESS_UAT_MISSING")
    else:
        exact(uat, {"kind", "commit", "artifact_digest", "schema", "started_at", "finished_at",
                    "smoke_binding_digest", "cases"}, "UAT")
        if (uat["kind"] not in ("synthetic_browser", "stage_business") or
                not sha(uat["commit"]) or not digest(uat["artifact_digest"]) or
                not schema(uat["schema"]) or not digest(uat["smoke_binding_digest"]) or
                not positive(uat["started_at"]) or not positive(uat["finished_at"]) or
                uat["started_at"] > uat["finished_at"] or uat["finished_at"] > now or
                type(uat["cases"]) is not dict or set(uat["cases"]) != CORE_UAT or
                any(type(v) is not str or v not in STATUS for v in uat["cases"].values())):
            raise ValueError("Invalid UAT assertion")
        if uat["kind"] != "stage_business":
            findings.append("SYNTHETIC_BROWSER_NOT_BUSINESS_UAT")
        if any(uat[k] != candidate[k] for k in ("commit", "artifact_digest", "schema")):
            findings.append("UAT_CANDIDATE_MISMATCH")
        if uat["smoke_binding_digest"] != projection["bindingDigest"]:
            findings.append("UAT_SMOKE_BINDING_MISMATCH")
        if projection["identityCorrelation"] != "CLAIMED_MATCH_ONLY" or projection["readSmoke"] != "API_SMOKE_PASS":
            findings.append("UAT_SMOKE_INCOMPLETE")
        if before is None or after is None or not (
                before["observed_at"] <= uat["started_at"] <= uat["finished_at"] <= after["observed_at"]):
            findings.append("UAT_NOT_BRACKETED")
        if now - uat["finished_at"] > 900:
            findings.append("UAT_STALE")
        if any(v != "pass" for v in uat["cases"].values()):
            findings.append("BUSINESS_UAT_INCOMPLETE")
    return {"state": "BLOCKED", "source": "unverified_caller_assertions",
            "runtime_correlation_claimed": not findings,
            "findings": sorted(set(findings)) + ["INDEPENDENT_RUNTIME_AUTHENTICITY_NOT_ESTABLISHED",
                "MODULE_SPECIFIC_UAT_NOT_ESTABLISHED"],
            "stage_verified": False, "deployment_authorized": False,
            "production_authorized": False, "live_verified": False}
