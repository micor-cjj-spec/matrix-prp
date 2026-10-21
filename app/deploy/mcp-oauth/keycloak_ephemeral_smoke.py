#!/usr/bin/env python3
"""Verify an ephemeral, loopback-only Keycloak staging instance.

Runs only in a disposable CI runner against http://127.0.0.1:18080.
Does not use PRP accounts, production OAuth credentials or real user data.
"""
import argparse
import json
import secrets
import urllib.error
from oauth_token_check import check_token
import os
import time
import urllib.error
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:18080"
RESOURCE = "https://prp.staging.example.org/api/mcp"
CLIENT_ID = "prp-pkce-probe"
CALLBACK = "http://127.0.0.1:8765/callback"


def request_json(url, form=None, bearer=None):
    if not url.startswith(BASE + "/"):
        raise ValueError("Only loopback Keycloak CI host is allowed")
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = Request(url, headers=headers, data=body)
    with urlopen(request, timeout=8) as response:
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError("Keycloak response size exceeded")
    return json.loads(payload)


def admin_create_client(admin_access, client_id, client_secret):
    """Create a disposable client ONLY in the CI Keycloak realm."""
    url = BASE + "/admin/realms/prp-mcp/clients"
    payload = {
        "clientId": client_id,
        "name": "Disposable OAuth resource-audience verification only",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "secret": client_secret,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "implicitFlowEnabled": False,
        "optionalClientScopes": ["prp.tasks.read"],
        "protocolMappers": [{
            "name": "PRP MCP resource audience - CI service client",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": "matrix-prp-mcp-resource",
                "id.token.claim": "false",
                "access.token.claim": "true"
            }
        }]
    }
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": "Bearer " + admin_access,
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 201:
                raise RuntimeError("Ephemeral Keycloak test client registration failed")
    except urllib.error.HTTPError:
        raise RuntimeError("Ephemeral Keycloak test client registration rejected") from None


def assert_invalid_target(token_endpoint, client_id, client_secret):
    """Incorrect resource URI must NEVER produce a usable access token."""
    try:
        request_json(token_endpoint, {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "prp.tasks.read",
            "resource": "https://not-prp.staging.example.org/api/mcp",
        })
    except urllib.error.HTTPError as error:
        if error.code != 400:
            raise RuntimeError("Wrong-resource token did not reject with HTTP 400") from None
        return
    raise RuntimeError("Keycloak accepted an unregistered protected resource")


def verify_real_issued_token(metadata, jwks, admin_access):
    """Obtain and cryptographically verify a genuine CI-only Keycloak bearer.

    Tests service-account grant for resource/audience compatibility.
    This does NOT substitute for the manual browser PKCE grant flow.
    """
    client_id = "prp-mcp-ci-audience"
    client_secret = secrets.token_urlsafe(40)
    admin_create_client(admin_access, client_id, client_secret)
    endpoint = BASE + "/realms/prp-mcp/protocol/openid-connect/token"
    issued = request_json(endpoint, {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "prp.tasks.read",
        "resource": RESOURCE,
    })
    bearer = issued.get("access_token")
    if not isinstance(bearer, str) or not bearer:
        raise RuntimeError("Keycloak returned no CI OAuth access token")
    result = check_token(bearer, jwks, issuer=metadata["issuer"], resource=RESOURCE,
                         client_id=client_id)
    assert_invalid_target(endpoint, client_id, client_secret)
    # Never print/save token, secret or decoded personal claim contents.
    return result


def wait_for_realm(seconds=180):
    metadata = BASE + "/realms/prp-mcp/.well-known/openid-configuration"
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            return request_json(metadata)
        except (OSError, urllib.error.HTTPError, ValueError):
            time.sleep(3)
    raise RuntimeError("Disposable Keycloak realm failed to initialize")


def find_client(clients, client_id):
    found = [c for c in clients if c.get("clientId") == client_id]
    if len(found) != 1:
        raise AssertionError(f"Expected exactly one client named {client_id}")
    return found[0]


