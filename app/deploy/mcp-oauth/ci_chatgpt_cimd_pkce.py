#!/usr/bin/env python3
"""CIMD/PKCE smoke against disposable Keycloak 26.8 only; no production endpoints.

Runs in the existing isolated GitHub CI Keycloak container AFTER its regular
smoke. The only external URL ever used by Keycloak is official public ChatGPT
CIMD metadata. Never obtains user tokens or prints login HTML, client state or
untrusted response bodies. Fails closed if CIMD egress/policy is unverified.
"""
import json
import os
import secrets
import hashlib
import base64
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.error import HTTPError

from keycloak_ephemeral_smoke import BASE, RESOURCE

CLIENT = "https://chatgpt.com/oauth/client.json"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
REALM_ADMIN = BASE + "/admin/realms/prp-mcp"
AUTH_URL = BASE + "/realms/prp-mcp/protocol/openid-connect/auth"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        return None


opener = build_opener(NoRedirect())


def request(url, *, method="GET", json_body=None, form=None, bearer=None):
    if not url.startswith(BASE + "/"):
        raise RuntimeError("REFUSED_NON_LOCAL_KEYCLOAK")
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    try:
        response = opener.open(Request(url, data=data, headers=headers, method=method), timeout=20)
    except HTTPError as err:
        response = err
    with response:
        status = response.status
        location = response.headers.get("Location", "")
        raw = response.read(300001)
        if len(raw) > 300000:
            raise RuntimeError("OVERSIZE_KEYCLOAK_RESPONSE")
        return status, location, raw


def read_json(url, bearer):
    status, _, raw = request(url, bearer=bearer)
    if status != 200:
        raise RuntimeError("ADMIN_READ_REJECTED_" + str(status))
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise RuntimeError("ADMIN_DOC_NOT_OBJECT")
    return result


def replace_admin_doc(url, token, value):
    status, _, _ = request(url, method="PUT", json_body=value, bearer=token)
    if status != 204:
        raise RuntimeError("ADMIN_UPDATE_REJECTED_" + str(status))


def admin_token():
    secret = os.environ.get("MCP_TEST_ADMIN_PASSWORD")
    if not secret or len(secret) < 24 or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("DISPOSABLE_CI_ONLY")
    status, _, body = request(
        BASE + "/realms/master/protocol/openid-connect/token",
        method="POST",
        form={"grant_type": "password", "client_id": "admin-cli",
              "username": "prp-smoke-admin", "password": secret},
    )
    if status != 200:
        raise RuntimeError("DISPOSABLE_ADMIN_LOGIN_FAILED")
    token = json.loads(body).get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("DISPOSABLE_ADMIN_TOKEN_MISSING")
    return token


def policy_docs():
    # These are deliberate negative-test fixtures, not a production installer.
    # PKCE MUST NOT be placed only under the client-id-uri policy.
    profiles = {"profiles": [
        {"name": "ci-chatgpt-cimd", "executors": [
            {"executor": "client-id-metadata-document", "configuration": {
                "cimd-allow-http-scheme": False,
                "cimd-allow-permitted-domains": ["chatgpt.com", "persistent.oaistatic.com"],
                "cimd-restrict-same-domain": False,
                "cimd-required-properties": ["client_id", "client_name", "redirect_uris"],
                "only-allow-confidential-client": False,
            }},
        ]},
        {"name": "ci-anonymous-pkce", "executors": [
            {"executor": "pkce-enforcer", "configuration": {"auto-configure": True}},
        ]},
    ]}
    policies = {"policies": [
        {"name": "ci-chatgpt-cimd-only", "enabled": True,
         "conditions": [{"condition": "client-id-uri", "configuration": {
             "client-id-uri-scheme": ["https"],
             "client-id-uri-allow-permitted-domains": ["chatgpt.com"],
         }}], "profiles": ["ci-chatgpt-cimd"]},
        {"name": "ci-cimd-anonymous-s256", "enabled": True,
         "conditions": [{"condition": "client-updater-context",
                         "configuration": {"update-client-source": ["ByAnonymous"]}}],
         "profiles": ["ci-anonymous-pkce"]},
    ]}
    return profiles, policies


