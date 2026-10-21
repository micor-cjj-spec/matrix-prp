"""Offline RS256/JWKS OAuth audience regression tests with disposable RSA key."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from oauth_token_check import check_token


ISSUER = "https://auth.stage.example/realms/prp-mcp"
RESOURCE = "https://prp.stage.example/api/mcp"
CLIENT = "prp-pkce-probe"


def b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class SignedOAuthTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.key = Path(cls.temp.name) / "key.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                        "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(cls.key)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        mod = subprocess.check_output(
            ["openssl", "rsa", "-in", str(cls.key), "-noout", "-modulus"],
            stderr=subprocess.DEVNULL).decode("ascii").strip()
        n = int(mod.split("=", 1)[1], 16)
        cls.jwks = {"keys": [{"kid": "ci-only", "kty": "RSA", "use": "sig",
                               "alg": "RS256",
                               "n": b64(n.to_bytes((n.bit_length() + 7) // 8, "big")),
                               "e": b64((65537).to_bytes(3, "big"))}]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def token(self, **overrides):
        now = int(time.time())
        claims = {"iss": ISSUER, "sub": "test-service",
                  "aud": [RESOURCE], "azp": CLIENT,
                  "scope": "openid prp.tasks.read",
                  "iat": now - 15, "exp": now + 300}
        claims.update(overrides)
        header = {"alg": "RS256", "kid": "ci-only", "typ": "JWT"}
        text = b64(json.dumps(header).encode()) + "." + b64(json.dumps(claims).encode())
        signature = subprocess.check_output(["openssl", "dgst", "-sha256",
                                             "-sign", str(self.key)],
                                            input=text.encode())
        return text + "." + b64(signature)

    def verify(self, token, jwks=None):
        return check_token(token, self.jwks if jwks is None else jwks,
                           issuer=ISSUER, resource=RESOURCE, client_id=CLIENT)

    def test_trusted_signed_resource_token(self):
        result = self.verify(self.token())
        self.assertEqual(result["audience"], "exact MCP resource")
        self.assertEqual(result["signature"], "RS256 verified")

    def test_issuer_audience_client_scope_expiry_are_enforced(self):
        bad_claims = [
            {"iss": "https://evil.example/realms/prp-mcp"},
            {"aud": ["matrix-prp-mcp-resource"]},
            {"aud": [RESOURCE, RESOURCE]},
            {"aud": ["https://another.example/api/mcp"]},
            {"aud": [RESOURCE, ""]},
            {"aud": [RESOURCE, 123]},
            {"azp": "different-client"},
            {"client_id": "other-client"},
            {"scope": "openid profile"},
            {"exp": 1},
            {"iat": int(time.time()) + 120},
        ]
        for claims in bad_claims:
            with self.subTest(claims=claims), self.assertRaises(ValueError):
                self.verify(self.token(**claims))

    def test_auth0_style_additional_signed_userinfo_audience_is_allowed(self):
        jwt = self.token(aud=[RESOURCE, ISSUER + "/userinfo"])
        result = self.verify(jwt)
        self.assertEqual(result["audience"], "exact MCP resource")
        self.assertTrue(result["additional_audiences_present"])
        self.assertFalse(self.verify(self.token())["additional_audiences_present"])

    def test_tampered_payload_or_signature_fails(self):
        token = self.token()
        pieces = token.split(".")
        altered = pieces[0] + "." + b64(b'{"sub":"forged"}') + "." + pieces[2]
        with self.assertRaises(ValueError):
            self.verify(altered)
        sig = pieces[2]
        tampered_sig = sig[:10] + ("A" if sig[10] != "A" else "B") + sig[11:]
        with self.assertRaises(ValueError):
            self.verify(pieces[0] + "." + pieces[1] + "." + tampered_sig)

    def test_unknown_jwks_and_non_jwt_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(self.token(), {"keys": []})
        with self.assertRaises(ValueError):
            self.verify("not.a.jwt")
        with self.assertRaises(ValueError):
            self.verify("opaque-access-token")

    def test_single_signed_client_id_claim_is_supported(self):
        jwt = self.token(azp=None, client_id=CLIENT)
        self.assertEqual(self.verify(jwt)["client"], "verified")


if __name__ == "__main__":
    unittest.main()
