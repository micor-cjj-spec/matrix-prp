#!/usr/bin/env python3
"""Disposable-only Keycloak Signed JWT client-authentication regression.

Uses a unique CI-only client (NOT ChatGPT's client ID) and a temporary RSA
private key generated inside the GitHub runner. Never handles user identities,
browser grants, refresh tokens, production credentials or actual ChatGPT JWTs.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from ci_chatgpt_cimd_pkce import BASE, REALM_ADMIN, request, admin_token
from keycloak_ephemeral_smoke import RESOURCE
from oauth_token_check import check_token

CLIENT = "ci-static-private-key-jwt"
ISSUER = BASE + "/realms/prp-mcp"
TOKEN_ENDPOINT = ISSUER + "/protocol/openid-connect/token"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def openssl(*args, input_data=None):
    completed = subprocess.run(
        ["openssl", *map(str, args)], input=input_data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=20,
    )
    if completed.returncode:
        raise RuntimeError("DISPOSABLE_OPENSSL_OPERATION_FAILED")
    return completed.stdout


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_keypair(folder):
    key = folder / "jwt-private.pem"
    cert = folder / "jwt-public.crt"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
            "-keyout", key, "-out", cert, "-days", "1", "-subj", "/CN=prp-ci-jwt")
    key.chmod(0o600)
    certificate_der = openssl("x509", "-in", cert, "-outform", "DER")
    return key, base64.b64encode(certificate_der).decode("ascii")


def register(token, certificate):
    url = REALM_ADMIN + "/clients"
    client = {
        "clientId": CLIENT,
        "name": "Ephemeral test of Signed JWT authentication only",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-jwt",
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "consentRequired": False,
        "fullScopeAllowed": False,
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": ["prp.tasks.read"],
        "attributes": {
            "use.jwks.url": "false",
            "jwt.credential.certificate": certificate,
            "token.endpoint.auth.signing.alg": "RS256",
        },
        "protocolMappers": [{
            "name": "CI only exact PRP resource",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": "matrix-prp-mcp-resource",
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        }],
    }
    status, _, _ = request(url, method="POST", json_body=client, bearer=token)
    if status != 201:
        raise RuntimeError("TEST_CLIENT_CREATION_REJECTED_HTTP_" + str(status))
    print("PASS JWT: generated disposable RSA credential and registered exact test client.")


def assertion(key, *, aud=TOKEN_ENDPOINT, issuer=CLIENT, subject=CLIENT, expires=60,
              replace_signature=False):
    issued = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    body = {
        "iss": issuer, "sub": subject, "aud": aud,
        "iat": issued, "nbf": issued - 2, "exp": issued + expires,
        "jti": secrets.token_urlsafe(24),
    }
    payload = ".".join(b64(json.dumps(obj, separators=(",", ":")).encode())
                       for obj in (header, body))
    signature = openssl("dgst", "-sha256", "-sign", key, input_data=payload.encode())
    if replace_signature:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    return payload + "." + b64(signature)


def token(key, *, mode="valid"):
    params = {
        "grant_type": "client_credentials",
        "client_id": CLIENT,
        "client_assertion_type": ASSERTION_TYPE,
        "scope": "prp.finance.read" if mode == "finance_scope" else "prp.tasks.read",
        "resource": "https://invalid-resource.example.invalid/api/mcp"
                    if mode == "bad_resource" else RESOURCE,
    }
    if mode != "missing":
        params["client_assertion"] = assertion(
            key,
            aud="https://invalid-audience.example.invalid/token" if mode == "bad_audience"
                else TOKEN_ENDPOINT,
            expires=-30 if mode == "expired" else 60,
            replace_signature=(mode == "bad_signature"),
        )
    status, _, raw = request(TOKEN_ENDPOINT, method="POST", form=params)
    if status == 200:
        try:
            return status, json.loads(raw).get("access_token")
        except (ValueError, AttributeError):
            raise RuntimeError("MALFORMED_TEST_TOKEN_RESPONSE") from None
    # Never surface Keycloak's raw error payload, assertion or certificate.
    return status, None


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("DISPOSABLE_RUNNER_ONLY")
    with tempfile.TemporaryDirectory(prefix="prp-private-key-jwt-", dir=os.environ["RUNNER_TEMP"]) as dir_name:
        key, cert = create_keypair(Path(dir_name))
        register(admin_token(), cert)
        status, access = token(key)
        if status != 200 or not isinstance(access, str):
            raise RuntimeError("VALID_PRIVATE_KEY_JWT_REJECTED_HTTP_" + str(status))
        jwks_status, _, body = request(ISSUER + "/protocol/openid-connect/certs")
        if jwks_status != 200:
            raise RuntimeError("ISSUER_JWKS_UNAVAILABLE")
        check_token(access, json.loads(body), issuer=ISSUER, resource=RESOURCE, client_id=CLIENT)
        print("PASS JWT: real RS256 private_key_jwt authenticates and issuer-signed MCP-audience token validates.")
        for failure in ("missing", "bad_signature", "bad_audience", "expired",
                        "bad_resource", "finance_scope"):
            reject_status, issued = token(key, mode=failure)
            if reject_status not in (400, 401) or issued is not None:
                raise RuntimeError("INVALID_ASSERTION_ACCEPTED_" + failure)
            print("PASS JWT: rejected " + failure + " client assertion.")
        print("PASS JWT: isolated client_credentials auth only; NO browser code/refresh/ChatGPT key verified.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        msg = str(exc)
        if len(msg) > 110 or any(s in msg for s in ("https://", "Bearer", "PRIVATE KEY", "access_token")):
            msg = "DISPOSABLE_JWT_UNVERIFIED"
        print("FAIL JWT: " + msg)
        raise SystemExit(1) from None
