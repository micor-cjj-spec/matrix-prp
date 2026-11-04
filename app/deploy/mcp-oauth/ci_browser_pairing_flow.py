#!/usr/bin/env python3
"""Isolated web-owner OAuth pairing: public S256 client, real PRP link & revoke.

Only runs after ci_pkce_browser.py has linked and revoked the initial synthetic
client; it verifies a separate browser pairing client using exact PRP SPA
callback. All credentials, authorization codes, tickets and JWTs are ephemeral.
No actual ChatGPT access, production Keycloak, server or user data involved.
"""
import json
import os
import ssl
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import Request
from urllib.error import HTTPError

import ci_pkce_browser as browser
from oauth_token_check import check_token

PUBLIC_PAIR_CLIENT = "ci-prp-browser-pairing"
PUBLIC_PAIR_REDIRECT = "https://prp-e2e.localhost/prp/me/mcp-clients"
PRP = "https://prp-e2e.localhost"
TOKEN_URL = browser.ISSUER + "/protocol/openid-connect/token"


def expect(response, status, stage):
    if response[0] != status:
        raise RuntimeError(stage + "_HTTP_" + str(response[0]))


def admin_token(opener):
    response = browser.request(opener,
        browser.ADMIN + "/realms/master/protocol/openid-connect/token",
        form=True, data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "prp-ci-admin",
            "password": os.environ["MCP_E2E_KC_ADMIN_PASSWORD"],
        })
    return browser.json_response(response, "BROWSER_PAIR_ADMIN_LOGIN")["access_token"]


