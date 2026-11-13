#!/usr/bin/env python3
"""Exact ChatGPT client-ID authcode/token/refresh test in DISPOSABLE Keycloak.

The official ChatGPT metadata's PUBLIC key URL cannot sign test assertions.
Only inside the short-lived GitHub CI realm we replace that client's remote
JWKS credential source with an ephemeral, local X.509 certificate. This is
a controlled TEST-KEY SUBSTITUTION, never an OpenAI signature verification.
No network request or OAuth callback is sent to chatgpt.com by this script.
Its exact client_id, redirect, protocol scopes, PKCE and public resource
stay unchanged. This script must never run against a live/host Keycloak.
"""
import json
import os
from pathlib import Path
import secrets
import tempfile
from urllib.parse import quote

import ci_chatgpt_cimd_pkce as cimd
import ci_jwt_authcode_refresh as e2e
from ci_static_client_jwt import create_keypair
from oauth_token_check import _b64url

CLIENT = cimd.CLIENT
CALLBACK = cimd.REDIRECT
RESOURCE = e2e.RESOURCE
SCOPE = "openid offline_access prp.tasks.read"


def assert_disposable():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or not os.environ.get("MCP_TEST_ADMIN_PASSWORD")
            or cimd.BASE != "http://127.0.0.1:18080"
            or not CLIENT.startswith("https://chatgpt.com/")):
        raise RuntimeError("REFUSED_NON_DISPOSABLE_KEYCLOAK")


def configure_exact_test_key(token, certificate):
    """Change credential source ONLY in the disposable Realm; no real JWKS."""
    url = cimd.REALM_ADMIN + "/clients?clientId=" + quote(CLIENT, safe="")
    status, _, raw = cimd.request(url, bearer=token)
    if status != 200:
        raise RuntimeError("EXACT_CLIENT_LOOKUP_HTTP_" + str(status))
    clients = json.loads(raw)
    matches = [v for v in clients if v.get("clientId") == CLIENT]
    if len(matches) != 1:
        raise RuntimeError("EXACT_CLIENT_ID_NOT_UNIQUE")
    key = matches[0].get("id")
    if not isinstance(key, str) or not key:
        raise RuntimeError("EXACT_CLIENT_INTERNAL_ID_MISSING")
    endpoint = cimd.REALM_ADMIN + "/clients/" + quote(key, safe="")
    client = cimd.read_json(endpoint, token)
    if (client.get("clientId") != CLIENT or client.get("redirectUris") != [CALLBACK]
            or client.get("publicClient") is not False
            or client.get("fullScopeAllowed") is not False
            or client.get("standardFlowEnabled") is not True
            or client.get("consentRequired") is not True
            or client.get("clientAuthenticatorType") != "client-jwt"):
        raise RuntimeError("EXACT_CLIENT_SECURITY_SHAPE_DRIFT")
    if client.get("optionalClientScopes") != ["prp.tasks.read", "offline_access"] and set(
            client.get("optionalClientScopes") or []) != {"prp.tasks.read", "offline_access"}:
        raise RuntimeError("EXACT_CLIENT_SCOPE_DRIFT")
    mappers = client.get("protocolMappers") or []
    audiences = [m.get("config", {}).get("included.custom.audience")
                 for m in mappers if m.get("protocolMapper") == "oidc-audience-mapper"]
    if audiences != [RESOURCE]:
        raise RuntimeError("EXACT_CLIENT_AUDIENCE_MAPPER_DRIFT")
    attrs = dict(client.get("attributes") or {})
    if attrs.get("jwks.url") != "https://chatgpt.com/oauth/jwks.json":
        raise RuntimeError("OFFICIAL_JWKS_REFERENCE_MISSING")
    # Synthetic key is private to this ephemeral container. Do not represent
    # passing this stage as verification of real OpenAI JWKS or private key.
    attrs["use.jwks.url"] = "false"
    attrs["jwt.credential.certificate"] = certificate
    attrs["token.endpoint.auth.signing.alg"] = "RS256"
    attrs["prp.ci.refresh-resource-guard"] = "enabled"
    # Remove URL to prevent deceptive claims that this test contacted OpenAI
    # keys. Exact pre-registration base config is tested by prior stage.
    attrs.pop("jwks.url", None)
    client["attributes"] = attrs
    cimd.replace_admin_doc(endpoint, token, client)
    readback = cimd.read_json(endpoint, token)
    actual_attrs = readback.get("attributes") or {}
    if (readback.get("clientId") != CLIENT or
            readback.get("redirectUris") != [CALLBACK] or
            readback.get("optionalClientScopes") is None or
            actual_attrs.get("use.jwks.url") != "false" or
            actual_attrs.get("jwt.credential.certificate") != certificate or
            actual_attrs.get("pkce.code.challenge.method") != "S256" or
            actual_attrs.get("prp.ci.refresh-resource-guard") != "enabled"):
        raise RuntimeError("EPHEMERAL_TEST_CERT_SUBSTITUTION_NOT_PERSISTED")
    print("PASS EXACT CI: official client ID/callback unchanged; synthetic signing key bound only in disposable Realm.")


def must_reject(status, label):
    if status not in (400, 401):
        raise RuntimeError(label + "_NOT_REJECTED_HTTP_" + str(status))


def validated_scope(tokens):
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise RuntimeError("SIGNED_ACCESS_TOKEN_MISSING")
    raw = json.loads(_b64url(access.split(".")[1]))
    granted = raw.get("scope")
    if not isinstance(granted, str):
        raise RuntimeError("ACCESS_TOKEN_SCOPE_MALFORMED")
    scopes = set(granted.split())
    if not {"prp.tasks.read"}.issubset(scopes):
        raise RuntimeError("ACCESS_TOKEN_TASK_SCOPE_MISSING")
    if any(v in scopes for v in (
        "prp.finance.read", "prp.wellness.read",
        "prp.write.create", "prp.write.update", "prp.write.confirm")):
        raise RuntimeError("ACCESS_TOKEN_EXCESSIVE_SCOPE")
    return scopes


