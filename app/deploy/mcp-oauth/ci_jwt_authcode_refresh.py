#!/usr/bin/env python3
"""Disposable-only Keycloak Authorization Code + PKCE + client-jwt + offline refresh.

Uses only loopback Keycloak and temporary RSA keys/CI user. The client ID here
is a synthetic one, NOT the real ChatGPT client. Never use production credentials
or log passwords, cookies, authorization codes, assertions or bearer tokens.
"""
import base64
import hashlib
from http.cookiejar import CookieJar, DefaultCookiePolicy
import json
import os
from pathlib import Path
import secrets
import tempfile
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

import ci_pkce_browser as browser
from ci_chatgpt_cimd_pkce import BASE, REALM_ADMIN, admin_token, request, read_json, replace_admin_doc
from ci_static_client_jwt import (create_keypair, assertion, ASSERTION_TYPE,
                                  RESOURCE, ISSUER, TOKEN_ENDPOINT)
from oauth_token_check import check_token, _b64url

CLIENT = "ci-authcode-private-jwt"
CALLBACK = "http://127.0.0.1:8765/callback"
SCOPE = "openid offline_access prp.tasks.read"


class LocalRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        dest = urlsplit(url)
        if dest._replace(query="", fragment="").geturl() == CALLBACK:
            raise browser.CallbackReceived(url)
        if (dest.scheme != "http" or dest.netloc != "127.0.0.1:18080"
                or not dest.path.startswith("/realms/prp-mcp/")):
            raise RuntimeError("UNEXPECTED_AUTH_REDIRECT")
        return super().redirect_request(req, fp, code, msg, headers, url)


def browser_opener():
    # Reuse the already green login/consent/PKCE form driver, but make its
    # issuer strictly the ephemeral loopback Keycloak.
    browser.ISSUER = ISSUER
    browser.RESOURCE = RESOURCE
    browser.CLIENT = CLIENT
    browser.CALLBACK = CALLBACK
    browser.request = classified_browser_request
    # Keycloak sets Secure auth-session cookies even in its dev-mode loopback
    # HTTP runner. Browsers treat localhost as a secure context, while Python's
    # CookieJar does not by default. This exception is restricted to a
    # disposable Keycloak loopback origin by LocalRedirect and request allowlist;
    # NEVER apply it to public or production HTTPS endpoints.
    policy = DefaultCookiePolicy(secure_protocols=("https", "wss", "http"))
    return build_opener(HTTPCookieProcessor(CookieJar(policy=policy)), LocalRedirect())


