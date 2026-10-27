#!/usr/bin/env python3
"""CI-only independent reproduction of the restored-clone password->refresh path.

Never used for production login. Ephemeral Keycloak on loopback only.
The host's restored Realm script executes the analogous flow inside a private
network with signed JWKS/audience assertions and automatic cleanup.
"""
import json
import os
import secrets
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

from ci_chatgpt_cimd_pkce import BASE, REALM_ADMIN, admin_token, read_json, replace_admin_doc, request
from ci_static_client_jwt import RESOURCE, ISSUER
from oauth_token_check import check_token, _b64url

CLIENT = "ci-restored-style-ro-password"
POLICY = "ci-ropc-refresh-policy"
PROFILE = "ci-ropc-refresh-profile"
ATTR = "prp.ci.refresh-resource-guard"
TOKEN = BASE + "/realms/prp-mcp/protocol/openid-connect/token"

def admin_call(path, token, *, method="GET", document=None):
    status, _, raw = request(REALM_ADMIN + path, method=method, bearer=token, json_body=document)
    if method in ("POST", "PUT", "DELETE"):
        if status not in (200, 201, 204):
            raise RuntimeError("CI_RESTORED_STYLE_ADMIN_STATUS_" + str(status))
        return None
    if status != 200:
        raise RuntimeError("CI_RESTORED_STYLE_READ_STATUS_" + str(status))
    return json.loads(raw)

def form_grant(data, *, revocation=False):
    endpoint = BASE + "/realms/prp-mcp/protocol/openid-connect/" + ("revoke" if revocation else "token")
    body = urlencode(data, doseq=True).encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    try:
        conn = build_opener(ProxyHandler({})).open(
            Request(endpoint, data=body, headers=headers, method="POST"), timeout=15)
    except HTTPError as err:
        conn = err
    with conn:
        code = conn.status
        content = conn.read(200001)
    if len(content) > 200000:
        raise RuntimeError("CI_RESTORED_STYLE_RESPONSE_OVERSIZE")
    if code != 200:
        # Return only a safe, finite RFC OAuth error code; never log the
        # error_description, user credentials, token or response body.
        try:
            error = json.loads(content).get("error")
        except (ValueError, TypeError, AttributeError):
            error = None
        allowed = {"invalid_grant", "invalid_scope", "invalid_request",
                   "invalid_target", "unauthorized_client", "invalid_client"}
        return code, {"error_kind": error if error in allowed else "UNCLASSIFIED"}
    return code, json.loads(content) if content else None

