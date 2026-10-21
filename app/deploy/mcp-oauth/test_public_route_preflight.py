import unittest
from public_route_preflight import canonical_resource, metadata_uri, inspect


RESOURCE = "https://mcp.staging.example.org/api/mcp"
ISSUER = "https://auth.staging.example.org/realms/prp-mcp"
WELL_KNOWN = "https://mcp.staging.example.org/.well-known/oauth-protected-resource/api/mcp"


def fake_fetch(uri, method, body):
    if uri == WELL_KNOWN:
        return 200, {"content-type": "application/json"}, {
            "resource": RESOURCE,
            "authorization_servers": [ISSUER],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["prp.tasks.read"],
        }
    if uri == RESOURCE:
        return 401, {
            "www-authenticate": 'Bearer resource_metadata="' + WELL_KNOWN + '"'
        }, {}
    raise AssertionError("Unrecognized preflight URI")


class PublicRouteContractTests(unittest.TestCase):
    def test_actual_backend_api_url_and_protected_resource_metadata(self):
        self.assertEqual(metadata_uri(RESOURCE), WELL_KNOWN)
        self.assertTrue(inspect(RESOURCE, ISSUER, fake_fetch)["unauthenticated_mcp_denied"])

    def test_wrong_resource_prefix_not_accepted(self):
        for value in (
            "https://mcp.staging.example.org/prp/api/mcp",
            "http://mcp.staging.example.org/api/mcp",
            "https://micor.top/api/mcp",
            "https://mcp.staging.example.org/api/mcp?debug=1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_resource(value)

    def test_missing_unauth_challenge_fails(self):
        def wrong_challenge(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "POST":
                headers = {"www-authenticate": "Bearer"}
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "challenge"):
            inspect(RESOURCE, ISSUER, wrong_challenge)

    def test_anonymous_mcp_must_fail_closed(self):
        def accidentally_open(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "POST":
                return 200, headers, {"result": {"tools": []}}
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "401"):
            inspect(RESOURCE, ISSUER, accidentally_open)

    def test_metadata_different_target_rejected(self):
        def tampered(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "GET":
                json_value["resource"] = "https://elsewhere.staging.example.org/api/mcp"
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "Advertised resource"):
            inspect(RESOURCE, ISSUER, tampered)


if __name__ == "__main__":
    unittest.main()