def main():
    assert_disposable()
    # Prior stage verifies this exact pre-registered client ID and callback;
    # it also disables dynamic CIMD interception in this synthetic Realm.
    with tempfile.TemporaryDirectory(prefix="exact-chatgpt-ci-", dir=os.environ["RUNNER_TEMP"]) as work:
        key, certificate = create_keypair(Path(work))
        token = cimd.admin_token()
        e2e.configure_realm(token)
        configure_exact_test_key(token, certificate)
        # Use the exact same fixed client ID for every transaction. The
        # temporary signer is NOT a ChatGPT private key.
        e2e.CLIENT = CLIENT
        e2e.CALLBACK = CALLBACK
        e2e.SCOPE = SCOPE
        originals = e2e.activate_exact_refresh_policy(token)
        user_password = secrets.token_urlsafe(40)
        username = e2e.create_user(token, user_password)
        opener = e2e.browser_opener()
        # All negative grants use the SAME exact pre-registered client ID,
        # not the separate 'ci-authcode-private-jwt' regression client.
        wrong_code, unused_verifier = e2e.browser.code_pkce(
            opener, username, user_password, SCOPE)
        wrong_code_status, _ = e2e.exchange(
            opener, key, grant="authorization_code", code=wrong_code,
            verifier=secrets.token_urlsafe(48), client_id=CLIENT)
        must_reject(wrong_code_status, "EXACT_BAD_PKCE_VERIFIER")
        print("PASS EXACT CI: incorrect S256 code verifier rejected on exact client.")

        code, verifier = e2e.browser.code_pkce(opener, username, user_password, SCOPE)
        status, tokens = e2e.exchange(
            opener, key, grant="authorization_code", code=code,
            verifier=verifier, client_id=CLIENT)
        if status != 200 or not tokens:
            raise RuntimeError("EXACT_CODE_EXCHANGE_HTTP_" + str(status))
        status, _, jwks_bytes = cimd.request(e2e.ISSUER + "/protocol/openid-connect/certs")
        if status != 200:
            raise RuntimeError("EXACT_KEYCLOAK_JWKS_UNAVAILABLE")
        issuer_jwks = json.loads(jwks_bytes)
        subject = e2e.verify_access(tokens, issuer_jwks, client_id=CLIENT)
        validated_scope(tokens)
        first = tokens.get("refresh_token")
        if not isinstance(first, str) or len(first) < 16:
            raise RuntimeError("EXACT_OFFLINE_REFRESH_MISSING")
        print("PASS EXACT CI: real Keycloak user consent, code, S256, synthetic signed assertion, exact aud and task-read scope.")

        bad, _ = e2e.exchange(opener, key, grant="refresh_token",
                               refresh=first, bad_auth=True, client_id=CLIENT)
        must_reject(bad, "EXACT_BAD_SIGNATURE")
        for kind, resource, scope in (
            ("WRONG_RESOURCE", "https://not-prp.staging.example.org/api/mcp", SCOPE),
            ("EMPTY_RESOURCE", "", SCOPE),
            ("MISSING_RESOURCE", None, SCOPE),
            ("DUPLICATE_RESOURCE", [
                RESOURCE, "https://not-prp.staging.example.org/api/mcp"], SCOPE),
            ("FINANCE_SCOPE", RESOURCE, "openid offline_access prp.finance.read"),
        ):
            status, _ = e2e.exchange(opener, key, grant="refresh_token",
                                     refresh=first, resource=resource,
                                     scope=scope, client_id=CLIENT)
            must_reject(status, "EXACT_" + kind)
        status, tokens2 = e2e.exchange(
            opener, key, grant="refresh_token", refresh=first, client_id=CLIENT)
        if status != 200 or not tokens2:
            raise RuntimeError("EXACT_OFFLINE_REFRESH_HTTP_" + str(status))
        e2e.verify_access(tokens2, issuer_jwks, subject=subject, client_id=CLIENT)
        validated_scope(tokens2)
        second = tokens2.get("refresh_token")
        if not isinstance(second, str) or first == second or len(second) < 16:
            raise RuntimeError("EXACT_REFRESH_NOT_ROTATED")
        replay, _ = e2e.exchange(opener, key, grant="refresh_token",
                                 refresh=first, client_id=CLIENT)
        must_reject(replay, "EXACT_REFRESH_REPLAY")
        e2e.revoke(opener, key, second, client_id=CLIENT)
        post_revoke, _ = e2e.exchange(opener, key, grant="refresh_token",
                                     refresh=second, client_id=CLIENT)
        must_reject(post_revoke, "EXACT_REFRESH_AFTER_REVOKE")
        e2e.rollback_exact_refresh_policy(token, originals)
        print("PASS EXACT CI: task-only refresh, resource and scope denials, rotation, replay, revoke, policy rollback.")
        print("NOTE: DISPOSABLE_TEST_CERT_ONLY; REAL_CHATGPT_JWKS_ASSERTION=UNVERIFIED; LIVE_REALM=UNCHANGED.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc)
        if (len(reason) > 100 or any(part in reason.lower() for part in
                ("https://", "access_token", "password", "callback", "assertion"))):
            reason = "EXACT_CLIENT_CI_UNVERIFIED"
        print("FAIL EXACT CI: " + reason)
        raise SystemExit(1) from None
