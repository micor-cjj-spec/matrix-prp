#!/usr/bin/env python3
"""GitHub disposable Keycloak only: exercise client-jwt with embedded JWKS."""
import base64
import json
import os
import secrets
import subprocess
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from ci_chatgpt_cimd_pkce import BASE, REALM_ADMIN, request, admin_token

CLIENT = "ci-embedded-jwks-" + secrets.token_hex(8)
TOKEN = BASE + "/realms/prp-mcp/protocol/openid-connect/token"
TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def jwt(key, kid, *, aud=TOKEN, expiry=90):
    now = int(time.time())
    header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    body = {"iss": CLIENT, "sub": CLIENT, "aud": aud, "iat": now,
            "nbf": now - 2, "exp": now + expiry, "jti": secrets.token_urlsafe(20)}
    msg = ".".join(b64(json.dumps(x, separators=(",", ":")).encode()) for x in (header, body))
    sig = key.sign(msg.encode(), padding.PKCS1v15(), hashes.SHA256())
    return msg + "." + b64(sig)


def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or not os.getenv("RUNNER_TEMP"):
        raise RuntimeError("CI_ONLY")
    if BASE != "http://127.0.0.1:18080":
        raise RuntimeError("UNEXPECTED_CI_KEYCLOAK_BASE")
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Name}}|{{.State.Running}}|{{.Config.Image}}",
         "prp-mcp-keycloak-ci"], capture_output=True, text=True, check=False, timeout=8)
    parts = result.stdout.strip().split("|")
    if result.returncode or len(parts) != 3 or parts[:2] != ["/prp-mcp-keycloak-ci", "true"]:
        raise RuntimeError("CI_CONTAINER_IDENTITY_MISSING")
    if parts[2] not in ("quay.io/keycloak/keycloak:26.8.0", "quay.io/keycloak/keycloak:26.8.1"):
        raise RuntimeError("UNEXPECTED_CI_IMAGE")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    kid = "ci-" + secrets.token_hex(8)
    jwk = {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid,
           "n": b64(pub.n.to_bytes((pub.n.bit_length()+7)//8, "big")),
           "e": b64(pub.e.to_bytes((pub.e.bit_length()+7)//8, "big"))}
    token = admin_token()
    client = {
        "clientId": CLIENT, "enabled": True, "protocol": "openid-connect",
        "publicClient": False, "clientAuthenticatorType": "client-jwt",
        "serviceAccountsEnabled": True, "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
        "attributes": {"use.jwks.url": "false", "use.jwks.string": "true",
                       "jwks.string": json.dumps({"keys": [jwk]}, separators=(",", ":")),
                       "token.endpoint.auth.signing.alg": "RS256"}}
    url = REALM_ADMIN + "/clients"
    status, _, _ = request(url, method="POST", json_body=client, bearer=token)
    if status != 201:
        raise RuntimeError("CREATE_FAILED_" + str(status))
    try:
        for name, signing_key, keyid, aud, exp, good in (
            ("valid", key, kid, TOKEN, 90, True),
            ("wrong_signature", rsa.generate_private_key(public_exponent=65537, key_size=2048), kid, TOKEN, 90, False),
            ("wrong_kid", key, "unknown-kid", TOKEN, 90, False),
            ("wrong_audience", key, kid, BASE + "/invalid", 90, False),
            ("expired", key, kid, TOKEN, -90, False),
        ):
            status, _, raw = request(TOKEN, method="POST", form={
                "grant_type": "client_credentials", "client_id": CLIENT,
                "client_assertion_type": TYPE,
                "client_assertion": jwt(signing_key, keyid, aud=aud, expiry=exp)})
            try:
                body = json.loads(raw)
            except ValueError:
                body = {}
            if good:
                if status != 200 or not body.get("access_token"):
                    raise RuntimeError(name + "_REJECTED_HTTP_" + str(status))
            elif status not in (400, 401) or body.get("error") != "invalid_client":
                raise RuntimeError(name + "_NOT_INVALID_CLIENT_HTTP_" + str(status))
            print("PASS EMBEDDED_JWKS_" + name)
    finally:
        from urllib.parse import quote
        status, _, raw = request(url + "?clientId=" + quote(CLIENT, safe=""), bearer=token)
        if status != 200:
            raise RuntimeError("CLEANUP_LOOKUP_FAILED")
        matches = [x for x in json.loads(raw) if x.get("clientId") == CLIENT]
        if len(matches) != 1:
            raise RuntimeError("CLEANUP_CLIENT_COUNT_UNEXPECTED")
        status, _, _ = request(url + "/" + matches[0]["id"], method="DELETE", bearer=token)
        if status != 204:
            raise RuntimeError("CLEANUP_DELETE_FAILED")
    print("EMBEDDED_JWKS_CI_PROOF=PASS")


if __name__ == "__main__":
    main()
