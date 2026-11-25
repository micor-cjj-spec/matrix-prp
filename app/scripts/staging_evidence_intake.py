"""P3.7.1: offline intake of normalized evidence claims. No authentication or I/O."""
import hashlib
import json
import re
from release_evidence import REPO, exact, sha, digest, schema
from staging_build_evidence import assess_build, CORE_JOBS, job_name

ENV = "prp-unified-396"
CI_WORKFLOW = (379348789, ".github/workflows/ci.yml")
# First adapter is deliberately restricted to the existing #430 witness profile.
WITNESS_WORKFLOW = (430022983, ".github/workflows/unified-396-artifact-428-witness.yml")
WITNESS_BRANCH = "review/unified-396-artifact-428"
ARTIFACT_NAME = "prp-unified-staging-tested-images-428"
WITNESS_JOBS = {"exact-source-disposable", "Synthetic Health V2 chromium 375/390/1280",
                "Synthetic Health V2 webkit 375/390/1280"}
IMAGES = {"backend", "gateway", "mysql"}
FRESH_SECONDS = 900  # Fixture review window, not an operational SLA.
MAX_INT = 2**53 - 1
MANDATORY = ["SOURCE_AUTHENTICITY_NOT_ESTABLISHED",
             "INDEPENDENT_ARTIFACT_BYTES_NOT_ESTABLISHED_HERE",
             "INDEPENDENT_RUNTIME_AND_DATABASE_PROOF_NOT_ESTABLISHED",
             "BUSINESS_UAT_NOT_ESTABLISHED", "INDEPENDENT_HUMAN_PROOF_NOT_ESTABLISHED"]


def require(ok, label):
    if not ok:
        raise ValueError("Invalid intake: " + label)


def pos(v):
    return type(v) is int and 0 < v <= MAX_INT


def enum(v, allowed):
    return type(v) is str and v in allowed


def ids(obj, keys):
    return all(pos(obj[k]) for k in keys)


def image_map(obj, keys=IMAGES):
    exact(obj, keys, "image IDs")
    require(all(digest(v) for v in obj.values()), "image IDs")


def binding(obj):
    return tuple(obj[k] for k in ("commit", "tree", "archive_digest", "schema"))


def validate_binding(obj):
    require(sha(obj["commit"]) and sha(obj["tree"]) and
            digest(obj["archive_digest"]) and schema(obj["schema"]), "candidate identity")


def fresh(t, now):
    return t <= now and now - t <= FRESH_SECONDS


def branch_name(v):
    return (type(v) is str and len(v) <= 200 and
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,99})*", v) is not None)


def canonical_digest(policy, evidence):
    # Sort unordered inventories, retain every validated field, domain separate.
    p = dict(policy, expected_ci_jobs=sorted(policy["expected_ci_jobs"]))
    e = dict(evidence)
    for key in ("ci", "witness"):
        if e[key] is not None:
            e[key] = dict(e[key], jobs=sorted(e[key]["jobs"], key=lambda j: (j["id"], j["name"])))
    raw = json.dumps({"domain": "PRP_P371_INTAKE_V1", "policy": p, "evidence": e},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode("ascii")).hexdigest()


