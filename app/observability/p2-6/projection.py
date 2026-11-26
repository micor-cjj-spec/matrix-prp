"""Pure offline CI evidence projection. No network, credentials, or authority."""
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import re
import sys

# Use the existing dev release contract, not a copy or a new release evaluator.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from release_status import evaluate, CHECKS

REPO = "micor-cjj-spec/matrix-prp"
WORKFLOW = ".github/workflows/ci.yml"
TTL = 120
FUTURE = 5
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 8
MAX_ITEMS = 400
MAX_TIME = 4102444800  # 2100-01-01
STATES = ("queued", "in_progress", "success", "failure", "cancelled", "skipped",
          "timed_out", "action_required", "neutral", "stale", "startup_failure", "unknown")
MCP_GROUPS = ("mcp-staging-runtime", "mcp-staging-tls", "mcp-real-pkce-e2e",
              "mcp-integrated-exact-chatgpt-client", "mcp-production-health-auth")
MODULES = {"task", "finance", "record", "video", "practice"}
FALSE_FLAGS = ("candidate_source_verified", "source_authenticated", "artifact_bytes_verified",
               "runtime_verified", "business_uat_verified", "baseline_restored",
               "current_review_satisfied", "release_eligible", "approval_authorized",
               "deployment_authorized", "production_authorized", "live_verified")
RELEASE_STATES = ("HELD", "BLOCKED", "READY_NOT_LIVE", "LIVE_CLAIMED_UNVERIFIED")
PROJECTION_STATES = ("fresh", "stale", "future", "rate_limit", "api_error", "timeout", "invalid")


class EvidenceUnavailable(ValueError):
    pass


def require(condition):
    if not condition:
        raise ValueError("invalid offline evidence")


def exact(obj, keys):
    require(type(obj) is dict and set(obj) == set(keys))


def integer(value, minimum=1, maximum=2**63-1):
    require(type(value) is int and minimum <= value <= maximum)
    return value


def sha(value):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None)
    return value


def epoch(value):
    return integer(value, 1, MAX_TIME)


def stamp(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is not None)
    return epoch(int(datetime.fromisoformat(value[:-1] + "+00:00").timestamp()))


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out)
        out[key] = value
    return out


def reject_constant(_):
    raise ValueError("invalid JSON constant")


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant)


def state(row):
    status, conclusion = row.get("status"), row.get("conclusion")
    if status in ("queued", "requested", "waiting", "pending") and conclusion is None:
        return "queued"
    if status == "in_progress" and conclusion is None:
        return "in_progress"
    if status == "completed" and conclusion in STATES[2:-1]:
        return conclusion
    return "unknown"


def pages(value, key, now, observed):
    require(type(value) is list and 0 < len(value) <= MAX_PAGES)
    items, total = [], None
    for i, envelope in enumerate(value, 1):
        exact(envelope, {"page", "http_status", "received_at", "body"})
        require(integer(envelope["page"], 1, MAX_PAGES) == i)
        status = envelope["http_status"]
        if status is None:
            raise EvidenceUnavailable("timeout")
        require(type(status) is int)
        if status == 429:
            raise EvidenceUnavailable("rate_limit")
        if status != 200:
            require(100 <= status <= 599)
            raise EvidenceUnavailable("api_error")
        t = epoch(envelope["received_at"])
        if now - t >= TTL:
            raise EvidenceUnavailable("stale")
        if t > now + FUTURE or t > observed + FUTURE:
            raise EvidenceUnavailable("future")
        body = envelope["body"]
        require(type(body) is dict and key in body and "total_count" in body)
        n = integer(body["total_count"], 0, MAX_ITEMS)
        if total is None:
            total = n
        require(n == total and type(body[key]) is list and len(body[key]) <= 100)
        require(bool(body[key]) or (total == 0 and len(value) == 1))
        items.extend(body[key])
        require(len(items) <= total)
    require(len(items) == total and all(type(row) is dict for row in items))
    ids = [integer(row.get("id")) for row in items]
    require(len(set(ids)) == len(ids))
    return items


