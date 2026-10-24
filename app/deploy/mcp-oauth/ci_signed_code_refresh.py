#!/usr/bin/env python3
"""Disposable Keycloak Authorization Code + Signed JWT + offline refresh E2E.

Uses an entirely new CI-only client ID and a temporary RSA keypair, NOT
ChatGPT's private key, account, or redirect. Operates only on the isolated
GitHub runner Keycloak/PRP/MySQL stack established by test_full_e2e_ci.sh.
Never prints tokens, codes, cookies, passwords, signed assertions or user data.
"""
import json
import os
from http.cookiejar import CookieJar
from pathlib import Path
import ssl
import tempfile

import ci_pkce_browser as browser
import ci_static_client_jwt as signed
from oauth_token_check import check_token

CLIENT = "ci-prp-signed-browser"
TOKEN_URL = browser.ISSUER + "/protocol/openid-connect/token"
AUTH_CLIENT_SCOPES = ("basic", "prp.tasks.read", "offline_access")
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
PRP = "https://prp-e2e.localhost"
ADMIN = "https://auth-e2e.localhost/admin/realms/prp-mcp"


def require(code, expected, stage):
    if code != expected:
        raise RuntimeError(stage + "_HTTP_" + str(code))


def admin_session(opener):
    response = browser.request(opener, browser.ISSUER.replace("/realms/prp-mcp", "/realms/master")
                               + "/protocol/openid-connect/token", form=True, data={
        "grant_type": "password", "client_id": "admin-cli",
        "username": "prp-ci-admin", "password": os.environ["MCP_E2E_KC_ADMIN_PASSWORD"],
    })
    return browser.json_response(response, "SIGNED_CLIENT_ADMIN")["access_token"]


def ensure_offline_scope(opener, admin):
    path = ADMIN + "/client-scopes"
    response = browser.request(opener, path, bearer=admin)
    require(response[0], 200, "CLIENT_SCOPES_READ")
    records = json.loads(response[2])
    if not isinstance(records, list):
        raise RuntimeError("CLIENT_SCOPES_INVALID")
    if "offline_access" not in {x.get("name") for x in records}:
        created = browser.request(opener, path, bearer=admin, data={
            "name": "offline_access", "protocol": "openid-connect",
            "attributes": {
                "consent.screen.text": "Offline Access",
                "display.on.consent.screen": "true",
                "include.in.token.scope": "true",
            },
        })
        require(created[0], 201, "OFFLINE_SCOPE_SETUP")
    print("PASS SIGNED E2E: isolated Keycloak offline_access scope available.")


def register(opener, admin, certificate):
    created = browser.request(opener, ADMIN + "/clients", bearer=admin, data={
        "clientId": CLIENT,
        "name": "Disposable Signed JWT Browser Refresh Proof",
        "enabled": True, "protocol": "openid-connect",
        "publicClient": False, "clientAuthenticatorType": "client-jwt",
        "standardFlowEnabled": True, "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False,
        "consentRequired": True, "fullScopeAllowed": False,
        "redirectUris": [browser.CALLBACK], "webOrigins": [],
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": ["prp.tasks.read", "offline_access"],
        "attributes": {
            "use.jwks.url": "false",
            "jwt.credential.certificate": certificate,
            "pkce.code.challenge.method": "S256",
            "token.endpoint.auth.signing.alg": "RS256",
        },
        "protocolMappers": [{
            "name": "CI signed browser exact resource",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": "matrix-prp-mcp-resource",
                "id.token.claim": "false", "access.token.claim": "true",
            },
        }],
    })
    require(created[0], 201, "SIGNED_CLIENT_CREATION")
    print("PASS SIGNED E2E: confidential client with exact redirect, S256 and task-only scope.")


def signed_request(opener, key, fields, mode="valid"):
    assertion = signed.assertion(
        key, aud="https://invalid.example.invalid/token" if mode == "bad_audience" else TOKEN_URL,
        issuer=CLIENT, subject=CLIENT, replace_signature=(mode == "bad_signature"),
    )
    form = dict(fields)
    form["client_id"] = CLIENT
    if mode != "missing":
        form["client_assertion_type"] = ASSERTION_TYPE
        form["client_assertion"] = assertion
    return browser.request(opener, TOKEN_URL, data=form, form=True)


def code_exchange(opener, key, code, verifier, mode="valid"):
    return signed_request(opener, key, {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": browser.CALLBACK,
        "code_verifier": "invalid-test-verifier" if mode == "bad_verifier" else verifier,
        "resource": browser.RESOURCE,
    }, mode=mode)


def refresh(opener, key, current, mode="valid"):
    return signed_request(opener, key, {
        "grant_type": "refresh_token", "refresh_token": current,
        "resource": browser.RESOURCE,
    }, mode=mode)


def verify_tokens(opener, first, second):
    jwks = browser.json_response(browser.request(
        opener, browser.ISSUER + "/protocol/openid-connect/certs"), "SIGNED_JWKS")
    for token in (first, second):
        if not isinstance(token, str):
            raise RuntimeError("SIGNED_USER_ACCESS_TOKEN_MISSING")
        check_token(token, jwks, issuer=browser.ISSUER,
                    resource=browser.RESOURCE, client_id=CLIENT)