def validate_run(run, workflow, expected_names, now, findings, prefix):
    exact(run, {"source", "repository", "head_repository", "workflow_id", "workflow_path",
                "run_id", "attempt", "latest_run_id", "latest_attempt", "head", "event", "branch",
                "status", "conclusion", "started_at", "finished_at", "observed_at",
                "total_count", "jobs", "checkout", "tested_tree"}, prefix)
    require(run["source"] == "github_metadata_claim" and run["repository"] == REPO
            and run["head_repository"] == REPO, prefix + " repository")
    require(enum(run["event"], ("push", "pull_request")) and branch_name(run["branch"]),
            prefix + " event/branch")
    require((run["workflow_id"], run["workflow_path"]) == workflow and
            type(run["workflow_id"]) is int, prefix + " workflow")
    require(ids(run, ("run_id", "attempt", "latest_run_id", "latest_attempt",
                       "started_at", "finished_at", "observed_at", "total_count"))
            and all(sha(run[k]) for k in ("head", "checkout", "tested_tree")), prefix + " identity")
    require(enum(run["status"], ("completed", "queued", "in_progress")) and
            (run["conclusion"] is None or enum(run["conclusion"],
             ("success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral"))),
            prefix + " status")
    require(type(run["jobs"]) is list and len(run["jobs"]) <= 100
            and run["total_count"] <= 100, prefix + " job list")
    names, numbers = [], []
    for j in run["jobs"]:
        exact(j, {"id", "name", "run_id", "attempt", "head", "status", "conclusion"}, "job")
        require(ids(j, ("id", "run_id", "attempt")) and job_name(j["name"]) and sha(j["head"])
                and enum(j["status"], ("completed", "queued", "in_progress"))
                and (j["conclusion"] is None or enum(j["conclusion"],
                     ("success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral"))),
                "job")
        names.append(j["name"])
        numbers.append(j["id"])
        if (j["run_id"], j["attempt"], j["head"], j["status"], j["conclusion"]) != (
                run["run_id"], run["attempt"], run["head"], "completed", "success"):
            findings.append(prefix + "_JOB_NOT_EXACT_SUCCESS")
    if (len(names) != run["total_count"] or len(set(names)) != len(names) or
            len(set(numbers)) != len(numbers) or set(names) != set(expected_names)):
        findings.append(prefix + "_JOB_INVENTORY_MISMATCH")
    if (run["run_id"], run["attempt"]) != (run["latest_run_id"], run["latest_attempt"]):
        findings.append(prefix + "_SUPERSEDED")
    if run["status"] != "completed" or run["conclusion"] != "success":
        findings.append(prefix + "_NOT_SUCCESS")
    if not run["started_at"] <= run["finished_at"] <= run["observed_at"] <= now or not fresh(run["observed_at"], now):
        findings.append(prefix + "_STALE_OR_INVALID_CHRONOLOGY")