def validate_keycloak(metadata, jwks, resource_client, pkce_client, optional_scope_names):
    # In the disposable runner only, Keycloak uses HTTP loopback.
    if metadata.get("issuer") != BASE + "/realms/prp-mcp":
        raise AssertionError("Keycloak did not publish the expected staging-only issuer")
    if "S256" not in metadata.get("code_challenge_methods_supported", []):
        raise AssertionError("PKCE S256 not advertised")
    for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        uri = metadata.get(name, "")
        if not isinstance(uri, str) or not uri.startswith(BASE + "/"):
            raise AssertionError(f"Untrusted Keycloak {name}")
    if not any(k.get("kty") == "RSA" and k.get("n") and k.get("e")
               for k in jwks.get("keys", [])):
        raise AssertionError("JWKS did not include an RSA public signing key")
    if resource_client.get("attributes", {}).get("resource_url") != RESOURCE:
        raise AssertionError("Protected-resource URL does not match expected audience")
    if not resource_client.get("bearerOnly"):
        raise AssertionError("Protected-resource client must be bearer-only")
    if pkce_client.get("redirectUris") != [CALLBACK]:
        raise AssertionError("Staging public client's exact callback differs")
    if pkce_client.get("attributes", {}).get("pkce.code.challenge.method") != "S256":
        raise AssertionError("Staging public client lacks S256 enforcement")
    if not pkce_client.get("publicClient") or not pkce_client.get("consentRequired"):
        raise AssertionError("Public client must require user consent")
    if pkce_client.get("directAccessGrantsEnabled"):
        raise AssertionError("Password grant must remain disabled")
    if "prp.tasks.read" not in optional_scope_names:
        raise AssertionError("Read-only task scope is not enabled for staging OAuth client")
    if any(s.startswith("prp.write.") for s in optional_scope_names):
        raise AssertionError("CI public client must not have optional write scopes")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-user", default="prp-smoke-admin")
    args = parser.parse_args()
    password = os.environ.get("MCP_TEST_ADMIN_PASSWORD")
    if not password or len(password) < 24:
        raise RuntimeError("Ephemeral Keycloak admin secret was not supplied")

    metadata = wait_for_realm()
    jwks_uri = metadata["jwks_uri"]
    jwks = request_json(jwks_uri)

    # Admin CLI password grant used only on disposable Keycloak's master realm,
    # never as an MCP client or PRP owner authentication mechanism.
    session = request_json(BASE + "/realms/master/protocol/openid-connect/token", {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": args.admin_user,
        "password": password,
    })
    access = session.get("access_token")
    if not isinstance(access, str) or not access:
        raise RuntimeError("Disposable Keycloak admin token unavailable")
    clients_uri = BASE + "/admin/realms/prp-mcp/clients"
    clients = request_json(clients_uri, bearer=access)
    resource_client = find_client(clients, "matrix-prp-mcp-resource")
    pkce_client = find_client(clients, CLIENT_ID)
    pkce_id = pkce_client["id"]
    optional = request_json(clients_uri + "/" + pkce_id + "/optional-client-scopes",
                            bearer=access)
    scopes = {s.get("name") for s in optional}
    defaults = request_json(clients_uri + "/" + pkce_id + "/default-client-scopes", bearer=access)
    if "basic" not in {item.get("name") for item in defaults}:
        raise RuntimeError("PKCE client missing Keycloak 25+ Subject (sub) basic scope")
    validate_keycloak(metadata, jwks, resource_client, pkce_client, scopes)
    verified = verify_real_issued_token(metadata, jwks, access)
    print("PASS: real Keycloak signed", verified["signature"],
          "access token with exact MCP resource audience and read scope.")
    print("PASS: wrong resource rejected with invalid_target HTTP 400.")
    print("PASS: live disposable Keycloak OIDC discovery/JWKS/PKCE and exact MCP resource registered.")
    print("PASS: staging browser client is read-only, consent-required, and has an exact callback.")
    print("No OAuth tokens, passwords or protected PRP user data were printed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never include exception causes/responses that might contain
        # admin access tokens or credentials in public CI output.
        raise SystemExit("Disposable Keycloak smoke failed; inspect realm and CI health safely.") from None
