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