def assess_intake(policy, evidence, now):
    """Return a deterministic advisory projection; never satisfy CurrentReview or release gates."""
    require(pos(now), "clock")
    exact(policy, {"repository", "environment", "candidate", "ci_context", "expected_ci_jobs",
                   "witness_context", "artifact_id"}, "review policy")
    require(policy["repository"] == REPO and policy["environment"] == ENV, "review policy")
    c = policy["candidate"]
    exact(c, {"commit", "tree", "archive_digest", "schema"}, "candidate")
    validate_binding(c)
    names = policy["expected_ci_jobs"]
    require(type(names) is list and 6 <= len(names) <= 100 and all(job_name(n) for n in names)
            and len(names) == len(set(names)) and CORE_JOBS <= set(names), "reviewed CI inventory")
    cc, wc = policy["ci_context"], policy["witness_context"]
    exact(cc, {"run_id", "attempt", "event", "branch", "checkout"}, "CI context")
    exact(wc, {"run_id", "attempt", "head"}, "witness context")
    require(ids(cc, ("run_id", "attempt")) and ids(wc, ("run_id", "attempt")) and
            sha(cc["checkout"]) and sha(wc["head"]) and pos(policy["artifact_id"]) and
            enum(cc["event"], ("push", "pull_request")) and branch_name(cc["branch"]), "reviewed context")
    # Only the current dev push and the existing #428 review branch are modeled.
    require((cc["event"], cc["branch"]) in (("push", "dev"),
             ("pull_request", "review/unified-396-ui-health-20261125")), "CI context")
    require(cc["event"] != "push" or cc["checkout"] == c["commit"], "push checkout")
    require(cc["run_id"] != wc["run_id"], "distinct witness run")
    exact(evidence, {"schema_version", "ci", "witness", "artifact_metadata", "archive_review", "operator"},
          "intake")
    require(type(evidence["schema_version"]) is int and evidence["schema_version"] == 1, "schema")
    findings = []
    ci, w, a, b, o = (evidence[k] for k in ("ci", "witness", "artifact_metadata", "archive_review", "operator"))
    for key in ("ci", "witness", "artifact_metadata", "archive_review", "operator"):
        if evidence[key] is None:
            findings.append(key.upper() + "_MISSING")

    if ci is not None:
        validate_run(ci, CI_WORKFLOW, names, now, findings, "CI")
        if (ci["run_id"], ci["attempt"], ci["event"], ci["branch"], ci["checkout"],
                ci["head"], ci["tested_tree"]) != (cc["run_id"], cc["attempt"], cc["event"],
                cc["branch"], cc["checkout"], c["commit"], c["tree"]):
            findings.append("CI_REVIEW_CONTEXT_MISMATCH")

    if w is not None:
        validate_run(w, WITNESS_WORKFLOW, WITNESS_JOBS, now, findings, "WITNESS")
        if (w["run_id"], w["attempt"], w["head"], w["event"], w["branch"],
                w["checkout"], w["tested_tree"]) != (wc["run_id"], wc["attempt"], wc["head"],
                "pull_request", WITNESS_BRANCH, c["commit"], c["tree"]):
            findings.append("WITNESS_SOURCE_MAPPING_MISMATCH")

    if a is not None:
        exact(a, {"source", "repository", "artifact_id", "name", "run_id", "attempt", "witness_head",
                  "zip_digest", "created_at", "expires_at", "observed_at", "expired"}, "artifact metadata")
        require(a["source"] == "github_metadata_claim" and a["repository"] == REPO
                and a["name"] == ARTIFACT_NAME and ids(a, ("artifact_id", "run_id", "attempt",
                    "created_at", "expires_at", "observed_at"))
                and sha(a["witness_head"]) and digest(a["zip_digest"]) and type(a["expired"]) is bool,
                "artifact metadata")
        if (a["artifact_id"], a["run_id"], a["attempt"], a["witness_head"]) != (
                policy["artifact_id"], wc["run_id"], wc["attempt"], wc["head"]):
            findings.append("ARTIFACT_WITNESS_CONTEXT_MISMATCH")
        if a["expired"] or a["expires_at"] <= now or not (
                a["created_at"] <= a["observed_at"] < a["expires_at"] and fresh(a["observed_at"], now)):
            findings.append("ARTIFACT_STALE_OR_EXPIRED")
        if w is not None and not w["started_at"] <= a["created_at"] <= w["finished_at"]:
            findings.append("ARTIFACT_OUTSIDE_WITNESS_RUN")

    if b is not None:
        exact(b, {"source", "artifact_id", "zip_digest", "commit", "tree", "archive_digest", "schema",
                  "images", "observed_at", "checksum_status", "source_status", "image_status"}, "archive review")
        require(b["source"] == "independent_archive_review_claim" and
                ids(b, ("artifact_id", "observed_at")) and digest(b["zip_digest"]) and
                all(enum(b[k], ("pass", "fail", "pending")) for k in
                    ("checksum_status", "source_status", "image_status")), "archive review")
        validate_binding(b)
        image_map(b["images"])
        if binding(b) != binding(c) or b["artifact_id"] != policy["artifact_id"]:
            findings.append("ARCHIVE_SOURCE_OR_CANDIDATE_MISMATCH")
        if any(b[k] != "pass" for k in ("checksum_status", "source_status", "image_status")):
            findings.append("ARCHIVE_REVIEW_INCOMPLETE")
        if b["observed_at"] > now:
            findings.append("ARCHIVE_REVIEW_FUTURE")
        if a is not None and (b["artifact_id"], b["zip_digest"]) != (a["artifact_id"], a["zip_digest"]):
            findings.append("ARCHIVE_ZIP_METADATA_MISMATCH")
        if a is not None and not a["created_at"] <= b["observed_at"] < a["expires_at"]:
            findings.append("ARCHIVE_REVIEW_OUTSIDE_ARTIFACT_LIFETIME")

    if o is not None:
        exact(o, {"source", "repository", "environment", "issue", "cutover_comment_id",
                  "smoke_comment_id", "commit", "tree", "archive_digest", "schema", "artifact_id",
                  "images", "mysql_before", "mysql_after", "cutover_at", "smoke_at",
                  "observed_at", "cutover_status", "read_smoke_status", "api_passed", "checks_executed",
                  "ordinary_nonadmin", "mcp_grant_rows", "account_reused"}, "operator claim")
        require(o["source"] == "operator_report_claim" and o["repository"] == REPO
                and o["environment"] == ENV and type(o["issue"]) is int and o["issue"] == 396
                and ids(o, ("cutover_comment_id", "smoke_comment_id", "artifact_id",
                            "cutover_at", "smoke_at", "observed_at"))
                and o["cutover_comment_id"] != o["smoke_comment_id"]
                and enum(o["cutover_status"], ("pass", "fail", "pending"))
                and enum(o["read_smoke_status"], ("API_SMOKE_PASS", "API_SMOKE_INCOMPLETE", "BLOCKED_RUNNER"))
                and type(o["api_passed"]) is int and type(o["checks_executed"]) is int
                and 0 <= o["api_passed"] <= 9 and o["api_passed"] <= o["checks_executed"] <= 11
                and type(o["mcp_grant_rows"]) is int and 0 <= o["mcp_grant_rows"] <= MAX_INT
                and all(type(o[k]) is bool for k in ("ordinary_nonadmin", "account_reused")),
                "operator claim")
        validate_binding(o)
        image_map(o["images"], {"backend", "gateway"})
        for db in (o["mysql_before"], o["mysql_after"]):
            exact(db, {"instance_digest", "image", "schema"}, "preserved MySQL")
            require(digest(db["instance_digest"]) and digest(db["image"]) and schema(db["schema"]),
                    "preserved MySQL")
        if binding(o) != binding(c) or o["artifact_id"] != policy["artifact_id"]:
            findings.append("OPERATOR_CANDIDATE_MISMATCH")
        if b is not None and any(o["images"][k] != b["images"][k] for k in ("backend", "gateway")):
            findings.append("OPERATOR_IMAGE_MISMATCH")
        # The archive's disposable mysql image is NOT the live preserved mysql.
        if o["mysql_before"] != o["mysql_after"] or o["mysql_after"]["schema"] != c["schema"]:
            findings.append("MYSQL_PRESERVATION_NOT_ESTABLISHED")
        if o["cutover_status"] != "pass":
            findings.append("CUTOVER_NOT_PASS")
        if (o["read_smoke_status"], o["api_passed"], o["checks_executed"]) != ("API_SMOKE_PASS", 9, 11):
            findings.append("READ_SMOKE_NOT_PASS")
        if not o["ordinary_nonadmin"] or not o["account_reused"] or o["mcp_grant_rows"] != 0:
            findings.append("READ_SMOKE_IDENTITY_NOT_ORDINARY_REUSED")
        if not o["cutover_at"] <= o["smoke_at"] <= o["observed_at"] <= now or not (
                fresh(o["smoke_at"], now) and fresh(o["observed_at"], now)):
            findings.append("OPERATOR_STALE_OR_INVALID_CHRONOLOGY")
        if b is not None and b["observed_at"] > o["cutover_at"]:
            findings.append("ARCHIVE_REVIEW_AFTER_CUTOVER")
        if a is not None and not a["created_at"] <= o["cutover_at"] < a["expires_at"]:
            findings.append("CUTOVER_OUTSIDE_ARTIFACT_LIFETIME")

    # Reuse P3.6 exact-build correlation only as an advisory adapter. Never
    # feed an intake result to CurrentReview, change gate status, or mint PASS.
    build = None
    if ci is not None and w is not None and a is not None and b is not None:
        if all(enum(q["status"], ("completed", "queued", "in_progress")) and
               (q["conclusion"] is None or enum(q["conclusion"], ("success", "failure", "cancelled", "skipped")))
               for q in [ci, w] + ci["jobs"]):
            candidate = {"repository": REPO, "commit": c["commit"],
                         "artifact_digest": c["archive_digest"], "schema": c["schema"]}
            snapshot = {"candidate_tree": c["tree"], "ci": {
                "repository": REPO, "run_id": ci["run_id"], "attempt": ci["attempt"],
                "latest_run_id": ci["latest_run_id"], "latest_attempt": ci["latest_attempt"],
                "head": ci["head"], "tested_tree": ci["tested_tree"], "status": ci["status"],
                "conclusion": ci["conclusion"], "total_count": ci["total_count"], "jobs": ci["jobs"]},
                "artifact": {"repository": REPO, "artifact_id": a["artifact_id"], "run_id": a["run_id"],
                    "attempt": a["attempt"], "witness_commit": w["head"], "source_commit": b["commit"],
                    "source_tree": b["tree"], "archive_digest": b["archive_digest"], "schema": b["schema"],
                    "witness_status": w["status"], "witness_conclusion": w["conclusion"],
                    "expires_at": a["expires_at"], "observed_at": b["observed_at"],
                    "archive_review": "checksums_claimed_pass" if all(b[k] == "pass" for k in
                        ("checksum_status", "source_status", "image_status")) else "failed"}}
            build = assess_build(candidate, snapshot, names, now)
            findings.extend("P36:" + f for f in build["findings"] if f != "INDEPENDENT_PROVENANCE_NOT_ESTABLISHED")
        else:
            findings.append("P36_ADAPTER_UNSUPPORTED_STATUS")
    return {"schema_version": 1, "source": "offline_unverified_intake", "state": "BLOCKED",
            "candidate_match_claimed": not findings, "binding_digest": canonical_digest(policy, evidence),
            "findings": sorted(set(findings)) + MANDATORY,
            "p36_build_review": build, "source_authenticated": False,
            "artifact_bytes_verified": False, "runtime_verified": False,
            "business_uat_verified": False, "approval_authorized": False,
            "release_eligible": False, "deployment_authorized": False,
            "production_authorized": False, "live_verified": False}
