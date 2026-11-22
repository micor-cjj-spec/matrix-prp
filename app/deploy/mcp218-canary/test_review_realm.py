"""Synthetic-only unit tests: candidate never deploys, writes, or registers OAuth clients."""
import unittest
from unittest.mock import patch

from review_realm import READ_SCOPES, REALM, build_review_video_candidate

RESOURCE = "https://mcp218-ci-spec.micor.top/api/mcp"


class ReviewVideoOnlyRealmCandidateTests(unittest.TestCase):
    def test_new_realm_and_only_three_explicit_client_scopes(self):
        data = build_review_video_candidate(RESOURCE)
        self.assertEqual(data["realm"], REALM)
        scopes = [x["name"] for x in data["clientScopes"]]
        self.assertEqual(scopes, ["basic", *READ_SCOPES])
        self.assertNotIn("prp.tasks.read", scopes)
        self.assertFalse(any(".write." in s for s in scopes))

    def test_single_resource_only_client_no_browser_or_chatgpt_client(self):
        data = build_review_video_candidate(RESOURCE)
        self.assertEqual(len(data["clients"]), 1)
        protected = data["clients"][0]
        self.assertEqual(protected["clientId"], "matrix-prp-mcp218-resource")
        self.assertEqual(protected["attributes"]["resource_url"], RESOURCE)
        self.assertTrue(protected["bearerOnly"])
        self.assertFalse(protected["standardFlowEnabled"])
        self.assertFalse(protected["directAccessGrantsEnabled"])
        self.assertFalse(protected["serviceAccountsEnabled"])
        self.assertNotIn("redirectUris", protected)
        self.assertNotIn("users", data)

    def test_token_subject_and_visible_consent_names(self):
        data = build_review_video_candidate(RESOURCE)
        basic, *scopes = data["clientScopes"]
        self.assertEqual(basic["name"], "basic")
        self.assertEqual(basic["protocolMappers"][0]["protocolMapper"], "oidc-sub-mapper")
        self.assertEqual(basic["protocolMappers"][0]["config"]["access.token.claim"], "true")
        for scope in scopes:
            self.assertEqual(scope["attributes"]["consent.screen.text"], scope["name"])
            self.assertEqual(scope["attributes"]["include.in.token.scope"], "true")
            self.assertEqual(scope["attributes"]["display.on.consent.screen"], "true")

    def test_safe_realm_baseline_and_no_account_registration(self):
        data = build_review_video_candidate(RESOURCE)
        self.assertTrue(data["bruteForceProtected"])
        self.assertFalse(data["registrationAllowed"])
        self.assertFalse(data["resetPasswordAllowed"])
        self.assertTrue(data["revokeRefreshToken"])
        self.assertEqual(data["refreshTokenMaxReuse"], 0)

    def test_deterministic_resource_only_no_state(self):
        first = build_review_video_candidate(RESOURCE)
        second = build_review_video_candidate(RESOURCE)
        self.assertEqual(first, second)
        self.assertEqual(len(first["clients"]), 1)
        self.assertEqual(first["clients"][0]["attributes"]["resource_url"], RESOURCE)

    def test_original_builder_is_not_modified(self):
        from review_realm import build_realm
        original = build_realm(RESOURCE)
        self.assertEqual(original["realm"], "prp-mcp")
        self.assertIn("prp.tasks.read", [x["name"] for x in original["clientScopes"]])
        self.assertNotIn("prp.reviews.read", [x["name"] for x in original["clientScopes"]])

    def test_no_network_dependency(self):
        with patch("socket.create_connection", side_effect=AssertionError("NETWORK_FORBIDDEN")):
            self.assertEqual(build_review_video_candidate(RESOURCE)["realm"], REALM)

    def test_reject_existing_v2_and_unrelated_hostnames(self):
        bad = (
            "https://prp-test.micor.top/api/mcp",
            "https://auth-test.micor.top/api/mcp",
            "https://auth.micor.top/api/mcp",
            "https://micor.top/api/mcp",
            "https://pos-preview.micor.top/api/mcp",
        )
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                build_review_video_candidate(url)

    def test_reject_insecure_malformed_and_credential_urls(self):
        bad = (
            "http://mcp218-ci-spec.micor.top/api/mcp",
            "https://mcp218-ci-spec.micor.top/api/foo",
            "https://mcp218-ci-spec.micor.top/api/mcp/",
            "https://mcp218-ci-spec.micor.top/api/mcp?jwt=something",
            "https://mcp218-ci-spec.micor.top/api/mcp#data",
            "https://someone:password@mcp218-ci-spec.micor.top/api/mcp",
            "https://mcp218-ci-spec.micor.top:8443/api/mcp",
            "https://mcp218-ci-spec.micor.top.evil.invalid/api/mcp",
            "https://mcp218-example.invalid/api/mcp",
            "https://MCP218-ci-spec.micor.top/api/mcp",
            "https://mcp218-.micor.top/api/mcp",
            "https://mcp218-ci-spec.micor.top//api/mcp",
            "",
            None,
        )
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                build_review_video_candidate(url)

    def test_reject_wrong_upstream_shape(self):
        from review_realm import build_realm
        original = build_realm(RESOURCE)
        original["clients"].append({"clientId": "unexpected-browser-client"})
        with patch("review_realm.build_realm", return_value=original):
            with self.assertRaisesRegex(ValueError, "UPSTREAM_REALM_SHAPE_CHANGED"):
                build_review_video_candidate(RESOURCE)


if __name__ == "__main__":
    unittest.main()
