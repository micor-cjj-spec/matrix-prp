#!/usr/bin/env python3
"""Read-only hosted OAuth/OIDC preflight for PRP MCP, no secrets or mutations.

Metadata-only assessment does NOT prove RFC 8707 resource behavior,
issuer-side client registration policy, refresh issuance or end-to-end login.
Those require a real browser/PKCE test with an issued signed bearer.
"""
import argparse
import json
from urllib.parse import urlsplit

from check_metadata import validate, public_get_json

SUPPORTED_AUTH_METHODS = frozenset((
    "none", "client_secret_post", "client_secret_basic", "private_key_jwt",
))
CIMD_AUTH_METHODS = frozenset(("none", "private_key_jwt"))


def _list_of_strings(obj, key):
    value = obj.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Malformed OIDC discovery field: " + key)
    return set(value)


def assess(issuer, resource, mode, fetch, *, registered_client_id=None):
    """Assess live or fixture OIDC metadata without registering a client.

    This intentionally returns metadata_only even when every static gate
    passes. A signed resource-bound user token and real client-registration
    acceptance cannot be established by OIDC discovery metadata alone.
    """
    if mode not in ("cimd", "dcr", "provided"):
        raise ValueError("Client registration mode must be cimd, dcr or provided")
    if not isinstance(issuer, str) or not isinstance(resource, str):
        raise ValueError("Explicit issuer and resource required")
    parsed = urlsplit(issuer)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.port not in (None, 443)):
        raise ValueError("Issuer must be exact HTTPS URL without query, userinfo or fragment")
    parsed_resource = urlsplit(resource)
    if (parsed_resource.scheme != "https" or not parsed_resource.hostname or
            parsed_resource.username or parsed_resource.password or
            parsed_resource.port not in (None, 443) or parsed_resource.query or
            parsed_resource.fragment or parsed_resource.path != "/api/mcp"):
        raise ValueError("Protected resource must be exact https://<host>/api/mcp")
    # Preserve the trailing slash of an issuer. Auth0 signs 'iss' with it.
    base = validate(issuer, resource, fetch)
    discovery = fetch(issuer.rstrip("/") + "/.well-known/openid-configuration")
    methods = _list_of_strings(discovery, "token_endpoint_auth_methods_supported")
    if not methods or not methods.intersection(SUPPORTED_AUTH_METHODS):
        raise ValueError("Provider does not advertise a supported token endpoint authentication method")
    scopes = _list_of_strings(discovery, "scopes_supported")
    grant_types = _list_of_strings(discovery, "grant_types_supported")
    if mode == "dcr":
        registration = discovery.get("registration_endpoint")
        if not isinstance(registration, str) or urlsplit(registration).scheme != "https":
            raise ValueError("DCR requires a published HTTPS registration_endpoint")
    elif mode == "cimd":
        if discovery.get("client_id_metadata_document_supported") is not True:
            raise ValueError("CIMD requires explicit issuer metadata support")
        if not methods.intersection(CIMD_AUTH_METHODS):
            raise ValueError("CIMD requires none or private_key_jwt token authentication")
    else:
        if (not isinstance(registered_client_id, str) or not registered_client_id or
                len(registered_client_id) > 128 or any(c.isspace() for c in registered_client_id)):
            raise ValueError("Pre-registered OAuth client ID is required for provided mode")

    warnings = [
        "Real signed user token with exact MCP resource aud, client ID, scope and sub not yet checked",
        "RFC 8707 resource forwarding and issuer-side client registration/redirect policy not verified",
        "Do not enable PRP MCP or merge/deploy based on metadata-only checks",
    ]
    refresh_advertised = ("refresh_token" in grant_types and "offline_access" in scopes)
    if not refresh_advertised:
        warnings.append("offline_access/refresh_token support not advertised; long-lived sessions need review")
    if issuer.endswith("/"):
        warnings.append("Issuer has a trailing slash: preserve it exactly in PRP config and JWT iss")
    if "auth0.com" in (parsed.hostname or "").lower():
        warnings.append("Auth0: enable Resource Parameter Compatibility Profile; verify issued aud and token scope")
    return {
        "phase": "metadata_only",
        "ready_for_production": False,
        "issuer": base["issuer"],
        "resource": base["resource"],
        "pkce_s256": base["pkce_s256"],
        "registration_mode": mode,
        "client_registration_discovery": "advertised" if base["client_registration_advertised"] else "not_advertised",
        "refresh_advertised": refresh_advertised,
        "token_endpoint_methods": sorted(methods.intersection(SUPPORTED_AUTH_METHODS)),
        "real_user_token_verified": False,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only hosted OAuth preflight for PRP MCP")
    parser.add_argument("--issuer", required=True, help="Exact issuer including any terminal slash")
    parser.add_argument("--resource", required=True, help="Exact HTTPS public PRP /api/mcp URL")
    parser.add_argument("--client-mode", required=True, choices=("cimd", "dcr", "provided"))
    parser.add_argument("--registered-client-id", help="Required with --client-mode provided")
    args = parser.parse_args()
    report = assess(args.issuer, args.resource, args.client_mode, public_get_json,
                    registered_client_id=args.registered_client_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("NOTE: This is discovery-only. No login, refresh grant, PKCE token, client registration or write performed.")


if __name__ == "__main__":
    main()
