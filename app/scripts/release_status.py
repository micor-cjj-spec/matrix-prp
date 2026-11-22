#!/usr/bin/env python3
"""Pure, offline release-status gate. Never triggers or authorizes deployment."""
import argparse
import json
from pathlib import Path

STATES = {"pass", "fail", "pending", "skipped"}
CHECKS = ("ci", "staging", "migration", "backup_restore", "approval", "production_smoke")


def evaluate(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    unknown = set(data) - {"commit", "checks", "publication_hold", "deployed_commit"}
    if unknown:
        raise ValueError("Unexpected keys: " + ", ".join(sorted(unknown)))
    commit = data.get("commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("commit must be a lowercase 40-character SHA")
    checks = data.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise ValueError("checks must contain exactly the six required gates")
    if any(type(checks[k]) is not str or checks[k] not in STATES for k in CHECKS):
        raise ValueError("Invalid check status")
    hold = data.get("publication_hold")
    if type(hold) is not bool:
        raise ValueError("publication_hold must be boolean")
    deployed = data.get("deployed_commit")
    if deployed is not None and (not isinstance(deployed, str) or len(deployed) != 40 or any(c not in "0123456789abcdef" for c in deployed)):
        raise ValueError("deployed_commit must be a lowercase 40-character SHA or null")
    blockers = []
    if hold:
        blockers.append("publication_hold")
    blockers += [k for k in CHECKS if k != "production_smoke" and checks[k] != "pass"]
    # A smoke failure is a known failed release check, not a clean preflight.
    # A claimed smoke pass without a matching deployed SHA is contradictory.
    smoke = checks["production_smoke"]
    if smoke == "fail":
        blockers.append("production_smoke")
    elif smoke == "pass" and deployed != commit:
        blockers.append("deployed_commit_mismatch" if deployed is not None else "deployed_commit_missing")
    eligible = not blockers
    # A successful workflow, skipped publish, or user approval alone never establishes LIVE.
    # This is offline evaluation of supplied evidence, NOT trusted proof of deployment.
    live = eligible and smoke == "pass" and deployed == commit
    return {
        "schema_version": 1,
        "commit": commit,
        "state": "LIVE_VERIFIED" if live else "HELD" if hold else "BLOCKED" if blockers else "READY_NOT_LIVE",
        "release_eligible": eligible,
        "live_verified": live,
        "blockers": blockers,
        "deployed_commit": deployed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["state"])


if __name__ == "__main__":
    main()
