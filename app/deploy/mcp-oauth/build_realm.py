#!/usr/bin/env python3
"""Generate an isolated Keycloak realm with the exact MCP resource URI.

This does not deploy Keycloak or configure an external MCP OAuth client.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def canonical_resource(value):
    if not isinstance(value, str):
        raise ValueError("Explicit HTTPS MCP resource URL is required")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment
            or not parsed.path.endswith("/api/mcp") or "//" in parsed.path
            or "/../" in parsed.path or "/./" in parsed.path):
        raise ValueError("MCP resource must be an exact HTTPS URL ending in /api/mcp")
    return value


def staging_redirect_uri(value):
    parsed = urlsplit(value)
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Redirect must have an explicit trusted host")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("Staging redirect must be HTTPS or an explicit loopback HTTP URI")
    if parsed.query or not parsed.path.startswith("/") or "*" in value or "//" in parsed.path:
        raise ValueError("Redirect URI must be exact, with no query or wildcard")
    return value


MCP_SCOPES = (
    "prp.tasks.read", "prp.finance.read", "prp.wellness.read",
    "prp.write.create", "prp.write.status", "prp.write.confirm",
)


def build_realm(resource, template=None, *, staging_client_id=None, staging_redirect=None):
    resource = canonical_resource(resource)
    base = json.loads((template or ROOT / "realm/prp-mcp-realm.json").read_text(encoding="utf-8"))
    if base.get("realm") != "prp-mcp" or not base.get("enabled"):
        raise ValueError("Unexpected Keycloak realm template")
    if base.get("clients"):
        raise ValueError("Template must not pre-register arbitrary clients")
    base["clients"] = [{
        "clientId": "matrix-prp-mcp-resource",
        "name": "Matrix PRP MCP Protected Resource",
        "enabled": True,
        "protocol": "openid-connect",
        "bearerOnly": True,
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "attributes": {
            "resource_url": resource
        }
    }]
    # These are optional, consent-visible scopes. A client gets none unless
    # a requested scope is explicitly assigned to that OAuth client.
    # Explicit clientScopes in a Keycloak realm import replace the realm
    # built-in scope defaults. Keycloak 25+ no longer always adds 'sub' to
    # access tokens automatically; its Subject mapper belongs to 'basic'.
    # Include this built-in-equivalent scope explicitly so PKCE browser tokens
    # have a stable signed issuer+subject for PRP identity linking.
    basic_scope = {
        "name": "basic",
        "description": "OIDC subject identity for PKCE bearer tokens",
        "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": "false",
            "display.on.consent.screen": "false",
        },
        "protocolMappers": [{
            "name": "Subject (sub)",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-sub-mapper",
            "consentRequired": False,
            "config": {
                "access.token.claim": "true",
                "introspection.token.claim": "true",
                "lightweight.claim": "false",
            },
        }],
    }
    base["clientScopes"] = [basic_scope] + [{
        "name": scope,
        "description": "PRP MCP permission: " + scope,
        "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": "true",
            "display.on.consent.screen": "true",
            "consent.screen.text": scope,
        },
    } for scope in MCP_SCOPES]
    if (staging_client_id is None) != (staging_redirect is None):
        raise ValueError("Staging client ID and redirect URI must both be provided")
    if staging_client_id is not None:
        if not (2 <= len(staging_client_id) <= 128 and
                staging_client_id[0].isalnum() and
                all(ch.isalnum() or ch in "._~-" for ch in staging_client_id)):
            raise ValueError("Invalid staging OAuth client ID")
        staging_redirect_uri(staging_redirect)
        # Explicit, read-only client for isolated browser PKCE testing only.
        # Never register ChatGPT or any unknown third-party redirect by default.
        base["clients"].append({
            "clientId": staging_client_id,
            "name": "PRP OAuth PKCE Staging Probe",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": True,
            "consentRequired": True,
            "standardFlowEnabled": True,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
            "redirectUris": [staging_redirect],
            "webOrigins": [],
            "attributes": {
                "pkce.code.challenge.method": "S256",
                "oauth2.device.authorization.grant.enabled": "false",
            },
            # Keycloak 25+ attaches the 'sub' (Subject) access-token
            # mapper via the built-in 'basic' default client scope.
            # Without it, a browser login can succeed while the bearer
            # has no signed subject and PRP MUST reject account linking.
            "defaultClientScopes": ["basic"],
            "optionalClientScopes": ["prp.tasks.read"],
            "protocolMappers": [{
                "name": "PRP MCP Resource Audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.client.audience": "matrix-prp-mcp-resource",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                },
            }],
        })
    return base


def main():
    parser = argparse.ArgumentParser(description="Build reviewed Keycloak MCP resource realm")
    parser.add_argument("--resource", required=True, help="Exact HTTPS URI published by PRP MCP")
    parser.add_argument("--output", default=str(ROOT / ".generated/realm/prp-mcp-realm.json"),
                        help="Destination JSON for Keycloak first-time import")
    parser.add_argument("--staging-client-id",
                        help="Optional exact ID of an isolated read-only OAuth PKCE test client")
    parser.add_argument("--staging-redirect",
                        help="Exact HTTPS or localhost callback URL for the staging PKCE client")
    options = parser.parse_args()
    result = build_realm(options.resource, staging_client_id=options.staging_client_id,
                         staging_redirect=options.staging_redirect)
    target = Path(options.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit("Refusing to overwrite existing Keycloak realm import; review state first")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {target}; contains one protected-resource client and NO OAuth login clients.")
    print("First-import only. Register actual OAuth clients/scopes and audience after admin review.")


if __name__ == "__main__":
    main()