def configure(token):
    profiles_endpoint = REALM_ADMIN + "/client-policies/profiles"
    policies_endpoint = REALM_ADMIN + "/client-policies/policies"
    original_profiles = read_json(profiles_endpoint, token)
    original_policies = read_json(policies_endpoint, token)
    if original_profiles.get("profiles") or original_policies.get("policies"):
        raise RuntimeError("CI_REALM_POLICIES_NOT_EMPTY")
    profiles, policies = policy_docs()
    replace_admin_doc(profiles_endpoint, token, profiles)
    replace_admin_doc(policies_endpoint, token, policies)
    found_profiles = read_json(profiles_endpoint, token)
    found_policies = read_json(policies_endpoint, token)
    expected_profiles = {x["name"] for x in profiles["profiles"]}
    expected_policies = {x["name"] for x in policies["policies"]}
    if not expected_profiles.issubset({x.get("name") for x in found_profiles.get("profiles", [])}):
        raise RuntimeError("CIMD_PROFILES_NOT_ACTIVE")
    if not expected_policies.issubset({
        x.get("name") for x in found_policies.get("policies", []) if x.get("enabled")
    }):
        raise RuntimeError("CIMD_POLICIES_NOT_ACTIVE")
    print("PASS CIMD: two isolated profiles and policies active in disposable Keycloak.")


def auth_request(method):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": CLIENT, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": "openid", "state": state, "resource": RESOURCE,
    }
    if method == "S256":
        params.update({"code_challenge_method": "S256", "code_challenge": challenge})
    elif method == "plain":
        params.update({"code_challenge_method": "plain", "code_challenge": verifier})
    status, location, _ = request(AUTH_URL + "?" + urlencode(params))
    # We never submit a login form, so a proper S256 request can only reach
    # Keycloak's login UI; no authorization code or user credential is used.
    error = None
    if status == 302 and location:
        parsed = urlsplit(location)
        if parsed.scheme == "https" and parsed.netloc == "chatgpt.com":
            query = parse_qs(parsed.query)
            if query.get("state") == [state]:
                error = query.get("error", [None])[0]
    return status, error, location


def require_pkce_result(mode):
    status, error, location = auth_request(mode)
    if mode == "S256":
        # 200 login page or an internal Keycloak redirect to its login route.
        internal = location.startswith(BASE + "/realms/prp-mcp/") or location.startswith("/realms/prp-mcp/")
        if not (status == 200 or (status == 302 and internal)) or error:
            raise RuntimeError("S256_AUTHORIZATION_NOT_ACCEPTED_HTTP_" + str(status))
    else:
        # Fail closed: an authorization/login page is NOT a rejection.
        # Errors may be a Keycloak 400 or an OAuth error redirect.
        if not (status == 400 or (status == 302 and error in {"invalid_request", "unauthorized_client"})):
            raise RuntimeError("PKCE_" + mode.upper() + "_NOT_ENFORCED_HTTP_" + str(status))


def verify_persisted(token):
    from urllib.parse import quote
    status, _, body = request(REALM_ADMIN + "/clients?clientId=" + quote(CLIENT, safe=""), bearer=token)
    if status != 200:
        raise RuntimeError("CIMD_CLIENT_READ_FAILED")
    clients = json.loads(body)
    exact = [c for c in clients if c.get("clientId") == CLIENT]
    if len(exact) != 1:
        raise RuntimeError("CIMD_CLIENT_NOT_REGISTERED")
    client = exact[0]
    if client.get("attributes", {}).get("pkce.code.challenge.method") != "S256":
        raise RuntimeError("CIMD_CLIENT_S256_NOT_PERSISTED")
    if client.get("redirectUris") != [REDIRECT]:
        raise RuntimeError("CIMD_CLIENT_CALLBACK_MISMATCH")
    print("PASS CIMD: real ChatGPT metadata resolved; exact callback and persisted S256.")


def main():
    token = admin_token()
    configure(token)
    # The first request exercises CIMD registration and ByAnonymous auto-config.
    require_pkce_result("S256")
    verify_persisted(token)
    for mode in ("missing", "plain"):
        require_pkce_result(mode)
        print("PASS CIMD: " + mode + " PKCE rejected on registered client.")
    # Every result is isolated CI behavior only; no real third-party login.
    print("PASS CIMD: isolated Keycloak 26.8 policy behavior verified; no user tokens.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not leak response body, HTML, OAuth state, callbacks or client
        # credentials into public CI logs; emit only controlled error reasons.
        code = str(exc)
        if len(code) > 100 or any(x in code.lower() for x in ("https://", "access_token", "password")):
            code = "CIMD_CI_UNVERIFIED"
        print("FAIL CIMD: " + code)
        raise SystemExit(1) from None
