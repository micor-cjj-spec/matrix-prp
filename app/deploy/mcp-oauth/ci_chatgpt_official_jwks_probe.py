#!/usr/bin/env python3
"""DISPOSABLE-only Keycloak official-JWKS network and bad-assertion verification.

The test reads public OpenAI JWKS inside Keycloak's actual container network
namespace, without saving key material or issuing any user tokens. It then
submits a synthetic invalid private_key_jwt to the exact pre-registered
ChatGPT client; 'invalid_client' is required. These two checks are separate:
this does NOT demonstrate that a real OpenAI-signed assertion succeeds, or
that the Keycloak JVM's CA store / HTTP client fetched the remote JWKS.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import ci_chatgpt_cimd_pkce as kc
from ci_static_client_jwt import create_keypair, openssl, b64

JWKS = "https://chatgpt.com/oauth/jwks.json"
CLIENT = "https://chatgpt.com/oauth/client.json"
TOKEN_ENDPOINT = kc.BASE + "/realms/prp-mcp/protocol/openid-connect/token"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# Separate OCI interpreter shares the disposable Keycloak network namespace;
# it does NOT share the Keycloak JVM's TLS client / CA trust store.
NETWORK_PROBE = r"""
import json, ssl, urllib.request
url = "https://chatgpt.com/oauth/jwks.json"
class StopRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("REDIRECT_FORBIDDEN")
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), StopRedirect(),
    urllib.request.HTTPSHandler(context=ssl.create_default_context()))
