"""#218 offline-only shared preflight: Node plan -> Python Realm candidate.

Reads a non-secret JSON plan and spawns only the existing local Node validator.
No network, Keycloak, Docker, database, OAuth grant, or output artifact.
Passing cannot be interpreted as G0/B2, staging, or deployment approval.
"""
import json
from pathlib import Path
import subprocess
import sys

from review_realm import READ_SCOPES, REALM, build_review_video_candidate
from review_exact_clients import review_package, validate_proposals


NODE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcp218-canary-plan.mjs"
NODE_OK = "MCP218_PLAN_SHAPE_PASS_ONLY_NO_DEPLOY_AUTHORIZATION"
PASS = "MCP218_OFFLINE_CONTRACT_PASS_ONLY_NO_DEPLOY_AUTHORIZATION"
MAX_PLAN_BYTES = 65536


def check_contract(path):
    """Return a fixed, non-sensitive failure code or None for static success."""
    try:
        plan_file = Path(path)
        if not plan_file.is_file() or plan_file.stat().st_size > MAX_PLAN_BYTES:
            return "PLAN_UNREADABLE_OR_TOO_LARGE"
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        return "PLAN_UNREADABLE_OR_TOO_LARGE"

    # Reuse the same validator as CI instead of reimplementing its rules.
    # All output is captured and deliberately never echoed (even on failure).
    try:
        node_result = subprocess.run(
            ["node", str(NODE_SCRIPT), str(plan_file)],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "PLAN_VALIDATOR_UNAVAILABLE"
    if (node_result.returncode != 0 or node_result.stdout.strip() != NODE_OK
            or node_result.stderr.strip()):
        return "PLAN_SHAPE_REJECTED"

    try:
        # The JS plan guard has already rejected non-object payloads,
        # unknown fields, extra scopes, write flags and shared resources.
        resource = plan["resource_url"]
        realm = build_review_video_candidate(resource)
        clients = realm["clients"]
        scopes = realm["clientScopes"]
        if (realm["realm"] != REALM or len(clients) != 1
                or clients[0].get("clientId") != "matrix-prp-mcp218-resource"
                or clients[0].get("attributes", {}).get("resource_url") != resource
                or clients[0].get("bearerOnly") is not True
                or len(scopes) != 1 + len(READ_SCOPES)
                or scopes[0]["name"] != "basic"
                or {s["name"] for s in scopes[1:]} != set(plan["advertised_scopes"])
                or {s["name"] for s in scopes[1:]} != set(READ_SCOPES)
                or "users" in realm
                or any("credentials" in client or "secret" in client for client in clients)):
            return "REALM_PLAN_CONTRACT_MISMATCH"
    except (LookupError, TypeError, ValueError, AttributeError):
        return "REALM_PLAN_CONTRACT_MISMATCH"

    # The exact login clients are *review candidates*, not part of the Realm
    # import. Tie them to the SAME plan's issuer/resource and keep synthetic
    # owners unallocated. Never emit the candidate or its input to logs.
    try:
        issuer = plan["issuer_url"]
        proposal = review_package(resource, issuer)
        owner = proposal["synthetic_owner_plan"]
        if (proposal["realm"] != REALM or
                proposal["resource"] != resource or
                proposal["issuer"] != issuer or
                proposal["deployable"] is not False or
                proposal["not_a_keycloak_import"] is not True or
                proposal["not_a_release_receipt"] is not True or
                validate_proposals(proposal["proposed_clients"], resource, issuer) is not True or
                owner["actual_user_ids"] != "NOT_ALLOCATED" or
                owner["expanded_user_ids_setting"] != "NOT_CONFIGURED" or
                owner["owner_client_grants"] != "NOT_GRANTED" or
                set(owner["required_read_scopes"]) != set(READ_SCOPES)):
            return "CLIENT_PLAN_CONTRACT_MISMATCH"
    except (LookupError, TypeError, ValueError, AttributeError):
        return "CLIENT_PLAN_CONTRACT_MISMATCH"
    return None


def main(args=None):
    arguments = sys.argv[1:] if args is None else args
    if len(arguments) != 1:
        print("MCP218_OFFLINE_CONTRACT_NO_GO EXACT_PLAN_PATH_REQUIRED")
        return 2
    failure = check_contract(arguments[0])
    if failure:
        print("MCP218_OFFLINE_CONTRACT_NO_GO " + failure)
        return 2
    print(PASS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
