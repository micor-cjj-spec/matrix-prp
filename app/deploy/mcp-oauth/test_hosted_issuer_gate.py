import unittest

from hosted_issuer_gate import assess
from check_metadata import validate


AUTH0_ISSUER = "https://tenant.us.auth0.com/"
KEYCLOAK_ISSUER = "https://auth.example.org/realms/prp-mcp"
RESOURCE = "https://prp.example.org/api/mcp"


def fixtures(issuer, *, methods=None, scopes=None, dcr=True, cimd=False):
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": issuer.rstrip("/") + "/authorize",
        "token_endpoint": issuer.rstrip("/") + "/oauth/token",
        "jwks_uri": issuer.rstrip("/") + "/.well-known/jwks.json",
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": methods if methods is not None else ["none", "client_secret_post"],
        "scopes_supported": scopes if scopes is not None else ["openid", "offline_access", "prp.tasks.read"],
        "client_id_metadata_document_supported": cimd,
    }
    if dcr:
        metadata["registration_endpoint"] = issuer.rstrip("/") + "/oauth/register"
    return {
        issuer.rstrip("/") + "/.well-known/openid-configuration": metadata,
        metadata["jwks_uri"]: {
            "keys": [{"kty": "RSA", "kid": "fixture-key", "use": "sig",
                      "alg": "RS256", "n": "not-a-private-key", "e": "AQAB"}],
        },
    }


class HostedIssuerGateTests(unittest.TestCase):
    def test_auth0_trailing_slash_is_preserved_exactly(self):
        data = fixtures(AUTH0_ISSUER)
        basic = validate(AUTH0_ISSUER, RESOURCE, data.__getitem__)
        self.assertEqual(basic["issuer"], AUTH0_ISSUER)
        check = assess(AUTH0_ISSUER, RESOURCE, "dcr", data.__getitem__)
        self.assertEqual(check["issuer"], AUTH0_ISSUER)
        self.assertEqual(check["phase"], "metadata_only")
        self.assertFalse(check["ready_for_production"])
        self.assertFalse(check["real_user_token_verified"])
        self.assertTrue(any("Resource Parameter Compatibility" in w for w in check["warnings"]))

    def test_keycloak_non_slash_issuer_remains_supported(self):
        data = fixtures(KEYCLOAK_ISSUER)
        self.assertEqual(assess(KEYCLOAK_ISSUER, RESOURCE, "dcr", data.__getitem__)["issuer"],
                         KEYCLOAK_ISSUER)

    def test_cimd_only_when_discovery_and_auth_method_support_it(self):
        good = fixtures(KEYCLOAK_ISSUER, cimd=True, methods=["private_key_jwt"])
        self.assertEqual(assess(KEYCLOAK_ISSUER, RESOURCE, "cimd",
                                good.__getitem__)["registration_mode"], "cimd")
        unsupported = fixtures(KEYCLOAK_ISSUER, cimd=False)
        with self.assertRaisesRegex(ValueError, "CIMD requires"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "cimd", unsupported.__getitem__)
        method = fixtures(KEYCLOAK_ISSUER, cimd=True, methods=["client_secret_post"])
        with self.assertRaisesRegex(ValueError, "none or private_key_jwt"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "cimd", method.__getitem__)

    def test_dcr_does_not_claim_success_without_registration_endpoint(self):
        data = fixtures(KEYCLOAK_ISSUER, dcr=False)
        with self.assertRaisesRegex(ValueError, "DCR requires"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "dcr", data.__getitem__)

    def test_registered_client_required_for_provided_mode(self):
        data = fixtures(KEYCLOAK_ISSUER, dcr=False)
        with self.assertRaisesRegex(ValueError, "Pre-registered"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "provided", data.__getitem__)
        result = assess(KEYCLOAK_ISSUER, RESOURCE, "provided", data.__getitem__,
                        registered_client_id="prp-client")
        self.assertFalse(result["ready_for_production"])

    def test_missing_refresh_capability_is_reported_but_no_token_ever_claimed(self):
        data = fixtures(KEYCLOAK_ISSUER, scopes=["openid", "prp.tasks.read"])
        result = assess(KEYCLOAK_ISSUER, RESOURCE, "dcr", data.__getitem__)
        self.assertFalse(result["refresh_advertised"])
        self.assertTrue(any("offline_access" in w for w in result["warnings"]))
        self.assertFalse(result["ready_for_production"])

    def test_insecure_endpoints_or_missing_token_auth_methods_fail_closed(self):
        bad = fixtures(KEYCLOAK_ISSUER, methods=[])
        with self.assertRaisesRegex(ValueError, "token endpoint authentication"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "dcr", bad.__getitem__)
        bad = fixtures(KEYCLOAK_ISSUER)
        bad[KEYCLOAK_ISSUER + "/.well-known/openid-configuration"]["issuer"] = "https://fake.example.org"
        with self.assertRaisesRegex(ValueError, "issuer metadata mismatch"):
            assess(KEYCLOAK_ISSUER, RESOURCE, "dcr", bad.__getitem__)
        with self.assertRaisesRegex(ValueError, "Protected resource"):
            assess(KEYCLOAK_ISSUER, "https://prp.example.org/prp/api/mcp", "dcr",
                   fixtures(KEYCLOAK_ISSUER).__getitem__)


if __name__ == "__main__":
    unittest.main()