def main():
    global phase
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("DISPOSABLE_GITHUB_RUNNER_ONLY")
    phase = "ADMIN_TOKEN"
    token = admin_token()
    policies = read_json(REALM_ADMIN + "/client-policies/policies", token)
    profiles = read_json(REALM_ADMIN + "/client-policies/profiles", token)
    original_realm = read_json(REALM_ADMIN, token)
    client_id = None
    user_id = None
    username = "ci-ropc-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(36)
    try:
        phase = "CLIENT_CREATE"
        marker = json.dumps([{"key": ATTR, "value": "enabled"}], separators=(",", ":"))
        admin_call("/clients", token, method="POST", document={
            "clientId": CLIENT, "enabled": True, "protocol": "openid-connect",
            "publicClient": True, "standardFlowEnabled": False,
            "implicitFlowEnabled": False, "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": False, "fullScopeAllowed": False,
            "redirectUris": [], "webOrigins": [],
            "defaultClientScopes": ["basic"],
            "optionalClientScopes": ["prp.tasks.read"], "attributes": {ATTR: "enabled"},
            "protocolMappers": [{"name": "CI restored-style MCP audience",
                "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                "config": {"included.custom.audience": RESOURCE,
                           "id.token.claim": "false", "access.token.claim": "true"}}],
        })
        phase = "CLIENT_READBACK"
        identities = admin_call("/clients?clientId=" + CLIENT, token)
        exact = [c for c in identities if c.get("clientId") == CLIENT]
        assert len(exact) == 1
        client_id = exact[0]["id"]
        phase = "PROFILE_INSTALL"
        admin_call("/client-policies/profiles", token, method="PUT", document={
            "profiles": profiles["profiles"] + [{"name": PROFILE, "executors": [
                {"executor": "prp-ci-refresh-resource-guard", "configuration": {
                    "target-client-id": CLIENT, "allowed-resource": RESOURCE}}]}],
        })
        phase = "POLICY_INSTALL"
        admin_call("/client-policies/policies", token, method="PUT", document={
            "policies": policies["policies"] + [{"name": POLICY, "enabled": True,
                "conditions": [{"condition": "client-attributes",
                    "configuration": {"attributes": marker}}],
                "profiles": [PROFILE]}],
        })
        phase = "POLICY_READBACK"
        p = admin_call("/client-policies/policies", token)
        assert len([x for x in p["policies"] if x.get("name") == POLICY and x.get("enabled")]) == 1
        conf = admin_call("/client-policies/profiles", token)
        assert len([x for x in conf["profiles"] if x.get("name") == PROFILE]) == 1
        phase = "ROTATION_REALM_UPDATE"
        admin_call("", token, method="PUT", document={
            **original_realm, "revokeRefreshToken": True, "refreshTokenMaxReuse": 0,
        })
        phase = "ROTATION_REALM_READBACK"
        new_realm = read_json(REALM_ADMIN, token)
        assert new_realm.get("revokeRefreshToken") is True
        assert new_realm.get("refreshTokenMaxReuse") == 0
        phase = "TEST_USER_CREATE"
        admin_call("/users", token, method="POST", document={
            "username": username, "enabled": True, "emailVerified": True,
            "email": username + "@example.invalid",
            "firstName": "Disposable", "lastName": "Refresh CI",
            "requiredActions": [],
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        })
        phase = "TEST_USER_READBACK"
        found = admin_call("/users?username=" + username + "&exact=true", token)
        matches = [x for x in found if x.get("username") == username]
        assert len(matches) == 1
        user_id = matches[0]["id"]
        phase = "JWKS_READBACK"
        status, _, raw = request(ISSUER + "/protocol/openid-connect/certs")
        assert status == 200
        jwks = json.loads(raw)

        def verify(result):
            bearer = result["access_token"]
            try:
                check_token(bearer, jwks, issuer=ISSUER, resource=RESOURCE,
                            client_id=CLIENT, required_scope="prp.tasks.read")
            except ValueError as failure:
                # Only exact diagnostic strings authored in our own verifier.
                categories = {
                    "JWT audience must contain exact MCP resource": "AUDIENCE_MISSING",
                    "Required OAuth task-read scope missing": "TASK_SCOPE_MISSING",
                    "JWT signed OAuth client mismatch": "CLIENT_MISMATCH",
                    "Conflicting signed OAuth client claims": "CLIENT_CLAIMS_CONFLICT",
                    "JWT issuer mismatch": "ISSUER_MISMATCH",
                    "JWT RS256 signature failed": "JWT_SIGNATURE_FAILED",
                    "Unknown or ambiguous JWKS signing key": "JWKS_KEY_NOT_FOUND",
                    "Unacceptable OAuth RSA signing key": "JWKS_KEY_INVALID",
                    "Invalid RSA signature length": "JWT_SIGNATURE_LENGTH",
                    "Expired or missing OAuth access token": "JWT_EXPIRY",
                    "Future or missing OAuth issue time": "JWT_ISSUED_AT",
                    "Expected trusted RS256 access token": "JWT_ALGORITHM",
                    "Malformed compact access token": "JWT_FORMAT",
                    "Malformed JWT claims": "JWT_CLAIMS_FORMAT",
                    "Malformed OAuth JWKS": "JWKS_FORMAT",
                    "JWT subject missing": "JWT_SUBJECT",
                    "Invalid external OAuth access token or JWKS": "JWT_INVALID_FIELDS",
                }
                print("CLONE_STYLE_JWT_DIAGNOSTIC=" + categories.get(str(failure), "OTHER_SIGNED_JWT_FAILURE"))
                raise
            claims = json.loads(_b64url(bearer.split(".")[1]))
            assert claims["sub"] == user_id
            assert "prp.finance.read" not in claims.get("scope", "").split()

        phase = "INITIAL_TOKEN_GRANT"
        status, issued = form_grant({
            "grant_type": "password", "client_id": CLIENT,
            "username": username, "password": password,
            "scope": "openid prp.tasks.read", "resource": RESOURCE,
        })
        if status != 200:
            print("CLONE_STYLE_INITIAL_GRANT_DIAGNOSTIC=" + issued["error_kind"])
            raise RuntimeError("CI_RESTORED_STYLE_PASSWORD_GRANT_HTTP_" + str(status))
        phase = "INITIAL_GRANT_RESPONSE_SHAPE"
        if not isinstance(issued, dict) or not isinstance(issued.get("access_token"), str):
            raise RuntimeError("CI_RESTORED_STYLE_MISSING_ACCESS_TOKEN")
        phase = "INITIAL_SIGNED_TOKEN_VERIFY"
        verify(issued)
        phase = "INITIAL_REFRESH_TOKEN_READ"
        first = issued["refresh_token"]

        def refresh(rt, *, resource=RESOURCE, scope="openid prp.tasks.read"):
            data = {"grant_type": "refresh_token", "client_id": CLIENT,
                    "refresh_token": rt, "scope": scope}
            if resource is not None:
                data["resource"] = resource
            return form_grant(data)

        phase = "NEGATIVE_RESOURCE"
        # Positive lifecycle first: negative token-grant attempts may revoke
        # the source token in some Keycloak grant paths. Never classify a
        # consumed token as failed canonical resource enforcement.
        phase = "CANONICAL_REFRESH"
        code, renewed = refresh(first)
        if code != 200:
            print("CLONE_STYLE_CANONICAL_REFRESH_DIAGNOSTIC=" + renewed["error_kind"])
            raise RuntimeError("CI_RESTORED_STYLE_CANONICAL_REFRESH_HTTP_" + str(code))
        verify(renewed)
        second = renewed["refresh_token"]
        assert second != first
        old, _ = refresh(first)
        assert old in (400, 401)
        phase = "REVOKE"
        revoke, _ = form_grant({"client_id": CLIENT, "token": second,
                                "token_type_hint": "refresh_token"}, revocation=True)
        assert revoke == 200
        blocked, _ = refresh(second)
        assert blocked in (400, 401)

        phase = "NEGATIVE_RESOURCE"
        cases = [
            ("foreign", "https://unrelated.example.test/api/mcp", "openid prp.tasks.read"),
            ("duplicate", [RESOURCE, RESOURCE], "openid prp.tasks.read"),
            ("blank", "", "openid prp.tasks.read"),
            ("finance", RESOURCE, "openid prp.finance.read"),
        ]
        for category, requested, requested_scope in cases:
            # Each rejection has a separate synthetic authorization/session,
            # so a failed refresh cannot invalidate the positive test.
            phase = "NEGATIVE_" + category.upper() + "_NEW_GRANT"
            code, fresh = form_grant({
                "grant_type": "password", "client_id": CLIENT,
                "username": username, "password": password,
                "scope": "openid prp.tasks.read", "resource": RESOURCE,
            })
            if code != 200:
                raise RuntimeError("CI_RESTORED_STYLE_NEGATIVE_FIXTURE_GRANT_HTTP_" + str(code))
            phase = "NEGATIVE_" + category.upper() + "_JWT_VERIFY"
            verify(fresh)
            phase = "NEGATIVE_" + category.upper() + "_REFRESH"
            bad, _ = refresh(fresh["refresh_token"], resource=requested, scope=requested_scope)
            if bad not in (400, 401):
                print("CLONE_STYLE_UNAPPROVED_RESOURCE_RESPONSE_STATUS=" + str(bad))
                raise RuntimeError("CI_RESTORED_STYLE_NEGATIVE_" + category.upper() + "_ACCEPTED")
        # RFC8707 allows resource omission. For a public client the
        # Keycloak refresh grant may infer the original canonical resource.
        # If it succeeds, demand an independently signed MCP-only token,
        # unchanged user/scope and real refresh rotation; never call this a
        # strict missing-resource denial.
        phase = "OMITTED_RESOURCE_COMPATIBILITY"
        status, fresh = form_grant({
            "grant_type": "password", "client_id": CLIENT,
            "username": username, "password": password,
            "scope": "openid prp.tasks.read", "resource": RESOURCE,
        })
        if status != 200:
            raise RuntimeError("CI_RESTORED_STYLE_OMITTED_FIXTURE_GRANT_HTTP_" + str(status))
        verify(fresh)
        code, omitted_result = refresh(fresh["refresh_token"], resource=None)
        if code == 200:
            verify(omitted_result)
            assert omitted_result["refresh_token"] != fresh["refresh_token"]
            old_status, _ = refresh(fresh["refresh_token"])
            assert old_status in (400, 401)
            revoke_status, _ = form_grant({
                "client_id": CLIENT, "token": omitted_result["refresh_token"],
                "token_type_hint": "refresh_token"}, revocation=True)
            assert revoke_status == 200
            denied_status, _ = refresh(omitted_result["refresh_token"])
            assert denied_status in (400, 401)
            print("PASS CLONE-STYLE: omitted resource remains signed canonical-audience only.")
        elif code in (400, 401):
            print("PASS CLONE-STYLE: omitted resource explicitly rejected.")
        else:
            raise RuntimeError("CI_RESTORED_STYLE_OMITTED_RESOURCE_UNEXPECTED_HTTP_" + str(code))
        phase = "PASS"
        print("PASS CLONE-STYLE: signed password-grant resource JWT, foreign/duplicate/blank resource denial.")
        print("PASS CLONE-STYLE: authenticated refresh rotation, replay refusal and revocation.")
    finally:
        if user_id:
            admin_call("/users/" + user_id, token, method="DELETE")
        admin_call("", token, method="PUT", document=original_realm)
        admin_call("/client-policies/policies", token, method="PUT", document=policies)
        admin_call("/client-policies/profiles", token, method="PUT", document=profiles)
        if client_id:
            admin_call("/clients/" + client_id, token, method="DELETE")
        assert read_json(REALM_ADMIN + "/client-policies/policies", token) == policies
        assert read_json(REALM_ADMIN + "/client-policies/profiles", token) == profiles
        print("PASS CLONE-STYLE: Realm, policy, client and user cleanup complete.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print secrets, external exception text, or response bodies.
        # Use the fixed phase name from our own test, not any remote data.
        phase = locals().get("phase", "UNKNOWN")
        print("CLONE_STYLE_FAILURE_PHASE=" + phase)
        msg = str(exc)
        if msg.startswith("CI_RESTORED_STYLE_") and msg.rsplit("_",1)[-1].isdigit():
            print("FAIL CLONE-STYLE: " + msg)
        else:
            print("FAIL CLONE-STYLE: UNCLASSIFIED")
        raise SystemExit(1) from None