def group(name):
    require(type(name) is str and 0 < len(name) <= 512)
    for prefix in MCP_GROUPS:
        if name == prefix or name.startswith(prefix + " / ") or name.startswith(prefix + " ("):
            return prefix
    return None


def regression_claim(receipt, commit, now):
    if receipt is None:
        return "missing"
    require(type(receipt) is dict and type(receipt.get("schema_version")) is int
            and receipt["schema_version"] == 1 and receipt.get("source") == "offline_simulation"
            and receipt.get("execution_mode") == "OFFLINE_SIMULATION" and receipt.get("state") == "BLOCKED"
            and receipt.get("repository") == REPO and receipt.get("environment") == "prp-unified-396"
            and receipt.get("issue") == 396 and all(receipt.get(k) is False for k in FALSE_FLAGS))
    c = receipt.get("candidate")
    require(type(c) is dict and c.get("repository") == REPO and sha(c.get("commit")) == commit
            and type(c.get("schema")) is int and c["schema"] == 31
            and type(c.get("artifact_digest")) is str
            and re.fullmatch(r"sha256:[a-f0-9]{64}", c["artifact_digest"]) is not None)
    w = receipt.get("window")
    fields = ("runtime_before_at", "started_at", "finished_at", "runtime_after_at")
    exact(w, fields)
    ordered = [epoch(w[k]) for k in fields]
    require(ordered == sorted(ordered) and ordered[-1] <= now + FUTURE
            and now - ordered[-1] < 900 and ordered[-1] - ordered[0] <= 900)
    modules, cleanup = receipt.get("module_results"), receipt.get("cleanup_results")
    exact(modules, MODULES)
    exact(cleanup, {owner + "_" + m for owner in ("A", "B") for m in MODULES | {"account", "category"}})
    require(all(x in ("pass", "pending") for x in [*modules.values(), *cleanup.values()]))
    claim = receipt.get("regression_complete_claimed")
    require(type(claim) is bool)
    complete = (all(x == "pass" for x in [*modules.values(), *cleanup.values()])
                and receipt.get("api_visible_baseline_matched_claimed") is True
                and receipt.get("journal_recorded_mutation_outcomes") ==
                {"recorded": 58, "http_200": 38, "http_denied": 20, "unknown_or_pending": 0, "other": 0})
    require(not claim or complete)
    unsigned = {k: v for k, v in receipt.items() if k != "binding_digest"}
    encoded = json.dumps({"domain": "PRP_S63_S5_ADVISORY_V1", "evidence": unsigned},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    require(receipt.get("binding_digest") == "sha256:" + hashlib.sha256(encoded).hexdigest())
    return "offline_claim_complete" if claim else "offline_claim_incomplete"


def unavailable(reason="invalid"):
    return {"fresh": False, "reason": reason, "authority": "offline_unverified",
            "runtime_verified": False, "deployment_authorized": False, "live_verified": False}


def project(raw, now):
    """Validate supplied API-shaped pages and claims, suppress all values on bad evidence."""
    try:
        now = epoch(now)
        data = parse(raw)
        exact(data, {"expected_sha", "observed_at", "run_pages", "job_pages", "release", "regression"})
        commit = sha(data["expected_sha"])
        observed = epoch(data["observed_at"])
        age = now - observed
        if age >= TTL:
            return unavailable("stale")
        if age < -FUTURE:
            return unavailable("future")
        runs = pages(data["run_pages"], "workflow_runs", now, observed)
        require(bool(runs))
        for row in runs:
            require(row.get("path") == WORKFLOW and sha(row.get("head_sha")) == commit
                    and row.get("repository", {}).get("full_name") == REPO
                    and row.get("head_repository", {}).get("full_name") == REPO)
            integer(row.get("run_attempt"))
            require(stamp(row.get("created_at")) <= stamp(row.get("updated_at")) <= now + FUTURE)
        selected = max(runs, key=lambda row: (stamp(row["created_at"]), row["id"]))
        run_state = state(selected)
        rows = pages(data["job_pages"], "jobs", now, observed)
        require(bool(rows))
        counts = {k: Counter() for k in ("all", "mcp")}
        durations = {k: 0 for k in counts}
        found = set()
        run_created = stamp(selected["created_at"])
        for row in rows:
            require(integer(row.get("run_id")) == selected["id"]
                    and integer(row.get("run_attempt")) == selected["run_attempt"]
                    and sha(row.get("head_sha")) == commit)
            mcp = group(row.get("name"))
            if mcp:
                found.add(mcp)
            st = state(row)
            duration = 0
            start, end = row.get("started_at"), row.get("completed_at")
            if row.get("status") == "completed" and start is not None and end is not None:
                t1, t2 = stamp(start), stamp(end)
                require(run_created <= t1 <= t2 <= now + FUTURE)
                duration = t2 - t1
            elif row.get("status") == "completed" and st not in ("skipped", "cancelled", "unknown"):
                require(False)
            elif row.get("status") != "completed":
                require(end is None)
                if start is not None:
                    require(run_created <= stamp(start) <= now + FUTURE)
            for g in ("all", "mcp") if mcp else ("all",):
                counts[g][st] += 1
                durations[g] += duration
        require(found == set(MCP_GROUPS))
        # Inconsistency never promotes a workflow to green.
        if run_state == "success" and any(counts["all"][k] for k in STATES if k not in ("success", "skipped", "neutral")):
            run_state = "unknown"
        release_state = "missing"
        if data["release"] is not None:
            release = data["release"]
            exact(release, {"commit", "checks", "publication_hold", "deployed_commit"})
            require(sha(release["commit"]) == commit)
            exact(release["checks"], CHECKS)
            # A synthetic run assertion cannot override failures or imply deployment.
            expected_ci = ("pass" if run_state == "success" and counts["all"]["success"] == len(rows) else "fail" if run_state in
                           ("failure", "timed_out", "startup_failure") else "pending")
            require(release["checks"]["ci"] == expected_ci)
            result = evaluate(release)
            require(result["release_eligible"] is False and result["live_verified"] is False
                    and result["deployment_authorized"] is False and result["state"] in RELEASE_STATES)
            release_state = result["state"]
        regression = regression_claim(data["regression"], commit, now)
        return {"fresh": True, "age_seconds": max(0, age),
                "run_age_seconds": max(0, now - stamp(selected["updated_at"])),
                "run_state": run_state, "jobs": {g: {k: counts[g][k] for k in STATES} for g in counts},
                "duration_seconds": durations, "release_state_claim": release_state,
                "regression_claim": regression, "authority": "offline_unverified",
                "runtime_verified": False, "deployment_authorized": False, "live_verified": False}
    except EvidenceUnavailable as exc:
        return unavailable(str(exc))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError, OSError):
        return unavailable()