with opener.open(urllib.request.Request(
        url, headers={"Accept": "application/json"}, method="GET"), timeout=12) as r:
    if r.status != 200 or r.headers.get_content_type() != "application/json":
        raise ValueError("INVALID_HTTP_OR_MIME")
    payload = r.read(65537)
    if len(payload) > 65536:
        raise ValueError("TOO_LARGE")
    doc = json.loads(payload)
    keys = doc.get("keys") if isinstance(doc, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ValueError("JWKS_EMPTY")
    if not any(isinstance(k, dict) and k.get("kty") == "RSA"
               and k.get("kid") and k.get("n") and k.get("e")
               and k.get("use", "sig") == "sig" for k in keys):
        raise ValueError("RS256_PUBLIC_SIGNING_KEY_ABSENT")
    if any(not isinstance(k, dict)
           or any(secret in k for secret in
                  ("d", "p", "q", "dp", "dq", "qi", "oth", "k"))
           for k in keys):
        raise ValueError("NONPUBLIC_JWKS")
print("OFFICIAL_JWKS_SAME_NAMESPACE_REACHABLE")
"""


def assert_disposable():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or not os.environ.get("MCP_TEST_ADMIN_PASSWORD")
            or kc.BASE != "http://127.0.0.1:18080"):
        raise RuntimeError("REFUSED_NON_DISPOSABLE_ENVIRONMENT")


def verify_persisted_remote_jwks():
    token = kc.admin_token()
    from urllib.parse import quote
    url = kc.REALM_ADMIN + "/clients?clientId=" + quote(CLIENT, safe="")
    status, _, body = kc.request(url, bearer=token)
    if status != 200:
        raise RuntimeError("EXACT_CLIENT_LOOKUP_FAILED")
    clients = [x for x in json.loads(body) if x.get("clientId") == CLIENT]
    if len(clients) != 1:
        raise RuntimeError("EXACT_CLIENT_NOT_UNIQUE")
    cid = clients[0].get("id")
    if not isinstance(cid, str):
        raise RuntimeError("EXACT_CLIENT_INTERNAL_ID_MISSING")
    full = kc.read_json(kc.REALM_ADMIN + "/clients/" + quote(cid, safe=""), token)
    attrs = full.get("attributes") or {}
    if (attrs.get("use.jwks.url") != "true"
            or attrs.get("jwks.url") != JWKS
            or full.get("clientAuthenticatorType") != "client-jwt"
            or full.get("clientId") != CLIENT
            or full.get("redirectUris") !=
               ["https://chatgpt.com/connector_platform_oauth_redirect"]
            or full.get("fullScopeAllowed") is not False):
        raise RuntimeError("REMOTE_JWKS_CLIENT_CONFIG_INVALID")
    print("PASS OFFICIAL JWKS: exact client uses official remote URL before synthetic test key substitution.")


def network_namespace_probe():
    cmd = [
        "docker", "run", "--rm",
        "--network", "container:prp-mcp-keycloak-ci",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=192m",
        "python:3.12-alpine", "python", "-c", NETWORK_PROBE,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("KEYCLOAK_NETWORK_JWKS_EGRESS_UNVERIFIED") from None
    if p.returncode != 0 or p.stdout.strip() != "OFFICIAL_JWKS_SAME_NAMESPACE_REACHABLE":
        # Do not print external errors, metadata, URLs with query or raw keys.
        raise RuntimeError("KEYCLOAK_NETWORK_JWKS_EGRESS_UNVERIFIED")
    print("PASS OFFICIAL JWKS: OpenAI public JWKS reachable from disposable Keycloak network namespace.")


def invalid_assertion(private_key):
    issued = int(time.time())
    header = {
        "typ": "JWT",
        "alg": "RS256",
        "kid": "ci-not-an-official-openai-public-key",
    }
    claims = {
        "iss": CLIENT, "sub": CLIENT,
        "aud": TOKEN_ENDPOINT, "jti": secrets.token_urlsafe(24),
        "iat": issued, "nbf": issued - 2, "exp": issued + 60,
    }
    unsigned = ".".join(b64(json.dumps(part, separators=(",", ":")).encode())
                        for part in (header, claims))
    signature = openssl("dgst", "-sha256", "-sign", private_key,
                        input_data=unsigned.encode())
    return unsigned + "." + b64(signature)


def require_synthetic_signature_denied():
    with tempfile.TemporaryDirectory(prefix="official-jwks-ci-",
                                     dir=os.environ["RUNNER_TEMP"]) as folder:
        key, unused_cert = create_keypair(Path(folder))
        status, _, body = kc.request(
            TOKEN_ENDPOINT, method="POST", form={
                "grant_type": "authorization_code",
                "client_id": CLIENT,
                "code": "ci-code-never-issued",
                "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect",
                "client_assertion_type": ASSERTION_TYPE,
                "client_assertion": invalid_assertion(key),
            })
        if status not in (400, 401):
            raise RuntimeError("UNTRUSTED_OPENAI_CLIENT_ASSERTION_NOT_REJECTED")
        try:
            reason = json.loads(body).get("error")
        except (ValueError, AttributeError):
            raise RuntimeError("INVALID_CLIENT_DENIAL_NOT_JSON") from None
        if reason != "invalid_client":
            raise RuntimeError("SIGNED_CLIENT_AUTHENTICATION_DENIAL_NOT_PROVEN")
    print("PASS OFFICIAL JWKS: untrusted RSA-signed client assertion rejected as invalid_client.")


def main():
    assert_disposable()
    verify_persisted_remote_jwks()
    network_namespace_probe()
    require_synthetic_signature_denied()
    print("BOUNDARY: public JWKS network reachable, real OpenAI signature NOT VERIFIED, live Realm unchanged.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        reason = str(error)
        if reason not in {
            "REFUSED_NON_DISPOSABLE_ENVIRONMENT",
            "EXACT_CLIENT_LOOKUP_FAILED", "EXACT_CLIENT_NOT_UNIQUE",
            "EXACT_CLIENT_INTERNAL_ID_MISSING",
            "REMOTE_JWKS_CLIENT_CONFIG_INVALID",
            "KEYCLOAK_NETWORK_JWKS_EGRESS_UNVERIFIED",
            "UNTRUSTED_OPENAI_CLIENT_ASSERTION_NOT_REJECTED",
            "INVALID_CLIENT_DENIAL_NOT_JSON",
            "SIGNED_CLIENT_AUTHENTICATION_DENIAL_NOT_PROVEN",
        }:
            reason = "OFFICIAL_JWKS_PROBE_UNVERIFIED"
        print("FAIL OFFICIAL JWKS: " + reason)
        raise SystemExit(1) from None
