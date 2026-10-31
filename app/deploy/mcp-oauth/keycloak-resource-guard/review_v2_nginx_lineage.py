#!/usr/bin/env python3
"""Read-only comparison of the historical B2 guard vhost and active V2 route.

Only aggregate, allowlisted comparison facts are printed. No raw Nginx
configuration, diff fragments or active secrets are printed. Never issues
an approval, constructs a receipt, writes a candidate or reloads Nginx.

An exact port-only normalization is useful evidence of *provenance*, but
does not authorize production or constitute Nginx security acceptance.
"""
import difflib
import hashlib
import json
from pathlib import Path
import stat

ACTIVE = Path("/etc/nginx/conf.d/prp-mcp-test.conf")
GUARD_ONLY = Path("/root/prp-mcp-cimd-stage-b/host-guard/prp-test.guard-only.conf")
B2_CANDIDATE = Path("/root/prp-mcp-cimd-stage-b/host-guard/prp-test.b2-candidate.conf")
HISTORIC_BACKUP = Path(
    "/root/prp-mcp-cimd-stage-b/host-guard/install-backup-20261022T084744Z/prp-mcp-test.conf"
)
EXPECTED = {
    "backup": "be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d",
    "guard_only": "90814118bda4c8ca0be3d87ae36accb003a4be7f593954d552bfe05c1c98e6bd",
    "b2_candidate": "47e428ff7ec46eb03f360cac1369e82f4c7c7795b1d0e2be5de5694364e02d2b",
}
OLD = b"127.0.0.1:18081"
V2 = b"127.0.0.1:18082"


def read_regular(path):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            return None
        return path.read_bytes()
    except OSError:
        return None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def difference_summary(first, second):
    """No config data exposed, only counts of changed line groups."""
    a = first.splitlines()
    b = second.splitlines()
    kinds = {"replace": 0, "insert": 0, "delete": 0}
    counts = {"old_lines_changed": 0, "new_lines_changed": 0}
    for tag, i, j, k, m in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        kinds[tag] += 1
        counts["old_lines_changed"] += j - i
        counts["new_lines_changed"] += m - k
    return {"edit_groups": kinds, **counts}


def inspect(paths=None):
    paths = paths or {
        "active": ACTIVE, "backup": HISTORIC_BACKUP,
        "guard_only": GUARD_ONLY, "b2_candidate": B2_CANDIDATE
    }
    result = {
        "diagnostic_only": True,
        "no_config_content_printed": True,
        "no_write_or_reload": True,
        "guard_only_install_approved": False,
        "b2_cutover_approved": False,
        "source_integrity": {},
        "route_counts": {},
        "active_vs_backup": "NOT_CHECKED",
        "normalized_active_matches_historical_backup": False,
        "guard_v2_review_only_projection_sha256": None,
    }
    content = {name: read_regular(path) for name, path in paths.items()}
    if any(value is None for value in content.values()):
        result["status"] = "MISSING_UNSAFE_OR_OVERSIZE_SOURCE"
        return result

    for name, raw in content.items():
        if name in EXPECTED:
            result["source_integrity"][name] = (
                "PINNED_SHA256_MATCH" if sha(raw) == EXPECTED[name] else "PINNED_SHA256_MISMATCH"
            )
        result["route_counts"][name] = {
            "old_18081": raw.count(OLD), "v2_18082": raw.count(V2),
            "mcp_path": b"/api/mcp" in raw,
            "resource_metadata_path":
                b"/.well-known/oauth-protected-resource/api/mcp" in raw,
        }
    result["active_sha256"] = sha(content["active"])
    if any(value != "PINNED_SHA256_MATCH"
           for value in result["source_integrity"].values()):
        result["status"] = "HISTORIC_SOURCE_DRIFT_REFUSE_PROJECTION"
        return result

    active, original = content["active"], content["backup"]
    result["active_vs_backup"] = difference_summary(original, active)
    # Only this EXACT byte replacement can count as a port-only change.
    result["normalized_active_matches_historical_backup"] = (
        active.count(V2) == original.count(OLD)
        and active.count(OLD) == 0
        and active.replace(V2, OLD) == original
    )

    # A *hash in memory*, not a candidate manifest, installation artifact,
    # or validated Nginx config. This is not output as an approval receipt.
    guard = content["guard_only"]
    if (guard.count(OLD) == 2 and V2 not in guard):
        result["guard_v2_review_only_projection_sha256"] = sha(guard.replace(OLD, V2))
        result["guard_v2_projection_status"] = "HYPOTHETICAL_NOT_TESTED_OR_APPROVED"
    else:
        result["guard_v2_projection_status"] = "BASELINE_UNEXPECTED_NO_PROJECTION"

    result["status"] = (
        "ACTIVE_PORT_ONLY_CHANGE_FROM_PINNED_BACKUP"
        if result["normalized_active_matches_historical_backup"]
        else "ACTIVE_HAS_ADDITIONAL_DIFFS_REVIEW_REQUIRED"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2, sort_keys=True))
