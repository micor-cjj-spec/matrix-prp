#!/usr/bin/env python3
"""Bounded GET-only, unauthenticated public metadata check for PRP MCP staging.

This is *not* OAuth, login, Keycloak Realm administration, a credential test,
Nginx install acceptance, or B2 recovery verification. It never reads private
records or sends user tokens. Network errors mean UNVERIFIED, not offline.
"""
import json
import socket
import ssl
import urllib.error
import urllib.request

RESOURCE = "https://prp-test.micor.top/api/mcp"
ISSUER = "https://auth-test.micor.top/realms/prp-mcp"
RESOURCE_METADATA = "https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp"
OIDC_DISCOVERY = ISSUER + "/.well-known/openid-configuration"
MAX_BYTES = 65536

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def fetch_json(opener, url):
    request = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "Cache-Control": "no-store",
        "User-Agent": "PRP-MCP-readonly-public-check/1",
    })
    with opener.open(request, timeout=10) as response:
        if response.status != 200:
            raise ValueError("UNEXPECTED_HTTP_STATUS")
        if response.url != url:
            raise ValueError("REDIRECTED")
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("INVALID_CONTENT_TYPE")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    return json.loads(raw, object_pairs_hook=reject_duplicates)

def resource_check(document):
    if not isinstance(document, dict):
        raise ValueError("BAD_RESOURCE_METADATA")
    if document.get("resource") != RESOURCE:
        raise ValueError("RESOURCE_URI_MISMATCH")
    if document.get("authorization_servers") != [ISSUER]:
        raise ValueError("ISSUER_LIST_MISMATCH")
    if document.get("scopes_supported") != ["prp.tasks.read"]:
        raise ValueError("NOT_STRICT_TASK_READ")
    if document.get("bearer_methods_supported") != ["header"]:
        raise ValueError("BEARER_METHOD_MISMATCH")

def oidc_check(document):
    if not isinstance(document, dict):
        raise ValueError("BAD_OIDC_DISCOVERY")
    if document.get("issuer") != ISSUER:
        raise ValueError("ISSUER_MISMATCH")
    methods = document.get("code_challenge_methods_supported")
    if not isinstance(methods, list) or "S256" not in methods:
        raise ValueError("S256_NOT_ADVERTISED")
    token = document.get("token_endpoint")
    if token != ISSUER + "/protocol/openid-connect/token":
        raise ValueError("TOKEN_ENDPOINT_MISMATCH")

def classify(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "HTTP_" + str(exc.code)
    if isinstance(exc, ssl.SSLError):
        return "TLS_UNVERIFIED"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "TIMEOUT_UNVERIFIED"
    if isinstance(exc, urllib.error.URLError):
        text = str(exc.reason).lower()
        if "name or service" in text or "nodename" in text or "no address associated" in text:
            return "DNS_UNVERIFIED"
        if "timed out" in text:
            return "TIMEOUT_UNVERIFIED"
        if "certificate" in text or "ssl" in text or "tls" in text:
            return "TLS_UNVERIFIED"
        return "NETWORK_UNVERIFIED"
    if isinstance(exc, ValueError):
        return str(exc) if len(str(exc)) < 80 else "FORMAT_UNVERIFIED"
    return "UNKNOWN_UNVERIFIED"

def main():
    # Ignore inherited proxy variables and disallow HTTP redirection.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        NoRedirect(),
    )
    cases = [
        ("resource_metadata", RESOURCE_METADATA, resource_check),
        ("oidc_discovery", OIDC_DISCOVERY, oidc_check),
    ]
    failed = False
    for label, url, validator in cases:
        try:
            validator(fetch_json(opener, url))
            print(label + "=PUBLIC_METADATA_VERIFIED")
        except Exception as exc:
            failed = True
            print(label + "=" + classify(exc))
    print("REAL_CHATGPT_OAUTH=NOT_TESTED")
    print("B2_RESTORE=NOT_TESTED")
    print("NGINX_INSTALLED_GUARD=NOT_TESTED")
    print("NO_HOST_CONFIGURATION_CHANGED=true")
    return 2 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
