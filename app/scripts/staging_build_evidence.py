"""P3.6 offline provenance correlation. Inputs are assertions, never authority."""
from release_evidence import exact, sha, digest, schema, REPO
import re

# Core jobs from the existing release-readiness contract. The caller must also
# supply a separately reviewed full expected inventory for this candidate.
CORE_JOBS = {"backend-tests", "web-build", "mobile-build",
             "db-migration-integration", "video-db-integration", "deployment-gate-tests"}


def positive(v):
    return type(v) is int and v > 0


def job_name(v):
    return type(v) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()/,+:-]{0,199}", v) is not None


def assess_build(candidate, snapshot, expected_jobs, now):
    """Check internal consistency only; no transport, discovery, or artifact I/O."""
    exact(candidate, {"repository", "commit", "artifact_digest", "schema"}, "candidate")
    if (candidate["repository"] != REPO or not sha(candidate["commit"]) or
            not digest(candidate["artifact_digest"]) or not schema(candidate["schema"]) or
            not positive(now)):
        raise ValueError("Invalid build candidate")
    if (type(expected_jobs) is not list or not 6 <= len(expected_jobs) <= 100 or
            not all(job_name(n) for n in expected_jobs) or
            len(set(expected_jobs)) != len(expected_jobs) or
            not CORE_JOBS <= set(expected_jobs)):
        raise ValueError("Invalid expected job inventory")
    exact(snapshot, {"candidate_tree", "ci", "artifact"}, "build snapshot")
    tree, ci, artifact = snapshot["candidate_tree"], snapshot["ci"], snapshot["artifact"]
    if not sha(tree):
        raise ValueError("Invalid candidate tree")
    exact(ci, {"repository", "run_id", "attempt", "latest_run_id", "latest_attempt",
               "head", "tested_tree", "status", "conclusion", "total_count", "jobs"}, "CI")
    if (ci["repository"] != REPO or not all(positive(ci[k]) for k in
            ("run_id", "attempt", "latest_run_id", "latest_attempt", "total_count")) or
            not sha(ci["head"]) or not sha(ci["tested_tree"]) or
            ci["status"] not in ("completed", "queued", "in_progress") or
            ci["conclusion"] not in (None, "success", "failure", "cancelled", "skipped") or
            type(ci["jobs"]) is not list or len(ci["jobs"]) > 100):
        raise ValueError("Invalid CI snapshot")
    names, ids = [], []
    blockers = []
    if ci["head"] != candidate["commit"] or ci["tested_tree"] != tree:
        blockers.append("CI_CANDIDATE_OR_TREE_MISMATCH")
    if (ci["run_id"], ci["attempt"]) != (ci["latest_run_id"], ci["latest_attempt"]):
        blockers.append("CI_RUN_SUPERSEDED")
    if ci["status"] != "completed" or ci["conclusion"] != "success":
        blockers.append("CI_NOT_SUCCESS")
    for j in ci["jobs"]:
        exact(j, {"id", "name", "run_id", "attempt", "head", "status", "conclusion"}, "job")
        if (not job_name(j["name"]) or not all(positive(j[k]) for k in ("id", "run_id", "attempt")) or
                not sha(j["head"]) or j["status"] not in ("completed", "queued", "in_progress") or
                j["conclusion"] not in (None, "success", "failure", "cancelled", "skipped")):
            raise ValueError("Invalid CI job")
        names.append(j["name"])
        ids.append(j["id"])
        if (j["run_id"], j["attempt"], j["head"], j["status"], j["conclusion"]) != (
                ci["run_id"], ci["attempt"], ci["head"], "completed", "success"):
            if "CI_JOB_NOT_EXACT_SUCCESS" not in blockers:
                blockers.append("CI_JOB_NOT_EXACT_SUCCESS")
    if (len(names) != ci["total_count"] or len(names) != len(set(names)) or
            len(ids) != len(set(ids)) or set(names) != set(expected_jobs)):
        blockers.append("CI_JOB_INVENTORY_MISMATCH")
    exact(artifact, {"repository", "artifact_id", "run_id", "attempt", "witness_commit",
                     "source_commit", "source_tree", "archive_digest", "schema",
                     "witness_status", "witness_conclusion", "expires_at",
                     "observed_at", "archive_review"}, "artifact")
    if (artifact["repository"] != REPO or not all(positive(artifact[k]) for k in
            ("artifact_id", "run_id", "attempt", "expires_at", "observed_at")) or
            not all(sha(artifact[k]) for k in ("witness_commit", "source_commit", "source_tree")) or
            not digest(artifact["archive_digest"]) or not schema(artifact["schema"]) or
            artifact["witness_status"] not in ("completed", "queued", "in_progress") or
            artifact["witness_conclusion"] not in (None, "success", "failure", "cancelled", "skipped") or
            artifact["archive_review"] not in ("not_reviewed", "checksums_claimed_pass", "failed")):
        raise ValueError("Invalid artifact snapshot")
    if (artifact["source_commit"], artifact["source_tree"], artifact["archive_digest"],
            artifact["schema"]) != (candidate["commit"], tree, candidate["artifact_digest"], candidate["schema"]):
        blockers.append("ARTIFACT_CANDIDATE_MISMATCH")
    if artifact["witness_status"] != "completed" or artifact["witness_conclusion"] != "success":
        blockers.append("ARTIFACT_WITNESS_NOT_SUCCESS")
    if artifact["run_id"] == ci["run_id"] and (artifact["attempt"] != ci["attempt"] or
            artifact["witness_commit"] != ci["head"]):
        blockers.append("ARTIFACT_RUN_IDENTITY_CONFLICT")
    if artifact["expires_at"] <= now or artifact["observed_at"] > now:
        blockers.append("ARTIFACT_EXPIRED_OR_FUTURE")
    if artifact["archive_review"] != "checksums_claimed_pass":
        blockers.append("ARTIFACT_CHECKSUM_REVIEW_INCOMPLETE")
    return {"state": "BLOCKED", "source": "unverified_caller_assertions",
            "candidate_match_claimed": not blockers, "ci_run_id_claimed": ci["run_id"],
            "ci_attempt_claimed": ci["attempt"], "artifact_id_claimed": artifact["artifact_id"],
            "artifact_run_id_claimed": artifact["run_id"],
            "artifact_attempt_claimed": artifact["attempt"],
            "source_tree_claimed": tree,
            "findings": blockers + ["INDEPENDENT_PROVENANCE_NOT_ESTABLISHED"],
            "ci_artifact_run_binding_verified": False, "deployment_authorized": False,
            "production_authorized": False, "live_verified": False}