def classified_browser_request(opener, url, *, data=None, bearer=None, form=False, method=None):
    """Return original driver contract, with static-only 400 error categories.

    Keycloak login POST errors are otherwise silently reduced to HTTP 400,
    making CI unable to distinguish an invalid realm/client setting from
    a broken browser driver. Never print URLs, HTML, cookies or response.
    """
    if not url.startswith(BASE + "/"):
        raise RuntimeError("DISPOSABLE_BROWSER_NON_LOCAL_REQUEST")
    headers = {"Accept": "text/html" if form else "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    body = None
    if data is not None:
        if form:
            body = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    try:
        response = opener.open(Request(url, data=body, headers=headers, method=method), timeout=15)
    except HTTPError as err:
        response = err
    with response:
        status = response.status
        raw = response.read(250001)
        if len(raw) > 250000:
            raise RuntimeError("OVERSIZED_BROWSER_RESPONSE")
        content = raw.decode("utf-8", errors="replace")
        # Token endpoint HTTP 400 is an expected *negative* test result
        # for bad PKCE, replay and revoked refresh; let exchange() assert it.
        if status == 400 and not url.startswith(TOKEN_ENDPOINT):
            lower = content[:30000].lower()
            diagnostic = "UNCLASSIFIED"
            for needle, category in (
                ("invalid_scope", "INVALID_SCOPE"),
                ("invalid scope", "INVALID_SCOPE"),
                ("invalid_grant", "INVALID_GRANT"),
                ("invalid_request", "INVALID_REQUEST"),
                ("invalid_client", "INVALID_CLIENT"),
                ("invalid username or password", "INVALID_LOGIN"),
                ("page has expired", "LOGIN_PAGE_EXPIRED"),
                ("cookie not found", "LOGIN_COOKIE_MISSING"),
                ("restart login", "LOGIN_RESTART"),
                ("request failed", "REQUEST_FAILED"),
                ("client session", "CLIENT_SESSION"),
            ):
                if needle in lower:
                    diagnostic = category
                    break
            stage = "TOKEN" if "/token" in url else (
                "LOGIN" if "/login-actions/" in url else "AUTHORIZE")
            raise RuntimeError("LOCAL_KEYCLOAK_HTTP_400_" + stage + "_" + diagnostic)
        return status, response.headers.get("Content-Type", ""), content


def configure_realm(token):
    realm = read_json(REALM_ADMIN, token)
    realm["revokeRefreshToken"] = True
    realm["refreshTokenMaxReuse"] = 0
    replace_admin_doc(REALM_ADMIN, token, realm)
    result = read_json(REALM_ADMIN, token)
    if result.get("revokeRefreshToken") is not True or result.get("refreshTokenMaxReuse") != 0:
        raise RuntimeError("OFFLINE_ROTATION_NOT_ACTIVE")
    scopes_status, _, raw = request(REALM_ADMIN + "/client-scopes", bearer=token)
    if scopes_status != 200:
        raise RuntimeError("READ_REALM_SCOPES_FAILED")
    available = {x.get("name") for x in json.loads(raw)}
    if not {"basic", "offline_access", "prp.tasks.read"}.issubset(available):
        raise RuntimeError("REQUIRED_OFFLINE_CLIENT_SCOPE_MISSING")
    print("PASS AUTHCODE: disposable Realm enables refresh rotation and read-only scopes.")


def activate_exact_refresh_policy(token):
    """Attach CI-only SPI to the real Keycloak refresh event for the throwaway client.

    Never replace existing policy collections with a test fixture. Keycloak's
    synthetic realm is thrown away after this GitHub Actions workflow.
    """
    profiles_url = REALM_ADMIN + "/client-policies/profiles"
    policies_url = REALM_ADMIN + "/client-policies/policies"
    profiles = read_json(profiles_url, token)
    policies = read_json(policies_url, token)
    profile_name = "ci-strict-refresh-resource"
    policy_name = "ci-strict-refresh-resource-only"
    if profile_name in {x.get("name") for x in profiles.get("profiles", [])}:
        raise RuntimeError("CI_REFRESH_PROFILE_ALREADY_REGISTERED")
    if policy_name in {x.get("name") for x in policies.get("policies", [])}:
        raise RuntimeError("CI_REFRESH_POLICY_ALREADY_REGISTERED")
    profiles["profiles"].append({
        "name": profile_name,
        "executors": [{"executor": "prp-ci-refresh-resource-guard", "configuration": {}}],
    })
    replace_admin_doc(profiles_url, token, profiles)
    policies["policies"].append({
        "name": policy_name,
        "enabled": True,
        "conditions": [{"condition": "any-client", "configuration": {}}],
        "profiles": [profile_name],
    })
    replace_admin_doc(policies_url, token, policies)
    actual_profiles = read_json(profiles_url, token)
    actual_policies = read_json(policies_url, token)
    matches = [x for x in actual_profiles.get("profiles", []) if x.get("name") == profile_name]
    enabled = [x for x in actual_policies.get("policies", []) if x.get("name") == policy_name
               and x.get("enabled") is True]
    if len(matches) != 1 or len(enabled) != 1:
        raise RuntimeError("CI_REFRESH_RESOURCE_POLICY_NOT_PERSISTED")
    if not any(x.get("executor") == "prp-ci-refresh-resource-guard"
               for x in matches[0].get("executors", [])):
        raise RuntimeError("CI_REFRESH_RESOURCE_SPI_NOT_INSTALLED")
    print("PASS AUTHCODE: real disposable Keycloak refresh-policy executor installed.")


def create_user(token, password):
    username = "ci-jwt-browser-" + secrets.token_hex(5)
    value = {
        "username": username,
        "enabled": True,
        "emailVerified": True,
        "firstName": "Disposable", "lastName": "OAuth Test",
        "email": username + "@example.invalid",
        "requiredActions": [],
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    status, _, _ = request(REALM_ADMIN + "/users", method="POST",
                           json_body=value, bearer=token)
    if status != 201:
        raise RuntimeError("CI_USER_CREATION_HTTP_" + str(status))
    return username


def register_client(token, certificate):
    value = {
        "clientId": CLIENT,
        "name": "Ephemeral CI authcode private-key-JWT refresh",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-jwt",
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "consentRequired": True,
        "fullScopeAllowed": False,
        "redirectUris": [CALLBACK],
        "webOrigins": [],
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": ["offline_access", "prp.tasks.read"],
        "attributes": {
            "use.jwks.url": "false",
            "jwt.credential.certificate": certificate,
            "token.endpoint.auth.signing.alg": "RS256",
            "pkce.code.challenge.method": "S256",
        },
        "protocolMappers": [{
            "name": "CI resource indicator only",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            # The Keycloak Audience Mapper treats Included Client and
            # Included Custom Audience as mutually exclusive. An actual
            # HTTPS MCP resource URI MUST use the latter, otherwise refresh
            # grants can issue an internal client-id audience.
            "config": {"included.custom.audience": RESOURCE,
                       "id.token.claim": "false", "access.token.claim": "true"},
        }],
    }
    status, _, _ = request(REALM_ADMIN + "/clients",
                           method="POST", json_body=value, bearer=token)
    if status != 201:
        raise RuntimeError("CI_AUTHCODE_CLIENT_CREATION_HTTP_" + str(status))
    print("PASS AUTHCODE: PKCE S256 confidential client with signed-JWT auth registered.")


def exchange(opener, key, *, grant, code=None, verifier=None, refresh=None,
             bad_auth=False, resource=RESOURCE, scope=SCOPE):
    data = {
        "grant_type": grant,
        "client_id": CLIENT,
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion(
            key, issuer=CLIENT, subject=CLIENT,
            replace_signature=bad_auth,
        ),
        "resource": resource,
    }
    if grant == "authorization_code":
        data.update({"code": code, "code_verifier": verifier,
                     "redirect_uri": CALLBACK})
    elif grant == "refresh_token":
        data["refresh_token"] = refresh
        # Keep the already-granted resource and task scope explicit.
        # Some resource-indicator implementations recalculate the audience
        # from the refresh request rather than inheriting the original grant.
        data["scope"] = scope
    else:
        raise RuntimeError("UNSUPPORTED_CI_GRANT")
    result = browser.request(opener, TOKEN_ENDPOINT, data=data, form=True)
    if result[0] != 200:
        # Only fixed HTTP status; never print error descriptions or payload.
        return result[0], None
    try:
        values = json.loads(result[2])
        if not isinstance(values, dict):
            raise ValueError()
    except ValueError:
        raise RuntimeError("INVALID_TOKEN_JSON") from None
    return 200, values


def verify_access(value, jwks, *, subject=None):
    bearer = value.get("access_token")
    if not isinstance(bearer, str):
        raise RuntimeError("ACCESS_TOKEN_ABSENT")
    try:
        check_token(bearer, jwks, issuer=ISSUER, resource=RESOURCE, client_id=CLIENT)
    except ValueError as exc:
        if str(exc) != "JWT audience must contain exact MCP resource":
            raise
        # The verifier checks the RSA signature BEFORE rejecting the
        # audience. Never print actual claims, client IDs or bearer.
        claims = json.loads(_b64url(bearer.split(".")[1]))
        aud = claims.get("aud")
        audiences = [aud] if isinstance(aud, str) else aud if isinstance(aud, list) else []
        source = ("EMPTY" if not audiences else
                  "CONTAINS_CLIENT" if "matrix-prp-mcp-resource" in audiences else
                  "CONTAINS_ACCOUNT" if "account" in audiences else "OTHER")
        task_scope = "READ" if "prp.tasks.read" in claims.get("scope", "").split() else "NO_READ"
        raise RuntimeError("SIGNED_REFRESH_AUDIENCE_" + source + "_SCOPE_" + task_scope) from None
    claims = json.loads(_b64url(bearer.split(".")[1]))
    if subject is not None and claims.get("sub") != subject:
        raise RuntimeError("REFRESH_TOKEN_SUBJECT_CHANGED")
    if "prp.finance.read" in claims.get("scope", "").split():
        raise RuntimeError("UNGRANTED_FINANCE_SCOPE")
    return claims["sub"]


def classify_unapproved_refresh(status, response, jwks, *, subject, prior_refresh):
    """Static, safe diagnosis for an unintended-resource refresh acceptance.

    Never log JWTs, client credentials, tokens, user subjects or the arbitrary
    requested resource. Verify issuer signature and trusted claims BEFORE
    examining the signed audience. This diagnostic is NOT an acceptance gate:
    caller must still fail closed when an unrelated resource is accepted.
    """
    if status != 200 or not isinstance(response, dict):
        return "UNEXPECTED_RESPONSE"
    bearer = response.get("access_token")
    if not isinstance(bearer, str):
        return "NO_ACCESS_TOKEN"
    try:
        verify_access(response, jwks, subject=subject)
    except (ValueError, RuntimeError):
        return "MCP_TOKEN_VALIDATION_FAILED"
    claims = json.loads(_b64url(bearer.split(".")[1]))
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else aud
    if not isinstance(audiences, list) or not all(isinstance(a, str) for a in audiences):
        return "AUDIENCE_INVALID"
    # The unexpected resource is a constant only within this disposable test.
    # Do not print audience values, even those supplied by an AS response.
    unexpected = "https://not-prp.staging.example.org/api/mcp"
    if unexpected in audiences:
        return "FOREIGN_RESOURCE_AUDIENCE_ISSUED"
    if RESOURCE not in audiences:
        return "CANONICAL_RESOURCE_AUDIENCE_MISSING"
    scopes = claims.get("scope", "")
    if not isinstance(scopes, str) or "prp.finance.read" in scopes.split():
        return "UNEXPECTED_SCOPE_ISSUED"
    token = response.get("refresh_token")
    if isinstance(token, str) and token and token != prior_refresh:
        return "CANONICAL_AUDIENCE_ONLY_REFRESH_ROTATED"
    return "CANONICAL_AUDIENCE_ONLY_NO_ROTATION_PROOF"


def revoke(opener, key, refresh):
    data = {
        "client_id": CLIENT,
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion(key, issuer=CLIENT, subject=CLIENT),
        "token": refresh,
        "token_type_hint": "refresh_token",
    }
    response = browser.request(opener, ISSUER + "/protocol/openid-connect/revoke",
                                data=data, form=True)
    if response[0] != 200:
        raise RuntimeError("OFFLINE_REVOKE_HTTP_" + str(response[0]))


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or not os.environ.get("MCP_TEST_ADMIN_PASSWORD")):
        raise RuntimeError("DISPOSABLE_GITHUB_CI_ONLY")
    with tempfile.TemporaryDirectory(prefix="prp-jwt-authcode-", dir=os.environ["RUNNER_TEMP"]) as d:
        key, certificate = create_keypair(Path(d))
        admin = admin_token()
        configure_realm(admin)
        register_client(admin, certificate)
        activate_exact_refresh_policy(admin)
        user_password = secrets.token_urlsafe(36)
        username = create_user(admin, user_password)
        opener = browser_opener()
        # Reuse existing robust login/consent driver; the code and verifier
        # exist only in this process and are never logged.
        bad_code, _ = browser.code_pkce(opener, username, user_password, "openid prp.tasks.read")
        bad_status, _ = exchange(opener, key, grant="authorization_code",
                                 code=bad_code, verifier=secrets.token_urlsafe(48))
        if bad_status not in (400, 401):
            raise RuntimeError("WRONG_PKCE_VERIFIER_ACCEPTED")
        print("PASS AUTHCODE: authorization code rejects incorrect PKCE verifier.")

        code, verifier = browser.code_pkce(opener, username, user_password, SCOPE)
        status, tokens = exchange(opener, key, grant="authorization_code",
                                  code=code, verifier=verifier)
        if status != 200 or not tokens:
            raise RuntimeError("AUTHCODE_CLIENT_JWT_EXCHANGE_HTTP_" + str(status))
        jwks_status, _, jwks_body = request(ISSUER + "/protocol/openid-connect/certs")
        if jwks_status != 200:
            raise RuntimeError("JWKS_HTTP_" + str(jwks_status))
        jwks = json.loads(jwks_body)
        sub = verify_access(tokens, jwks)
        first_refresh = tokens.get("refresh_token")
        if not isinstance(first_refresh, str) or len(first_refresh) < 16:
            raise RuntimeError("OFFLINE_REFRESH_NOT_GRANTED")
        print("PASS AUTHCODE: real user consent + S256 code + private_key_jwt exchange, signed resource JWT.")

        bad_status, _ = exchange(opener, key, grant="refresh_token",
                                 refresh=first_refresh, bad_auth=True)
        if bad_status not in (400, 401):
            raise RuntimeError("BAD_REFRESH_CLIENT_SIGNATURE_ACCEPTED")

        wrong_resource_status, wrong_resource_response = exchange(
            opener, key, grant="refresh_token", refresh=first_refresh,
            resource="https://not-prp.staging.example.org/api/mcp")
        if wrong_resource_status not in (400, 401):
            # Distinguish a rejected resource policy from an issuer that
            # ignores the request but stamps the correct MCP-only audience.
            # Neither behavior can be silently labeled approved; preserve
            # the intentional failing authorization-server negative test.
            kind = classify_unapproved_refresh(
                wrong_resource_status, wrong_resource_response, jwks,
                subject=sub, prior_refresh=first_refresh)
            print("NEGATIVE RESOURCE DIAGNOSTIC=" + kind)
            raise RuntimeError("WRONG_REFRESH_RESOURCE_ACCEPTED")
        wrong_scope_status, _ = exchange(
            opener, key, grant="refresh_token", refresh=first_refresh,
            scope="openid offline_access prp.finance.read")
        if wrong_scope_status not in (400, 401):
            raise RuntimeError("UNGRANTED_REFRESH_FINANCE_SCOPE_ACCEPTED")
        print("PASS AUTHCODE: refresh rejects unrelated MCP resource and finance scope.")

        refreshed_status, refreshed = exchange(opener, key, grant="refresh_token",
                                                refresh=first_refresh)
        if refreshed_status != 200 or not refreshed:
            raise RuntimeError("OFFLINE_REFRESH_HTTP_" + str(refreshed_status))
        verify_access(refreshed, jwks, subject=sub)
        second_refresh = refreshed.get("refresh_token")
        if not isinstance(second_refresh, str) or not second_refresh or second_refresh == first_refresh:
            raise RuntimeError("OFFLINE_REFRESH_NOT_ROTATED")
        replay_status, _ = exchange(opener, key, grant="refresh_token",
                                    refresh=first_refresh)
        if replay_status not in (400, 401):
            raise RuntimeError("OLD_OFFLINE_REFRESH_REPLAY_ACCEPTED")
        print("PASS AUTHCODE: offline refresh with signed client JWT, rotation and replay denial.")

        revoke(opener, key, second_refresh)
        revoked_status, _ = exchange(opener, key, grant="refresh_token",
                                     refresh=second_refresh)
        if revoked_status not in (400, 401):
            raise RuntimeError("REVOKED_OFFLINE_REFRESH_ACCEPTED")
        print("PASS AUTHCODE: refresh revocation blocks renewed access.")
        print("CI-ONLY: no real ChatGPT client keys, production data or server changes.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error = str(e)
        if len(error) > 110 or any(term in error.lower() for term in (
                "access_token", "http://", "https://", "password", "bearer", "?")):
            error = "AUTHCODE_CI_UNVERIFIED"
        print("FAIL AUTHCODE: " + error)
        raise SystemExit(1) from None
