#!/usr/bin/env python3
"""NO-WRITE review artifact for two missing PRP MCP OAuth clients.

This script does not log in, connect to Keycloak, mutate the Realm, install
Nginx, issue B2 receipts, or import any Keycloak administrator SDK. Its
output is deliberately NOT a Keycloak realm-import JSON document or an
authorization to perform an Admin REST write.

Based on the repository's separately tested disposable-client configurations.
The reviewer must additionally verify actual active scopes, existing client
policies, native CIMD conflicts, current Realm/user subject compatibility,
public TLS/routes, and independent backup/recovery approvals.
"""
import json

REALM = "prp-mcp"
RESOURCE = "https://prp-test.micor.top/api/mcp"
CHATGPT = "https://chatgpt.com/oauth/client.json"
FIRST_PARTY = "prp-first-party-link"
CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
PRP_CALLBACK = "https://prp-test.micor.top/prp/me/mcp-link/callback"
CHATGPT_JWKS = "https://chatgpt.com/oauth/jwks.json"


def client_proposals():
    """Reviewable create-only candidates; NOT instructions to install."""
    common = {
        "enabled": True,
        "protocol": "openid-connect",
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "fullScopeAllowed": False,
        "consentRequired": True,
        "webOrigins": [],
        "defaultClientScopes": ["basic"],
    }
    first = {
        **common,
        "clientId": FIRST_PARTY,
        "name": "PRP first-party Keycloak identity link — REVIEW ONLY",
        "publicClient": True,
        "redirectUris": [PRP_CALLBACK],
        "optionalClientScopes": [],
        "attributes": {"pkce.code.challenge.method": "S256"},
        "protocolMappers": [],
    }
    chatgpt = {
        **common,
        "clientId": CHATGPT,
        "name": "ChatGPT PRP task read — REVIEW ONLY",
        "publicClient": False,
        "clientAuthenticatorType": "client-jwt",
        "redirectUris": [CHATGPT_CALLBACK],
        "optionalClientScopes": ["prp.tasks.read", "offline_access"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "use.jwks.url": "true",
            "jwks.url": CHATGPT_JWKS,
        },
        "protocolMappers": [{
            "name": "PRP MCP exact audience",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.custom.audience": RESOURCE,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        }],
    }
    return [first, chatgpt]


def validate_proposals(proposals):
    """Fail closed if a candidate is broadened from the reviewed exact form."""
    if not isinstance(proposals, list) or len(proposals) != 2:
        raise ValueError("REVIEW_CLIENT_COUNT_CHANGED")
    expected = client_proposals()
    by_id = {}
    for item in proposals:
        if not isinstance(item, dict) or not isinstance(item.get("clientId"), str):
            raise ValueError("REVIEW_CLIENT_INVALID")
        name = item["clientId"]
        if name in by_id:
            raise ValueError("REVIEW_CLIENT_DUPLICATE")
        by_id[name] = item
    if set(by_id) != {FIRST_PARTY, CHATGPT}:
        raise ValueError("REVIEW_CLIENT_ID_CHANGED")
    for item in expected:
        if by_id[item["clientId"]] != item:
            raise ValueError("REVIEW_CLIENT_SHAPE_CHANGED")
    # None of the proposals can confer application data write privileges.
    for item in proposals:
        if any(s.startswith(("prp.finance.", "prp.wellness.", "prp.write."))
               for s in item["optionalClientScopes"] + item["defaultClientScopes"]):
            raise ValueError("REVIEW_FORBIDDEN_SCOPE")
    return True


def review_package():
    candidates = client_proposals()
    validate_proposals(candidates)
    return {
        "status": "PENDING_INDEPENDENT_G0_AND_B2_APPROVAL",
        "deployable": False,
        "realm": REALM,
        "resource": RESOURCE,
        "purpose": "Review two create-only client additions. No active change permitted.",
        "proposed_clients": candidates,
        "preconditions": [
            "Current test Realm must be independently backed up and recoverable.",
            "Preserve every existing client, policy, profile, mapper and user.",
            "Native CIMD URI interception must be independently reviewed; never silently disable it.",
            "Approve exact Keycloak client/route scope and a reversible G0+B2 change.",
            "Register first-party client and reviewed HTTPS callback only after authorization.",
            "Confirm first-party and ChatGPT token subjects match in actual Realm.",
            "Check real OpenAI private_key_jwt, PKCE S256, resource audience, refresh and revocation.",
            "Require owner-granted prp.tasks.read; finance/wellness and MCP writes remain disabled.",
            "Run real ChatGPT prp_tasks_list with at most 20 owner records before declaring success.",
        ],
        "not_a_keycloak_import": True,
        "not_a_release_receipt": True,
    }


def main():
    # Prints only fixed public metadata and configuration candidates. No
    # contact with the user's credentials, databases, containers or network.
    print(json.dumps(review_package(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
