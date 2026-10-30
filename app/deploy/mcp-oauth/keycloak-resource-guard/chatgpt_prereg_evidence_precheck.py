#!/usr/bin/env python3
"""Fail-closed, read-only SQL evidence checks for a Keycloak prp-mcp Realm.

Input is deliberately a *small operator-supplied JSON document*, not a DB
connection. The tool never reads credentials, invokes Docker or Keycloak Admin
API, and never authorizes deployment. The operator must collect the two
counts with read-only SQL separately. Do not place user records or secrets in
the input document.

Example input:
{"realm":"prp-mcp","client_count":13,"chatgpt_client_count":0,
 "backup_restore_passed":true,"restore_realm_client_count":13,
 "restore_chatgpt_client_count":0,"independent_b2_approval":false}
"""
import argparse
import json
import sys
from pathlib import Path

EXPECTED_REALM = "prp-mcp"
EXPECTED_CLIENT = "https://chatgpt.com/oauth/client.json"
MAX_BYTES = 4096
REQUIRED = {
    "realm", "client_count", "chatgpt_client_count",
    "backup_restore_passed", "restore_realm_client_count",
    "restore_chatgpt_client_count", "independent_b2_approval",
}


def evaluate(data):
    if not isinstance(data, dict) or set(data) != REQUIRED:
        raise ValueError("INVALID_EVIDENCE_FIELDS")
    if data["realm"] != EXPECTED_REALM:
        raise ValueError("REALM_MISMATCH")
    for key in ("client_count", "chatgpt_client_count",
                "restore_realm_client_count", "restore_chatgpt_client_count"):
        if type(data[key]) is not int or data[key] < 0:
            raise ValueError("INVALID_COUNT_" + key.upper())
    if type(data["backup_restore_passed"]) is not bool:
        raise ValueError("INVALID_RESTORE_STATUS")
    if type(data["independent_b2_approval"]) is not bool:
        raise ValueError("INVALID_APPROVAL_STATUS")
    findings = []
    if data["client_count"] != 13:
        findings.append("LIVE_CLIENT_COUNT_REVIEW_REQUIRED")
    if data["chatgpt_client_count"] != 0:
        findings.append("EXACT_CLIENT_ALREADY_EXISTS_OR_DUPLICATED")
    if not data["backup_restore_passed"]:
        findings.append("RESTORE_NOT_PROVEN")
    if data["restore_realm_client_count"] != 13:
        findings.append("RESTORE_REALM_COUNT_REVIEW_REQUIRED")
    if data["restore_chatgpt_client_count"] != 0:
        findings.append("RESTORE_EXACT_CLIENT_UNEXPECTED")
    if not data["independent_b2_approval"]:
        findings.append("INDEPENDENT_APPROVAL_MISSING")
    # A project-owner authorization statement is distinct from independent B2
    # recovery acceptance; do not conflate either with deployment permission.
    # This diagnostic is never an approval source, even if supplied booleans
    # appear favorable. The real B2 authority remains external to this tool.
    return {
        "diagnostic_only": True,
        "exact_client_id": EXPECTED_CLIENT,
        "findings": findings,
        "evidence_consistency": "MATCHES_RECORDED_BASELINE" if not any(
            x for x in findings if x != "INDEPENDENT_APPROVAL_MISSING"
        ) else "REVIEW_REQUIRED",
        "deployment_permitted": False,
        "b2_authorization": "BLOCKED_UNTIL_INDEPENDENT_REVIEW",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_json", type=Path)
    args = parser.parse_args()
    if not args.evidence_json.is_file() or args.evidence_json.stat().st_size > MAX_BYTES:
        parser.error("MISSING_OR_OVERSIZE_EVIDENCE")
    try:
        evidence = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        result = evaluate(evidence)
    except (ValueError, UnicodeError, OSError) as exc:
        print("PRECHECK=FAIL " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["evidence_consistency"] == "MATCHES_RECORDED_BASELINE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
