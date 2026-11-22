#!/usr/bin/env python3
"""Pure, offline release-status projection. NEVER authorizes or proves deployment."""
import argparse
import json
from pathlib import Path

STATES = {"pass", "fail", "pending", "skipped"}
CHECKS = ("ci", "staging", "migration", "backup_restore", "approval", "production_smoke")
PRE_PUBLISH_CHECKS = CHECKS[:-1]


def _is_commit(value):
    return isinstance(value, str) and len(value) == 40 and all(
        c in "0123456789abcdef" for c in value
    )


def evaluate(data):
    """Evaluate assertions supplied by a caller, NOT independently verified facts.

    A trusted evidence collector must bind checks, deployed SHA and smoke results
    to the same immutable candidate/run before using any status in a live UI.
    """
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    unknown = set(data) - {"commit", "checks", "publication_hold", "deployed_commit"}
    if unknown:
        raise ValueError("Unexpected keys: " + ", ".join(sorted(unknown)))
    commit = data.get("commit")
    if not _is_commit(commit):
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
    if deployed is not None and not _is_commit(deployed):
        raise ValueError("deployed_commit must be a lowercase 40-character SHA or null")

    blockers = []
    if hold:
        blockers.append("publication_hold")
    blockers += [k for k in PRE_PUBLISH_CHECKS if checks[k] != "pass"]

    # Pending smoke is normal before the first deployment. A known failed or
    # explicitly skipped verification, however, must not appear release-ready.
    smoke = checks["production_smoke"]
    if smoke in ("fail", "skipped"):
        blockers.append("production_smoke")
    if smoke == "pass" and deployed != commit:
        blockers.append("deployed_commit_missing" if deployed is None else "deployed_commit_mismatch")

    eligible = not blockers
    # This is a logical projection only: all six claims come from input JSON.
    # Do not expose this flag as authoritative production verification.
    live = eligible and smoke == "pass" and deployed == commit
    return {
        "schema_version": 1,
        "commit": commit,
        "state": "HELD" if hold else "BLOCKED" if blockers else "LIVE_VERIFIED" if live else "READY_NOT_LIVE",
        "release_eligible": eligible,
        "live_verified": live,
        "evidence_trust": "unverified_caller_assertions",
        "deployment_authorized": False,
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
    print(result["state"] + " (offline, unverified caller assertions; NOT a production release receipt)")


if __name__ == "__main__":
    main()
