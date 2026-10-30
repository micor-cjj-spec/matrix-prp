#!/usr/bin/env python3
"""Disposable Keycloak CI only: static JWKS client-jwt token-endpoint proof.

Requires TEST_KEYCLOAK_BASE (loopback URL), TEST_ADMIN_TOKEN and
TEST_REALM (disposable realm). Does not access PRP staging or production.
Run inside the existing isolated CI job, not on a live realm.
"""
import base64
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import subprocess
from urllib.error import HTTPError

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def request(url, method="GET", body=None, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif body is not None:
        data = urllib.parse.urlencode(body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        data = None
    try:
        response = urllib.request.urlopen(urllib.request.Request(
            url, data=data, headers=headers, method=method), timeout=12)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read(10000)


def main():
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("REFUSED: disposable GitHub CI only")
    base = os.environ["TEST_KEYCLOAK_BASE"].rstrip("/")
    if not (base.startswith("http://127.0.0.1:") or base.startswith("http://localhost:")):
        raise SystemExit("REFUSED: Keycloak must be loopback")
    realm = os.environ["TEST_REALM"]
    if realm != "prp-mcp":
        raise SystemExit("REFUSED: expected disposable prp-mcp realm")
    container = os.environ.get("TEST_KEYCLOAK_CONTAINER")
    if container != "prp-mcp-keycloak-ci":
        raise SystemExit("REFUSED: disposable CI container not identified")
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Name}}|{{.State.Running}}", container],
        capture_output=True, text=True, timeout=8, check=False)
    if result.returncode != 0 or result.stdout.strip() != "/prp-mcp-keycloak-ci|true":
        raise SystemExit("REFUSED: disposable CI container unavailable")
    token = os.environ["TEST_ADMIN_TOKEN"]
    client_id = "prp-static-jwks-ci-" + secrets.token_hex(8)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private.public_key().public_numbers()
    kid = "ci-" + secrets.token_hex(8)
    jwk = {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": kid,
           "n": b64(pub.n.to_bytes((pub.n.bit_length()+7)//8, "big")),
           "e": b64(pub.e.to_bytes((pub.e.bit_length()+7)//8, "big"))}
    admin = base + "/admin/realms/" + realm + "/clients"
    endpoint = base + "/realms/" + realm + "/protocol/openid-connect/token"
    client = {"clientId": client_id, "enabled": True, "protocol": "openid-connect",
              "publicClient": False, "clientAuthenticatorType": "client-jwt",
              "serviceAccountsEnabled": True, "standardFlowEnabled": False,
              "directAccessGrantsEnabled": False,
              "attributes": {"use.jwks.url": "false", "use.jwks.string": "true",
                             "jwks.string": json.dumps({"keys": [jwk]})}}
    status, headers, _ = request(admin, "POST", client, token)
    if status != 201:
        raise RuntimeError("CI_CLIENT_CREATE_FAILED_" + str(status))
    location = headers.get("Location", "")
    if not location.startswith(admin + "/"):
        raise RuntimeError("CI_CLIENT_LOCATION_UNEXPECTED")

    def assertion(key, keyid=kid, aud=endpoint, exp_offset=120):
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT", "kid": keyid}
        claims = {"iss": client_id, "sub": client_id, "aud": aud,
                  "iat": now, "nbf": now, "exp": now + exp_offset,
                  "jti": secrets.token_urlsafe(18)}
        msg = b64(json.dumps(header).encode()) + "." + b64(json.dumps(claims).encode())
        sig = key.sign(msg.encode(), padding.PKCS1v15(), hashes.SHA256())
        return msg + "." + b64(sig)

    def probe(label, jwt, expect_success):
        status, _, raw = request(endpoint, "POST", {
            "grant_type": "client_credentials", "client_id": client_id,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": jwt})
        if expect_success:
            if status != 200 or "access_token" not in json.loads(raw):
                raise RuntimeError(label + "_FAILED_HTTP_" + str(status))
        elif status == 200 or status < 400:
            raise RuntimeError(label + "_UNEXPECTED_ACCEPT_HTTP_" + str(status))
        print("PASS " + label + " HTTP_" + str(status))

    try:
        probe("VALID_STATIC_JWKS", assertion(private), True)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        probe("WRONG_SIGNATURE", assertion(other), False)
        probe("WRONG_KID", assertion(private, keyid="unknown"), False)
        probe("WRONG_AUDIENCE", assertion(private, aud=base + "/invalid"), False)
        probe("EXPIRED_ASSERTION", assertion(private, exp_offset=-60), False)
    finally:
        status, _, _ = request(location, "DELETE", token=token)
        if status != 204:
            raise RuntimeError("CI_CLIENT_CLEANUP_FAILED_" + str(status))
    print("STATIC_JWKS_TOKEN_ENDPOINT_PROOF=PASS")


if __name__ == "__main__":
    main()
