#!/usr/bin/env python3
"""External, GET-only, fixed-URL PRP MCP staging metadata diagnostic.

No OAuth callback, token, authorization request, POST, MCP tool call,
admin API, credentials, redirect, proxy, DNS override or deployment action.
Observed public metadata is not an approval to change B2 or production.
"""
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

RESOURCE = "https://prp-test.micor.top/api/mcp"
RESOURCE_METADATA = "https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp"
ISSUER = "https://auth-test.micor.top/realms/prp-mcp"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
JWKS = ISSUER + "/protocol/openid-connect/certs"
ALLOWED_URLS = frozenset((RESOURCE_METADATA, DISCOVERY, JWKS))
MAX_BODY = 65536


class ProbeError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ProbeError("REDIRECT_FORBIDDEN")


def unique_keys(pairs):
    doc = {}
    for key, value in pairs:
        if key in doc:
            raise ProbeError("DUPLICATE_JSON_KEY")
        doc[key] = value
    return doc


def public_get(url):
    if url not in ALLOWED_URLS:
        raise ProbeError("URL_NOT_ALLOWLISTED")
    opener = build_opener(
        ProxyHandler({}), NoRedirect(),
        HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(Request(url, method="GET", headers={
                "Accept": "application/json",
                "User-Agent": "PRP-Public-GetOnly-Review/1.0",
        }), timeout=9) as response:
            if response.geturl() != url:
                raise ProbeError("REDIRECT_FORBIDDEN")
            if response.status != 200:
                raise ProbeError("NON_200_RESPONSE")
            if response.headers.get_content_type() != "application/json":
                raise ProbeError("CONTENT_TYPE_INVALID")
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ProbeError("JSON_TOO_LARGE")
            try:
                obj = json.loads(raw, object_pairs_hook=unique_keys)
            except (ValueError, UnicodeDecodeError) as exc:
                if isinstance(exc, ProbeError):
                    raise
                raise ProbeError("INVALID_JSON") from None
            if not isinstance(obj, dict):
                raise ProbeError("JSON_OBJECT_REQUIRED")
            return obj
    except ProbeError:
        raise
    except HTTPError:
        raise ProbeError("NON_200_RESPONSE") from None
    except (OSError, URLError, TimeoutError):
        # Never misclassify a transport failure as a safe 403/404/421 denial.
        raise ProbeError("TRANSPORT_UNVERIFIED") from None


def verify_resource(document):
    if document.get("resource") != RESOURCE:
        raise ProbeError("RESOURCE_MISMATCH")
    if document.get("authorization_servers") != [ISSUER]:
        raise ProbeError("ISSUER_REFERENCE_MISMATCH")
    if document.get("bearer_methods_supported") != ["header"]:
        raise ProbeError("BEARER_METHODS_INVALID")
    scopes = document.get("scopes_supported")
    if scopes != ["prp.tasks.read"]:
        raise ProbeError("TASK_ONLY_SCOPE_NOT_DEPLOYED")


def verify_discovery(document):
    if document.get("issuer") != ISSUER:
        raise ProbeError("ISSUER_MISMATCH")
    if document.get("client_id_metadata_document_supported") is not True:
        raise ProbeError("CIMD_NOT_ADVERTISED")
    if "S256" not in document.get("code_challenge_methods_supported", []):
        raise ProbeError("PKCE_S256_NOT_ADVERTISED")
    if "authorization_code" not in document.get("grant_types_supported", []):
        raise ProbeError("AUTHORIZATION_CODE_NOT_ADVERTISED")
    if document.get("jwks_uri") != JWKS:
        raise ProbeError("JWKS_ENDPOINT_DRIFT")


def verify_jwks(document):
    keys = document.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ProbeError("SIGNING_KEYS_MISSING")
    if not any(isinstance(k, dict)
               and k.get("kty") == "RSA" and k.get("n") and k.get("e")
               and k.get("use", "sig") == "sig"
               and k.get("alg", "RS256") == "RS256"
               for k in keys):
        raise ProbeError("RS256_PUBLIC_KEY_MISSING")


def assess(fetch=public_get):
    checks = {}
    for name, url, validate in (
        ("resource_metadata", RESOURCE_METADATA, verify_resource),
        ("issuer_discovery", DISCOVERY, verify_discovery),
        ("issuer_public_jwks", JWKS, verify_jwks),
    ):
        try:
            validate(fetch(url))
            checks[name] = {"state": "PASS"}
        except ProbeError as exc:
            checks[name] = {"state": "UNVERIFIED", "reason": str(exc)}
        except Exception:
            checks[name] = {"state": "UNVERIFIED", "reason": "UNEXPECTED_ERROR"}
    complete = all(v["state"] == "PASS" for v in checks.values())
    return {
        "status": ("PUBLIC_GET_ONLY_METADATA_PASSED" if complete else
                   "PUBLIC_GET_ONLY_METADATA_REVIEW_REQUIRED"),
        "phase": "public_metadata_only",
        "checks": checks,
        "request_method": "GET_ONLY",
        "target_environment": "staging",
        "production_prp_contacted": False,
        "bearer_or_login_tested": False,
        "mcp_post_or_tools_called": False,
        "public_ipv6_independently_proven": False,
        "chatgpt_oauth_verified": False,
        "b2_release_approved": False,
        "production_nginx_or_keycloak_changed": False,
    }


if __name__ == "__main__":
    report = assess()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PUBLIC_GET_ONLY_METADATA_PASSED":
        raise SystemExit(2)
