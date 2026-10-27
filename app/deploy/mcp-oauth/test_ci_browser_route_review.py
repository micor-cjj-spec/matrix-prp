"""Offline: browser route-surface check never emits OAuth query or JWT."""
import contextlib
from io import StringIO
import unittest

from ci_browser_route_review import Audit, classify, path_class, require_review_coverage


class BrowserRouteReviewTests(unittest.TestCase):
    def test_callback_query_never_collected_and_exact_callback_allowed(self):
        audit = Audit()
        audit.record("GET", "https://prp-e2e.localhost/prp/me/mcp-link/callback"
                     "?code=HIGHLY_PRIVATE_TEST_CODE&state=SECRET&iss=TEST")
        self.assertEqual(audit.seen, {
            ("GET", "/prp/me/mcp-link/callback")
        })
        self.assertEqual(audit.unexpected(), [])
        self.assertNotIn("SECRET", str(audit.seen))
        self.assertNotIn("HIGHLY_PRIVATE", str(audit.summary()))

    def test_methods_exact_and_static_asset_regex(self):
        for method, path in (
            ("GET", "/prp/me/mcp-clients"),
            ("POST", "/api/mcp/identity/oidc/start"),
            ("POST", "/api/mcp/identity/oidc/finish"),
            ("GET", "/api/users/me"),
            ("GET", "/prp/assets/McpClientsView-aB29_.js"),
            ("GET", "/prp/assets/base-AZ92.css"),
        ):
            with self.subTest(path=path):
                self.assertIs(classify(method, "https://prp-e2e.localhost" + path), True)
        for method, path in (
            ("POST", "/prp/me/mcp-clients"),
            ("GET", "/api/mcp/identity/oidc/start"),
            ("GET", "/api/tasks"),
            ("GET", "/prp/"),
            ("GET", "/prp/sw.js"),
            ("GET", "/prp/api/mcp"),
            ("POST", "/api/mcp/approval/drafts/00000000-0000-0000-0000-000000000000"),
            ("GET", "/prp/assets/../../.env"),
            ("GET", "/api/%6dcp"),
        ):
            with self.subTest(path=path):
                self.assertIs(classify(method, "https://prp-e2e.localhost" + path), False)

    def test_foreign_origin_is_not_collected(self):
        audit = Audit()
        audit.record("GET", "https://auth-e2e.localhost/realms/prp-mcp/protocol/"
                     "openid-connect/auth?state=DO_NOT_KEEP")
        audit.record("POST", "https://chatgpt.com/api/private?Bearer=NONE")
        self.assertFalse(audit.seen)
        self.assertIsNone(classify("POST", "https://auth-e2e.localhost/foo"))

    def test_unreviewed_paths_fail_closed_without_printing_url_or_token(self):
        audit = Audit()
        audit.record("GET", "https://prp-e2e.localhost/api/users/private/123456"
                     "?jwt=LEAK_TEST")
        audit.record("GET", "https://prp-e2e.localhost/prp/sw.js")
        sink = StringIO()
        with contextlib.redirect_stdout(sink):
            with self.assertRaisesRegex(
                    RuntimeError, "CHROMIUM_BROWSING_ROUTES_NOT_COVERED_BY_G0_CANDIDATE"):
                require_review_coverage(audit)
        diagnostic = sink.getvalue()
        self.assertIn("API_USERS", diagnostic)
        self.assertIn("SPA_OTHER", diagnostic)
        for secret in ("123456", "LEAK_TEST", "/api/users/private", "/prp/sw.js"):
            self.assertNotIn(secret, diagnostic)

    def test_covered_paths_pass(self):
        audit = Audit()
        audit.record("GET", "https://prp-e2e.localhost/prp/login")
        audit.record("POST", "https://prp-e2e.localhost/api/auth/login")
        audit.record("GET", "https://prp-e2e.localhost/prp/assets/index-A5g.css")
        sink = StringIO()
        with contextlib.redirect_stdout(sink):
            require_review_coverage(audit)
        self.assertIn("3 unique", sink.getvalue())

    def test_sanitized_path_classes_do_not_echo_identity(self):
        self.assertEqual(
            path_class("GET", "https://prp-e2e.localhost/api/mcp/users/123"),
            "API_MCP")


if __name__ == "__main__":
    unittest.main()
