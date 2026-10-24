#!/usr/bin/env python3
"""Disposable-only Keycloak Authorization Code + PKCE + client-jwt + offline refresh.

Uses only loopback Keycloak and temporary RSA keys/CI user. The client ID here
is a synthetic one, NOT the real ChatGPT client. Never use production credentials
or log passwords, cookies, authorization codes, assertions or bearer tokens.
"""
import base64
import hashlib
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import tempfile
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler

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
    # Reuse the already green login/consent/PCKE form driver, but make its
    # issuer strictly the ephemeral loopback Keycloak.
    browser.ISSUER = ISSUER
    browser.RESOURCE = RESOURCE
    browser.CLIENT = CLIENT
    browser.CALLBACK = CALLBACK
    return build_opener(HTTPCookieProcessor(CookieJar()), LocalRedirect())


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


def create_user(token, password):
    username = "ci-jwt-browser-" + secrets.token_hex(5)
    value = {
        "username": username,
        "enabled": True,
        "emailVerified": True,
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
            "config": {"included.client.audience": "matrix-prp-mcp-resource",
                       "id.token.claim": "false", "access.token.claim": "true"},
        }],
    }
    status, _, _ = request(REALM_ADMIN + "/clients",
                           method="POST", json_body=value, bearer=token)
    if status != 201:
        raise RuntimeError("CI_AUTHCODE_CLIENT_CREATION_HTTP_" + str(status))
    print("PASS AUTHCODE: PKCE S256 confidential client with signed-JWT auth registered.")


def exchange(opener, key, *, grant, code=None, verifier=None, refresh=None, bad_auth=False):
    data = {
        "grant_type": grant,
        "client_id": CLIENT,
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion(
            key, issuer=CLIENT, subject=CLIENT,
            replace_signature=bad_auth,
        ),
        "resource": RESOURCE,
    }
    if grant == "authorization_code":
        data.update({"code": code, "code_verifier": verifier,
                     "redirect_uri": CALLBACK})
    elif grant == "refresh_token":
        data["refresh_token"] = refresh
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
    check_token(bearer, jwks, issuer=ISSUER, resource=RESOURCE, client_id=CLIENT)
    claims = json.loads(_b64url(bearer.split(".")[1]))
    if subject is not None and claims.get("sub") != subject:
        raise RuntimeError("REFRESH_TOKEN_SUBJECT_CHANGED")
    if "prp.finance.read" in claims.get("scope", "").split():
        raise RuntimeError("UNGRANTED_FINANCE_SCOPE")
    return claims["sub"]


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
        user_password = secrets.token_urlsafe(36)
        username = create_user(admin, user_password)
        opener = browser_opener()
        # Reuse existing robust login/consent driver; the code and verifier
        # exist only in this process and are never logged.
        bad_code, _ = browser.code_pkce(opener, username, user_password, SCOPE)
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