def run():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("GITHUB_RUNNER_REQUIRED")
    if os.environ.get("MCP_E2E_CRUD") == "true":
        raise RuntimeError("SIGNED_USER_TEST_REQUIRES_READONLY_STAGE")
    browser.CLIENT = CLIENT  # Exclusive to this standalone process.
    context = ssl.create_default_context(cafile=os.environ["MCP_E2E_CA_CERT"])
    opener = browser.build_opener(
        browser.HTTPSHandler(context=context),
        browser.HTTPCookieProcessor(CookieJar()), browser.SafeRedirect(),
    )
    browser.wait_ready(opener, browser.ISSUER + "/.well-known/openid-configuration")
    with tempfile.TemporaryDirectory(prefix="mcp-signed-browser-", dir=os.environ["RUNNER_TEMP"]) as folder:
        key, cert = signed.create_keypair(Path(folder))
        admin = admin_session(opener)
        ensure_offline_scope(opener, admin)
        register(opener, admin, cert)
        code, verifier = browser.code_pkce(
            opener, "e2e-keycloak-owner", os.environ["MCP_E2E_KC_USER_PASSWORD"],
            requested_scopes="openid offline_access prp.tasks.read",
        )
        response = code_exchange(opener, key, code, verifier)
        first = browser.json_response(response, "SIGNED_CODE_EXCHANGE")
        access, refresh_token = first.get("access_token"), first.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise RuntimeError("OFFLINE_REFRESH_TOKEN_MISSING")
        print("PASS SIGNED E2E: real login/consent, S256 code and signed private_key_jwt exchange.")

        for mode in ("missing", "bad_signature", "bad_audience"):
            rejected = refresh(opener, key, refresh_token, mode)
            if rejected[0] not in (400, 401):
                raise RuntimeError("INVALID_REFRESH_CLIENT_ASSERTION_ACCEPTED_" + mode)
        renewed = browser.json_response(refresh(opener, key, refresh_token), "SIGNED_REFRESH")
        new_access, current_refresh = renewed.get("access_token"), renewed.get("refresh_token")
        if not isinstance(current_refresh, str) or not current_refresh:
            raise RuntimeError("ROTATED_REFRESH_TOKEN_MISSING")
        verify_tokens(opener, access, new_access)
        print("PASS SIGNED E2E: offline refresh through signed client JWT, access-token JWKS/audience.")

        # An unrelated user or an unapproved MCP client must never see tasks.
        unauth = browser.jsonrpc(opener, new_access, 31, "tools/list")
        require(unauth[0], 401, "SIGNED_UNGRANTED_CLIENT")
        owner = browser.json_response(browser.request(
            opener, PRP + "/api/auth/login",
            data={"username": "stage_admin", "password": os.environ["MCP_E2E_PRP_PASSWORD"]}),
            "PRP_OWNER_LOGIN")
        owner_token = owner["data"]["token"]
        grant = browser.json_response(browser.request(
            opener, PRP + "/api/mcp/clients", bearer=owner_token,
            data={"clientId": CLIENT, "scopes": ["prp.tasks.read"],
                  "password": os.environ["MCP_E2E_PRP_PASSWORD"]}),
            "SIGNED_PRP_GRANT")
        if grant.get("data", {}).get("status") != "ACTIVE":
            raise RuntimeError("SIGNED_PRP_GRANT_NOT_ACTIVE")
        tools = browser.jsonrpc(opener, new_access, 32, "tools/list", {})
        require(tools[0], 200, "SIGNED_MCP_TOOL_DISCOVERY")
        if "prp_tasks_list" not in {x.get("name") for x in tools[1].get("result", {}).get("tools", [])}:
            raise RuntimeError("SIGNED_TASK_TOOL_MISSING")
        task = browser.jsonrpc(opener, new_access, 33, "tools/call",
                               {"name": "prp_tasks_list", "arguments": {}})
        if task[0] != 200 or task[1].get("error") or task[1].get("result", {}).get("isError"):
            raise RuntimeError("SIGNED_READ_TOOL_REJECTED")
        print("PASS SIGNED E2E: refreshed JWT reads scoped synthetic PRP tasks.")

        browser.json_response(browser.request(
            opener, PRP + "/api/mcp/clients/revoke", bearer=owner_token,
            data={"clientId": CLIENT}), "SIGNED_CLIENT_REVOKE")
        require(browser.jsonrpc(opener, new_access, 34, "tools/list")[0], 401,
                "SIGNED_CLIENT_REVOKED_ACCESS")
        print("PASS SIGNED E2E: PRP revokes access to still-valid refreshed bearer.")

        # Authorization-server refresh revocation is a separate Keycloak
        # endpoint and is NOT claimed by the PRP grant revocation proof.
        # The PRP grant itself must block a previously issued bearer immediately.


if __name__ == "__main__":
    try:
        run()
    except Exception as err:
        message = str(err)
        if len(message) > 140 or any(term in message for term in
                                      ("?", "Bearer", "password=", "token=", "access_token")):
            message = "SIGNED_E2E_UNVERIFIED"
        print("FAIL SIGNED E2E: " + message)
        raise SystemExit(1)