def prometheus(raw, now):
    """Only fixed label values and numbers; no input strings, IDs, or secrets."""
    value = project(raw, now)
    lines = ["# TYPE prp_ci_projection_fresh gauge",
             "prp_ci_projection_fresh " + ("1" if value["fresh"] else "0")]
    reason = "fresh" if value["fresh"] else value["reason"]
    for st in PROJECTION_STATES:
        lines.append('prp_ci_projection_state{state="' + st + '"} ' + str(int(reason == st)))
    if not value["fresh"]:
        return "\n".join(lines) + "\n"
    lines += ["prp_ci_snapshot_age_seconds " + str(value["age_seconds"]),
              "prp_ci_run_age_seconds " + str(value["run_age_seconds"])]
    for st in STATES:
        lines.append('prp_ci_run_state{state="' + st + '"} ' + str(int(value["run_state"] == st)))
    for g in ("all", "mcp"):
        for st in STATES:
            lines.append('prp_ci_jobs{group="' + g + '",state="' + st + '"} ' + str(value["jobs"][g][st]))
        lines.append('prp_ci_completed_job_duration_seconds{group="' + g + '"} ' + str(value["duration_seconds"][g]))
    for st in RELEASE_STATES + ("missing",):
        lines.append('prp_ci_release_state_claim{state="' + st + '"} ' + str(int(value["release_state_claim"] == st)))
    for st in ("missing", "offline_claim_complete", "offline_claim_incomplete"):
        lines.append('prp_ci_regression_claim{state="' + st + '"} ' + str(int(value["regression_claim"] == st)))
    return "\n".join(lines) + "\n"
