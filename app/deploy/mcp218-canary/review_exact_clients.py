"""#218 isolated OAuth exact-client review candidates — NEVER an install bundle.

Pure in-memory proposals for human security review only. No files, network,
Keycloak Admin, users, passwords, client secrets, scopes granted, or deployment.
The existing V2 `prp-mcp` Realm and its grants must remain untouched.
"""
from copy import deepcopy
import re
from urllib.parse import urlsplit

from review_realm import READ_SCOPES, REALM, _exact_candidate_resource

CHATGPT_ID = "https://chatgpt.com/oauth/client.json"
CHATGPT_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
CHATGPT_JWKS = "https://chatgpt.com/oauth/jwks.json"
# The shipped PRP SPA rejects any other client_id in checkedFirstPartyAuthorizeUrl.
# Reusing the *identifier* in a separate, uninstalled Realm is safe: issuer,
# client registration, signing keys and redirect origin remain isolated.
# Never reuse the actual V2 Keycloak client or its owner grants.
FIRST_PARTY_ID = "prp-first-party-link"


def _review_issuer(issuer):
    if not isinstance(issuer, str):
        raise ValueError("MCP218_ISSUER_MUST_BE_ISOLATED")
    parsed = urlsplit(issuer)
    host = parsed.hostname
    if (parsed.scheme != "https" or not host or parsed.netloc != host
            or parsed.path != "/" + "realms/" + REALM
            or parsed.query or parsed.fragment
            or issuer != f"https://{host}/realms/{REALM}"):
        raise ValueError("MCP218_ISSUER_MUST_BE_ISOLATED")
    parts = host.split(".")
    if (len(host) > 253 or len(parts) < 2 or
            not parts[0].startswith("auth-mcp218-") or
            parts[0] == "auth-mcp218-" or
            parts[-1] in ("test", "invalid", "example", "localhost", "local") or
            not all(len(part) <= 63 and re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part
            ) for part in parts)):
        raise ValueError("MCP218_ISSUER_MUST_BE_ISOLATED")
    return issuer


def client_proposals(resource, issuer):
    """Return exactly two *non-deployable* review shapes. No registrations."""
    resource = _exact_candidate_resource(resource)
    _review_issuer(issuer)
    base_url = resource.removesuffix("/api/mcp")
    if issuer.startswith(base_url + "/"):
        raise ValueError("MCP218_CLIENT_SHARED_RESOURCE_ISSUER")
    common = {
        "enabled": True,  # proposed eventual client only, NOT environment flag
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
    first_party = {
        **common,
        "clientId": FIRST_PARTY_ID,
        "name": "MCP218 first-party identity link — REVIEW ONLY",
        "publicClient": True,
        "redirectUris": [base_url + "/prp/me/mcp-link/callback"],
        "optionalClientScopes": [],
        "attributes": {"pkce.code.challenge.method": "S256"},
        "protocolMappers": [],
    }
    chatgpt = {
        **common,
        "clientId": CHATGPT_ID,
        "name": "ChatGPT MCP218 review/video read — REVIEW ONLY",
        "publicClient": False,
        "clientAuthenticatorType": "client-jwt",
        "redirectUris": [CHATGPT_REDIRECT],
        "optionalClientScopes": list(READ_SCOPES),
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "use.jwks.url": "true",
            "jwks.url": CHATGPT_JWKS,
        },
        "protocolMappers": [{
            "name": "MCP218 exact read-only resource audience",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.custom.audience": resource,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        }],
    }
    return [first_party, chatgpt]


def validate_proposals(candidates, resource, issuer):
    """Fail closed against silent scope, redirect or client-shape broadening."""
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ValueError("MCP218_CLIENT_REVIEW_SHAPE_CHANGED")
    expected = client_proposals(resource, issuer)
    if (candidates != expected or
            {c.get("clientId") for c in candidates if isinstance(c, dict)}
            != {FIRST_PARTY_ID, CHATGPT_ID}):
        raise ValueError("MCP218_CLIENT_REVIEW_SHAPE_CHANGED")
    return True


def review_package(resource, issuer):
    """Not a Keycloak import: refuse to conflate this with real client consent."""
    proposals = client_proposals(resource, issuer)
    validate_proposals(proposals, resource, issuer)
    return {
        "status": "PENDING_INDEPENDENT_G0_B2_AND_ACTUAL_TARGET_REVIEW",
        "deployable": False,
        "not_a_keycloak_import": True,
        "not_a_release_receipt": True,
        "realm": REALM,
        "resource": resource,
        "issuer": issuer,
        "proposed_clients": deepcopy(proposals),
        "synthetic_owner_plan": {
            "labels_only": ["synthetic-owner-A", "synthetic-owner-B"],
            "actual_user_ids": "NOT_ALLOCATED",
            "expanded_user_ids_setting": "NOT_CONFIGURED",
            "owner_client_grants": "NOT_GRANTED",
            "required_read_scopes": list(READ_SCOPES),
        },
        "review_gates": [
            "Verify independent host, DNS, TLS, Realm and recovery authority first.",
            "Independently review exact clients, PKCE S256, JWKS and audience.",
            "Only after approval create two synthetic owners in isolated data.",
            "Set expanded-user-ids to those two verified synthetic user IDs only.",
            "Owner must explicitly consent to the complete client grant scope set.",
            "Test denied third owner, incorrect client, revoked grant, no writes.",
            "Never copy or mutate existing V2 client registrations or grants.",
        ],
    }
