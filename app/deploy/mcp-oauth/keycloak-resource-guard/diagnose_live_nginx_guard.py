#!/usr/bin/env python3
"""Read-only B2 guard-only Nginx pair classification; never an approval gate.

Use only after the separately trusted verify_guard_release_gate.py
--evidence-only reports PASS. This diagnostic NEVER installs, reloads,
rewrites or approves anything; Nginx -T output and stderr are not printed.
"""
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path("/root/prp-mcp-cimd-stage-b")
GUARD = ROOT / "host-guard"
CONFIG_DIR = Path("/etc/nginx/conf.d")
KNOWN_ROLLBACK = {
    "micor.top.conf": "ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b",
    "prp-mcp-test.conf": "be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d",
}
CANDIDATES = {
    "micor.top.conf": "micor.top.candidate.conf",
    "prp-mcp-test.conf": "prp-test.guard-only.conf",
}


def sha_safe(path):
    """Hash known regular non-symlink files, never disclose their contents."""
    try:
        meta = path.lstat()
        if not stat.S_ISREG(meta.st_mode):
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for piece in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(piece)
        return digest.hexdigest()
    except (OSError, PermissionError):
        return None


def classify(root=ROOT, conf_dir=CONFIG_DIR, nginx_run=None):
    if nginx_run is None:
        nginx_run = subprocess.run
    # No positive authorization result is possible from this diagnostic.
    result = {
        "diagnostic_only": True,
        "guard_install_authorized": False,
        "b2_cutover_authorized": False,
        "production_change_performed": False,
        "candidate_manifest": "UNVERIFIED",
        "nginx_config_inventory": "NOT_CHECKED",
        "files": {},
        "pair_state": "UNKNOWN_NO_INSTALL_DECISION",
    }
    parent = root / "host-guard"
    manifest_path = parent / "candidate-manifest.safe.json"
    try:
        if parent.is_symlink() or not parent.is_dir() or manifest_path.is_symlink():
            result["candidate_manifest"] = "UNSAFE_PATH"
            return result
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(manifest, dict)
        candidates = manifest.get("candidates")
        sources = manifest.get("source_hashes")
        assert isinstance(candidates, dict) and isinstance(sources, dict)
        assert all(isinstance(k, str) and isinstance(v, str)
                   for k, v in sources.items())
        assert all(isinstance(candidates.get(n), str)
                   and re.fullmatch(r"[0-9a-f]{64}", candidates[n])
                   for n in CANDIDATES.values())
        result["candidate_manifest"] = "PARSED_UNVERIFIED"
    except (OSError, ValueError, UnicodeError, AssertionError, TypeError):
        result["candidate_manifest"] = "MISSING_OR_INVALID"
        return result

    states = {}
    for name, candidate_file in CANDIDATES.items():
        actual = sha_safe(conf_dir / name)
        expected = candidates[candidate_file]
        candidate_actual = sha_safe(parent / candidate_file)
        if actual is None:
            state = "MISSING_OR_NOT_REGULAR"
        elif actual == expected:
            state = "GUARD_ONLY_CANDIDATE"
        elif actual == KNOWN_ROLLBACK[name]:
            state = "KNOWN_ROLLBACK_BASELINE"
        else:
            state = "UNRECOGNIZED_DRIFT"
        states[name] = state
        result["files"][name] = {
            "active_state": state,
            "candidate_matches_manifest": candidate_actual == expected,
            "active_sha256": actual if state == "UNRECOGNIZED_DRIFT" else None,
        }

    try:
        # Capture entirely in memory. Never print nginx -T stdout/stderr:
        # either can contain active secrets and sensitive configuration.
        inspected = nginx_run(["nginx", "-T"], capture_output=True,
                               timeout=15, check=False)
        if inspected.returncode == 0:
            inventory = re.findall(
                r"^# configuration file (.+):$",
                inspected.stdout.decode("utf-8", errors="replace"), re.M)
            expected = list(sources)
            expected.append(str(conf_dir / "micor.top.conf"))
            expected.append(str(conf_dir / "prp-mcp-test.conf"))
            if inventory == expected:
                result["nginx_config_inventory"] = "ORDER_AND_PATHS_MATCH_MANIFEST"
            else:
                result["nginx_config_inventory"] = "INVENTORY_OR_ORDER_DRIFT"
                result["expected_inventory_count"] = len(expected)
                result["observed_inventory_count"] = len(inventory)
        else:
            result["nginx_config_inventory"] = "NGINX_TEST_FAILED"
    except (OSError, TimeoutError, subprocess.TimeoutExpired):
        result["nginx_config_inventory"] = "NGINX_TEST_UNAVAILABLE"

    versions = set(states.values())
    if versions == {"GUARD_ONLY_CANDIDATE"}:
        result["pair_state"] = "CANDIDATE_PAIR_MATCHES_HASHES"
    elif versions == {"KNOWN_ROLLBACK_BASELINE"}:
        result["pair_state"] = "KNOWN_ROLLBACK_PAIR"
    elif versions <= {"GUARD_ONLY_CANDIDATE", "KNOWN_ROLLBACK_BASELINE"}:
        result["pair_state"] = "MIXED_KNOWN_VERSIONS"
    else:
        result["pair_state"] = "UNRECOGNIZED_OR_INCOMPLETE"

    # Even exact matching hashes are insufficient without public acceptance,
    # provenance, explicit approval, and original independent B2 gate.
    result["guard_install_authorized"] = False
    result["b2_cutover_authorized"] = False
    return result


if __name__ == "__main__":
    print(json.dumps(classify(), indent=2, sort_keys=True))
