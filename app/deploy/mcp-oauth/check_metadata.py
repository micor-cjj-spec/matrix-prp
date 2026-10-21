#!/usr/bin/env python3
"""Read-only OAuth issuer metadata preflight. Does not authenticate or issue tokens."""
import argparse
import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def https_url(raw, label):
    if not isinstance(raw, str):
        raise ValueError(f"{label}: HTTPS URL required")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError(f"{label}: explicit HTTPS URL without credentials or fragment required")
    return raw.rstrip("/")


def validate(issuer, resource, fetch):
    issuer = https_url(issuer, "issuer")
    https_url(resource, "resource")
    if not urlparse(resource).path:
        raise ValueError("resource: canonical MCP endpoint path required")
    configuration = fetch(issuer + "/.well-known/openid-configuration")
    if configuration.get("issuer") != issuer:
        raise ValueError("issuer metadata mismatch")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        https_url(configuration.get(key), key)
    if "S256" not in configuration.get("code_challenge_methods_supported", []):
        raise ValueError("PKCE S256 is not advertised")
    if "authorization_code" not in configuration.get("grant_types_supported", []):
        raise ValueError("authorization_code is not advertised")
    keys = fetch(configuration["jwks_uri"]).get("keys", [])
    if not isinstance(keys, list) or not any(
        isinstance(key, dict) and key.get("kty") == "RSA" and key.get("n") and key.get("e")
        and key.get("use", "sig") == "sig" and key.get("alg", "RS256") == "RS256"
        for key in keys
    ):
        raise ValueError("No RSA signing key advertised in JWKS")
    return {
        "issuer": issuer,
        "resource": resource,
        "pkce_s256": True,
        "authorization_code": True,
        "public_signing_keys": len(keys),
        "client_registration_advertised": bool(
            configuration.get("registration_endpoint")
            or configuration.get("client_id_metadata_document_supported")
        ),
    }


def public_get_json(uri):
    uri = https_url(uri, "discovery URL")
    request = Request(uri, headers={"Accept": "application/json", "User-Agent": "PRP-MCP-Preflight/1.0"})
    with urlopen(request, timeout=8) as response:
        final_uri = response.geturl()
        https_url(final_uri, "redirect URL")
        if urlparse(final_uri).hostname != urlparse(uri).hostname:
            raise ValueError("Cross-host metadata redirect is forbidden")
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("OAuth metadata exceeds size cap")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("OAuth metadata must be a JSON object")
    return data


def main():
    parser = argparse.ArgumentParser(description="Read-only external OAuth issuer metadata preflight")
    parser.add_argument("--issuer", required=True, help="Exact HTTPS OAuth issuer URI")
    parser.add_argument("--resource", required=True, help="Exact canonical HTTPS PRP MCP resource URI")
    args = parser.parse_args()
    result = validate(args.issuer, args.resource, public_get_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("Metadata-only preflight passed; NOT a token, consent, host or end-to-end authorization test.")


if __name__ == "__main__":
    main()
