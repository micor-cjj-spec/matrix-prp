"""S6 v1 offline review snapshot validation; never a deployment/readiness gate."""
import datetime as dt
import json
from pathlib import Path
import re
import sys

DEFAULT = Path(__file__).with_name("unified-staging-status") / "test-env-status.json"
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
CHECKS = {
    398: {"s0_contract", "full_ci"},
    400: {"compose_static", "disposable_runtime", "full_ci"},
    403: {"disposable_runtime", "full_ci", "ui_synthetic_browser",
          "health_synthetic_browser", "personal_os_synthetic_browser"},
    407: {"disposable_runtime"},
}
VERSIONS = {398: None, 400: 29, 403: 31, 407: 30}
PERSISTENT = {"source_sha", "backend_digest", "web_digest", "flyway_version",
              "flyway_checksums", "last_health_check", "last_owner_isolation_check",
              "last_browser_check", "last_uat_check"}
BLOCKERS = {"host_identity_and_s0_approval", "host_inventory_and_capacity",
            "placement_and_isolation", "exact_candidate_and_image_review",
            "separate_s4_approval", "persistent_https_and_runtime_evidence",
            "synthetic_owner_and_device_uat", "stage_restore_rehearsal"}


def require(condition):
    if not condition:
        raise ValueError("INVALID_REVIEW_SNAPSHOT")


def keys(value, expected):
    require(type(value) is dict and set(value) == expected)


def distinct(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def utc(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value))
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def positive(value):
    return type(value) is int and value > 0


def matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


def validate(data):
    keys(data, {"schema_version", "issue", "observed_at", "status", "scope",
                "repository_baseline", "candidates", "ci_archive",
                "persistent_stage", "gates", "blockers"})
    require(type(data["schema_version"]) is int and data["schema_version"] == 1)
    require(type(data["issue"]) is int and data["issue"] == 396)
    require(data["status"] == "blocked" and data["scope"] == "repository_review_only")
    observed = utc(data["observed_at"])
    require(observed <= dt.datetime.now(dt.timezone.utc))
    keys(data["repository_baseline"], {"main", "dev"})
    require(all(matches(SHA, x) for x in data["repository_baseline"].values()))
    keys(data["persistent_stage"], PERSISTENT)
    require(all(x is None for x in data["persistent_stage"].values()))
    gates = data["gates"]
    checks = {"s0_host_inventory", "s1_placement", "s4_install", "s5_uat"}
    approvals = {"stage_deployment_authorized", "production_authorized", "oauth_mcp_authorized"}
    keys(gates, checks | approvals)
    require(all(gates[x] == "not_run" for x in checks))
    require(all(gates[x] is False for x in approvals))
    require(type(data["blockers"]) is list and len(data["blockers"]) == len(BLOCKERS)
            and all(type(x) is str for x in data["blockers"])
            and set(data["blockers"]) == BLOCKERS)
    candidates = data["candidates"]
    require(type(candidates) is list and len(candidates) == len(CHECKS))
    prs, runs = set(), {}
    for candidate in candidates:
        keys(candidate, {"pr", "pr_head_sha", "expected_flyway", "checks"})
        pr = candidate["pr"]
        require(type(pr) is int and pr in CHECKS and pr not in prs)
        prs.add(pr)
        require(matches(SHA, candidate["pr_head_sha"]))
        version = candidate["expected_flyway"]
        require((version is None if pr == 398 else type(version) is int and version == VERSIONS[pr]))
        entries = candidate["checks"]
        require(type(entries) is list and len(entries) == len(CHECKS[pr]))
        kinds = set()
        for check in entries:
            keys(check, {"kind", "run_id", "attempt", "conclusion"})
            kind = check["kind"]
            require(type(kind) is str and kind in CHECKS[pr] and kind not in kinds)
            kinds.add(kind)
            require(positive(check["run_id"]) and check["run_id"] not in runs)
            require(positive(check["attempt"]) and check["conclusion"] == "success")
            runs[check["run_id"]] = (pr, kind)
    archive = data["ci_archive"]
    keys(archive, {"pr", "run_id", "artifact_id", "archive_digest",
                   "expires_at", "expired_at_observation"})
    require(archive["pr"] == 403 and positive(archive["run_id"])
            and runs.get(archive["run_id"]) == (403, "disposable_runtime"))
    require(positive(archive["artifact_id"]) and matches(DIGEST, archive["archive_digest"]))
    expires = utc(archive["expires_at"])
    require(type(archive["expired_at_observation"]) is bool
            and archive["expired_at_observation"] == (expires <= observed))
    return {"status": "blocked", "snapshot_valid": True,
            "ci_archive_expired_by_clock": expires <= dt.datetime.now(dt.timezone.utc),
            "stage_deployment_authorized": False, "production_authorized": False,
            "persistent_readiness": "not_established"}


def load(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 65536)
    return validate(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=distinct))


def main():
    try:
        require(len(sys.argv) <= 2)
        print(json.dumps(load(sys.argv[1] if len(sys.argv) == 2 else DEFAULT), sort_keys=True))
    except (ValueError, TypeError, OSError, OverflowError):
        print('{"snapshot_valid":false,"status":"blocked","stage_deployment_authorized":false}')
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
