import unittest
from check_metadata import validate


ISSUER = "https://auth.example.org/realms/prp-mcp"
RESOURCE = "https://prp.example.org/api/mcp"
JWKS = "https://auth.example.org/realms/prp-mcp/protocol/openid-connect/certs"


def fixtures():
    return {
        ISSUER + "/.well-known/openid-configuration": {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
            "token_endpoint": ISSUER + "/protocol/openid-connect/token",
            "jwks_uri": JWKS,
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "registration_endpoint": ISSUER + "/clients-registrations/openid-connect",
        },
        JWKS: {"keys": [{"kty": "RSA", "kid": "test-public", "use": "sig",
                         "alg": "RS256", "n": "public-modulus", "e": "AQAB"}]},
    }


class MetadataPreflightTests(unittest.TestCase):
    def test_valid_keycloak_oidc_issuer(self):
        responses = fixtures()
        result = validate(ISSUER, RESOURCE, responses.__getitem__)
        self.assertTrue(result["pkce_s256"])
        self.assertTrue(result["client_registration_advertised"])

    def test_wrong_issuer_rejected(self):
        responses = fixtures()
        responses[ISSUER + "/.well-known/openid-configuration"]["issuer"] = "https://evil.example.org"
        with self.assertRaisesRegex(ValueError, "issuer metadata mismatch"):
            validate(ISSUER, RESOURCE, responses.__getitem__)

    def test_pkce_s256_required(self):
        responses = fixtures()
        responses[ISSUER + "/.well-known/openid-configuration"]["code_challenge_methods_supported"] = ["plain"]
        with self.assertRaisesRegex(ValueError, "PKCE S256"):
            validate(ISSUER, RESOURCE, responses.__getitem__)

    def test_https_resource_required(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            validate(ISSUER, "http://prp.example.org/api/mcp", fixtures().__getitem__)

    def test_jwks_rsa_signing_key_required(self):
        responses = fixtures()
        responses[JWKS] = {"keys": [{"kty": "oct", "kid": "symmetric-not-public"}]}
        with self.assertRaisesRegex(ValueError, "RSA signing key"):
            validate(ISSUER, RESOURCE, responses.__getitem__)


if __name__ == "__main__":
    unittest.main()
