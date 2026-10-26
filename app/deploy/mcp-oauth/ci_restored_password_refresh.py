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
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("DISPOSABLE_GITHUB_RUNNER_ONLY")
    token = admin_token()
    policies = read_json(REALM_ADMIN + "/client-policies/policies", token)
    profiles = read_json(REALM_ADMIN + "/client-policies/profiles", token)
    original_realm = read_json(REALM_ADMIN, token)
    client_id = None
    user_id = None
    username = "ci-ropc-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(36)
    try:
        marker = json.dumps([{"key": ATTR, "value": "enabled"}], separators=(",", ":"))
        admin_call("/clients", token, method="POST", document={
            "clientId": CLIENT, "enabled": True, "protocol": "openid-connect",
            "publicClient": True, "standardFlowEnabled": False,
            "implicitFlowEnabled": False, "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": False, "fullScopeAllowed": False,
            "redirectUris": [], "webOrigins": [],
            "optionalClientScopes": ["prp.tasks.read"], "attributes": {ATTR: "enabled"},
            "protocolMappers": [{"name": "CI restored-style MCP audience",
                "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                "config": {"included.custom.audience": RESOURCE,
                           "id.token.claim": "false", "access.token.claim": "true"}}],
        })
        identities = admin_call("/clients?clientId=" + CLIENT, token)
        exact = [c for c in identities if c.get("clientId") == CLIENT]
        assert len(exact) == 1
        client_id = exact[0]["id"]
        admin_call("/client-policies/profiles", token, method="PUT", document={
            "profiles": profiles["profiles"] + [{"name": PROFILE, "executors": [
                {"executor": "prp-ci-refresh-resource-guard", "configuration": {
                    "target-client-id": CLIENT, "allowed-resource": RESOURCE}}]}],
        })
        admin_call("/client-policies/policies", token, method="PUT", document={
            "policies": policies["policies"] + [{"name": POLICY, "enabled": True,
                "conditions": [{"condition": "client-attributes",
                    "configuration": {"attributes": marker}}],
                "profiles": [PROFILE]}],
        })
        p = admin_call("/client-policies/policies", token)
        assert len([x for x in p["policies"] if x.get("name") == POLICY and x.get("enabled")]) == 1
        conf = admin_call("/client-policies/profiles", token)
        assert len([x for x in conf["profiles"] if x.get("name") == PROFILE]) == 1
        admin_call("", token, method="PUT", document={
            **original_realm, "revokeRefreshToken": True, "refreshTokenMaxReuse": 0,
        })
        new_realm = read_json(REALM_ADMIN, token)
        assert new_realm.get("revokeRefreshToken") is True
        assert new_realm.get("refreshTokenMaxReuse") == 0
        admin_call("/users", token, method="POST", document={
            "username": username, "enabled": True, "emailVerified": True,
            "email": username + "@example.invalid",
            "firstName": "Disposable", "lastName": "Refresh CI",
            "requiredActions": [],
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        })
        found = admin_call("/users?username=" + username + "&exact=true", token)
        matches = [x for x in found if x.get("username") == username]
        assert len(matches) == 1
        user_id = matches[0]["id"]
        status, _, raw = request(ISSUER + "/protocol/openid-connect/certs")
        assert status == 200
        jwks = json.loads(raw)

        def verify(result):
            bearer = result["access_token"]
            check_token(bearer, jwks, issuer=ISSUER, resource=RESOURCE,
                        client_id=CLIENT, required_scope="prp.tasks.read")
            claims = json.loads(_b64url(bearer.split(".")[1]))
            assert claims["sub"] == user_id
            assert "prp.finance.read" not in claims.get("scope", "").split()

        status, issued = form_grant({
            "grant_type": "password", "client_id": CLIENT,
            "username": username, "password": password,
            "scope": "openid prp.tasks.read", "resource": RESOURCE,
        })
        if status != 200:
            print("CLONE_STYLE_INITIAL_GRANT_DIAGNOSTIC=" + issued["error_kind"])
            raise RuntimeError("CI_RESTORED_STYLE_PASSWORD_GRANT_HTTP_" + str(status))
        verify(issued)
        first = issued["refresh_token"]

        def refresh(rt, *, resource=RESOURCE, scope="openid prp.tasks.read"):
            data = {"grant_type": "refresh_token", "client_id": CLIENT,
                    "refresh_token": rt, "scope": scope}
            if resource is not None:
                data["resource"] = resource
            return form_grant(data)

        for resource in ("https://unrelated.example.test/api/mcp",
                         [RESOURCE, RESOURCE], None, ""):
            bad, _ = refresh(first, resource=resource)
            if bad not in (400, 401):
                raise RuntimeError("CI_RESTORED_STYLE_WRONG_RESOURCE_ACCEPTED")
        bad, _ = refresh(first, scope="openid prp.finance.read")
        if bad not in (400, 401):
            raise RuntimeError("CI_RESTORED_STYLE_UNGRANTED_SCOPE")
        code, renewed = refresh(first)
        if code != 200:
            raise RuntimeError("CI_RESTORED_STYLE_CANONICAL_REFRESH_HTTP_" + str(code))
        verify(renewed)
        second = renewed["refresh_token"]
        assert second != first
        old, _ = refresh(first)
        assert old in (400, 401)
        revoke, _ = form_grant({"client_id": CLIENT, "token": second,
                                "token_type_hint": "refresh_token"}, revocation=True)
        assert revoke == 200
        blocked, _ = refresh(second)
        assert blocked in (400, 401)
        print("PASS CLONE-STYLE: signed password-grant resource JWT, wrong/duplicate/missing resource denial.")
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
        # Avoid printing arbitrary assertion/Keycloak bodies and bearer tokens.
        msg = str(exc)
        if msg.startswith("CI_RESTORED_STYLE_") and msg.rsplit("_",1)[-1].isdigit():
            print("FAIL CLONE-STYLE: " + msg)
        else:
            print("FAIL CLONE-STYLE: UNCLASSIFIED")
        raise SystemExit(1) from None
