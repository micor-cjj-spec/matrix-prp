import unittest
from build_realm import build_realm, canonical_resource


class KeycloakResourceRealmTests(unittest.TestCase):
    def test_canonical_resource_registered_and_browser_clients_not_created(self):
        url = "https://prp.staging.test/prp/api/mcp"
        realm = build_realm(url)
        self.assertEqual(realm["realm"], "prp-mcp")
        self.assertEqual(len(realm["clients"]), 1)
        resource = realm["clients"][0]
        self.assertEqual(resource["clientId"], "matrix-prp-mcp-resource")
        self.assertEqual(resource["attributes"]["resource_url"], url)
        self.assertTrue(resource["bearerOnly"])
        self.assertFalse(resource["standardFlowEnabled"])
        self.assertFalse(resource["directAccessGrantsEnabled"])
        self.assertFalse(resource["serviceAccountsEnabled"])

    def test_scopes_optional_and_never_granted_without_client_assignment(self):
        realm = build_realm("https://prp.staging.test/api/mcp")
        self.assertEqual(len(realm["clientScopes"]), 6)
        self.assertTrue(all(s["attributes"]["include.in.token.scope"] == "true"
                            for s in realm["clientScopes"]))
        self.assertEqual(len(realm["clients"]), 1)
        self.assertFalse(realm["clients"][0]["standardFlowEnabled"])

    def test_explicit_read_only_pkce_client_and_exact_audience(self):
        realm = build_realm(
            "https://prp.staging.test/api/mcp",
            staging_client_id="prp-pkce-probe",
            staging_redirect="http://127.0.0.1:8765/callback")
        self.assertEqual(len(realm["clients"]), 2)
        client = realm["clients"][1]
        self.assertEqual(client["clientId"], "prp-pkce-probe")
        self.assertEqual(client["redirectUris"], ["http://127.0.0.1:8765/callback"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertTrue(client["consentRequired"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertEqual(client["optionalClientScopes"], ["prp.tasks.read"])
        self.assertEqual(client["defaultClientScopes"], ["basic"])  # required signed sub
        self.assertEqual(client["protocolMappers"][0]["config"]["included.client.audience"],
                         "matrix-prp-mcp-resource")

    def test_rejects_non_loopback_http_redirects_and_wildcards(self):
        for uri in (
            "http://attack.example.org/callback",
            "https://attack.example.org/*",
            "https://user:secret@example.org/redirect",
            "https://app.example.org/redirect?code=foo",
        ):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                build_realm("https://prp.staging.test/api/mcp",
                            staging_client_id="prp-pkce-probe", staging_redirect=uri)

    def test_staging_client_always_requires_both_arguments(self):
        with self.assertRaises(ValueError):
            build_realm("https://prp.staging.test/api/mcp",
                        staging_client_id="prp-pkce-probe")

    def test_no_arbitrary_insecure_resource(self):
        for value in (
            "http://prp.staging.test/api/mcp",
            "https://prp.staging.test/api/mcp?key=secret",
            "https://person:secret@prp.staging.test/api/mcp",
            "https://prp.staging.test/api/mcp#fragment",
            "https://prp.staging.test/foo",
            "https://prp.staging.test/../api/mcp",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_resource(value)

    def test_nonstandard_staging_uri_retains_exact_path(self):
        resource = "https://prp.staging.test/prp/api/mcp"
        self.assertEqual(
            build_realm(resource)["clients"][0]["attributes"]["resource_url"], resource
        )


if __name__ == "__main__":
    unittest.main()