def register_public_pairing_client(opener, admin):
    public_client = {
        "clientId": PUBLIC_PAIR_CLIENT,
        "name": "Disposable first-party browser identity pairing (PKCE only)",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "consentRequired": True,
        "fullScopeAllowed": False,
        "redirectUris": [PUBLIC_PAIR_REDIRECT],
        "webOrigins": [PRP],
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": ["prp.tasks.read"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "oauth2.device.authorization.grant.enabled": "false",
        },
        "protocolMappers": [{
            "name": "Exact PRP protected resource URI",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.custom.audience": browser.RESOURCE,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        }],
    }
    result = browser.request(opener,
        browser.ADMIN + "/admin/realms/prp-mcp/clients",
        bearer=admin, data=public_client)
    expect(result, 201, "PUBLIC_PAIR_CLIENT_CREATION")
    print("PASS PAIR: separate public PKCE-only client with exact SPA callback and CORS origin.")


def browser_token_exchange(opener, code, verifier):
    # An ordinary Python code exchange cannot prove WebKit can POST across
    # origins. Check the actual public client's token-endpoint CORS response.
    preflight = Request(TOKEN_URL, method="OPTIONS", headers={
        "Origin": PRP,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    try:
        with opener.open(preflight, timeout=15) as response:
            if response.status not in (200, 204):
                raise RuntimeError("PAIR_PREFLIGHT_HTTP_" + str(response.status))
            if response.headers.get("Access-Control-Allow-Origin") != PRP:
                raise RuntimeError("PAIR_PREFLIGHT_CORS_ORIGIN_UNAVAILABLE")
    except HTTPError as error:
        raise RuntimeError("PAIR_PREFLIGHT_HTTP_" + str(error.code)) from None

    payload = urlencode({
        "grant_type": "authorization_code",
        "client_id": PUBLIC_PAIR_CLIENT,
        "code": code,
        "redirect_uri": PUBLIC_PAIR_REDIRECT,
        "code_verifier": verifier,
        "resource": browser.RESOURCE,
    }).encode()
    request = Request(TOKEN_URL, method="POST", data=payload, headers={
        "Origin": PRP,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError("PAIR_BROWSER_TOKEN_HTTP_" + str(response.status))
            if response.headers.get("Access-Control-Allow-Origin") != PRP:
                raise RuntimeError("PAIR_BROWSER_TOKEN_CORS_ORIGIN_UNAVAILABLE")
            raw = response.read(50001)
    except HTTPError as error:
        raise RuntimeError("PAIR_BROWSER_TOKEN_HTTP_" + str(error.code)) from None
    if len(raw) > 50000:
        raise RuntimeError("PAIR_BROWSER_TOKEN_RESPONSE_TOO_LARGE")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise RuntimeError("PAIR_BROWSER_TOKEN_RESPONSE_INVALID")
    print("PASS PAIR: CORS preflight and token response allow exact PRP Web origin.")
    return doc


def run():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("DISPOSABLE_CI_ONLY")
    if os.environ.get("MCP_E2E_CRUD") == "true":
        raise RuntimeError("PUBLIC_PAIRING_REQUIRES_READONLY_STACK")
    opener = browser.build_opener(
        browser.HTTPSHandler(context=ssl.create_default_context(cafile=os.environ["MCP_E2E_CA_CERT"])),
        browser.HTTPCookieProcessor(CookieJar()), browser.SafeRedirect(),
    )
    browser.wait_ready(opener, browser.ISSUER + "/.well-known/openid-configuration")
    register_public_pairing_client(opener, admin_token(opener))

    owner_password = os.environ["MCP_E2E_PRP_PASSWORD"]
    login = browser.json_response(browser.request(opener, PRP + "/api/auth/login",
        data={"username": "stage_admin", "password": owner_password}), "PRP_OWNER")
    prp_bearer = login["data"]["token"]
    # To prove FIRST-TIME binding, remove the previous isolated test link. The
    # entire MySQL store and user are synthetic and discarded on job exit.
    browser.json_response(browser.request(opener, PRP + "/api/mcp/identity/unlink",
        bearer=prp_bearer, data={"password": owner_password}), "PRP_UNLINK")
    initial = browser.json_response(browser.request(opener, PRP + "/api/mcp/identity",
        bearer=prp_bearer), "PRP_UNLINK_VERIFY")
    if initial.get("data"):
        raise RuntimeError("PAIR_FIRST_LINK_PRECONDITION")
    grant = browser.json_response(browser.request(opener, PRP + "/api/mcp/clients/pairing",
        bearer=prp_bearer, data={
            "clientId": PUBLIC_PAIR_CLIENT, "password": owner_password,
        }), "PUBLIC_PAIR_OWNER_GRANT")
    if grant.get("data", {}).get("status") != "ACTIVE":
        raise RuntimeError("PAIR_CLIENT_OWNER_GRANT_UNAVAILABLE")
    ticket = browser.json_response(browser.request(opener,
        PRP + "/api/mcp/identity/tickets", bearer=prp_bearer,
        data={"clientId": PUBLIC_PAIR_CLIENT, "password": owner_password}),
        "PUBLIC_PAIR_TICKET").get("data", {}).get("code")
    if not isinstance(ticket, str) or len(ticket) != 43:
        raise RuntimeError("PUBLIC_PAIR_TICKET_INVALID")

    # Same browser-shaped Keycloak flow used by PRP's Vue pairing wizard. The
    # SafeRedirect captures the HTTPS SPA callback without fetching any app
    # code or printing the authorization URL/query.
    browser.CLIENT = PUBLIC_PAIR_CLIENT
    browser.CALLBACK = PUBLIC_PAIR_REDIRECT
    code, verifier = browser.code_pkce(opener, "e2e-keycloak-owner",
        os.environ["MCP_E2E_KC_USER_PASSWORD"])
    token_doc = browser_token_exchange(opener, code, verifier)
    token = token_doc.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("PUBLIC_PAIR_ACCESS_TOKEN_UNAVAILABLE")
    jwks = browser.json_response(browser.request(opener,
        browser.ISSUER + "/protocol/openid-connect/certs"), "PUBLIC_PAIR_JWKS")
    check_token(token, jwks, issuer=browser.ISSUER,
        resource=browser.RESOURCE, client_id=PUBLIC_PAIR_CLIENT)
    print("PASS PAIR: real user consent, public S256 code exchange, signed MCP URI audience.")

    before = browser.jsonrpc(opener, token, 91, "tools/list", {})
    expect(before, 401, "UNLINKED_PAIR_TOKEN_DENIED")
    paired = browser.json_response(browser.request(opener,
        PRP + "/api/mcp/link", bearer=token, data={"ticket": ticket}),
        "FIRST_PARTY_BROWSER_LINK")
    if paired.get("data", {}).get("newlyLinked") is not True:
        raise RuntimeError("FIRST_PARTY_LINK_NOT_INSERTED")
    replay = browser.request(opener, PRP + "/api/mcp/link",
        bearer=token, data={"ticket": ticket})
    expect(replay, 409, "PAIR_TICKET_REPLAY")
    print("PASS PAIR: PRP owner ticket binds verified Keycloak issuer/sub and rejects replay.")

    browser.json_response(browser.request(opener, PRP + "/api/mcp/clients/revoke",
        bearer=prp_bearer, data={"clientId": PUBLIC_PAIR_CLIENT}), "PAIR_TEMP_GRANT_REVOKE")
    after = browser.jsonrpc(opener, token, 92, "tools/list", {})
    expect(after, 401, "PUBLIC_PAIR_CLIENT_REVOKED")
    links = browser.json_response(browser.request(opener, PRP + "/api/mcp/identity",
        bearer=prp_bearer), "LINK_SURVIVES_CLIENT_REVOKE")
    if len(links.get("data", [])) != 1:
        raise RuntimeError("IDENTITY_LINK_LOST_AFTER_TEMP_CLIENT_REVOKE")
    print("PASS PAIR: temporary public-client task permission revoked; identity link persists.")
    print("CI-ONLY: genuine ChatGPT connection, actual browser JavaScript and production Keycloak untested.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        reason = str(exc)
        if len(reason) > 120 or any(x in reason for x in (
            "https://", "http://", "token=", "Bearer", "password=", "?",
        )):
            reason = "ISOLATED_BROWSER_PAIR_UNVERIFIED"
        print("FAIL PAIR: " + reason)
        raise SystemExit(1) from None
