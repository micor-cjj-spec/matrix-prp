"""Contract tests for review-only *task-read* account-bootstrap route plan.

Never installs Nginx, enables B2, registers OAuth, or issues any bearer token.
"""
import unittest

from approval_routes_pending import (
    EXACT, REGEX, READONLY_LINK_EXACT, READONLY_LINK_REGEX,
    render_approval_routes, render_readonly_link_routes,
)

REQUIRED_METHODS = {
    "/prp/login": "GET",
    "/prp/me/mcp-clients": "GET",
    "/api/auth/login": "POST",
    "/api/users/me": "GET",
    "/api/mcp/clients": "GET POST",
    "/api/mcp/clients/revoke": "POST",
    "/api/mcp/identity": "GET",
    "/api/mcp/identity/tickets": "POST",
    "/api/mcp/identity/unlink": "POST",
    "/api/mcp/link": "POST",
}


class ReadonlyLinkReviewRoutesTests(unittest.TestCase):
    def test_exactly_scoped_routes_without_approval_or_general_business(self):
        self.assertEqual(READONLY_LINK_EXACT, REQUIRED_METHODS)
        self.assertEqual(len(READONLY_LINK_REGEX), 1)
        self.assertEqual(set(READONLY_LINK_REGEX.values()), {"GET"})
        for excluded in (
            "/api/", "/api/auth/register", "/api/tasks", "/api/mcp/approval",
            "/admin", "/api/finance", "/api/mcp/approval/drafts",
            "/prp/me/mcp-approve", "/prp/", "/api/mcp",
        ):
            self.assertNotIn(excluded, READONLY_LINK_EXACT)
        self.assertTrue(set(READONLY_LINK_EXACT).issubset(EXACT))
        self.assertTrue(set(READONLY_LINK_REGEX).issubset(REGEX))

    def test_rendered_proxy_remains_private_secure_and_noncacheable(self):
        rendered = render_readonly_link_routes("/tmp/reviewed-ca.pem")
        self.assertEqual(rendered.count("location = "), 10)
        self.assertEqual(rendered.count('location ~ "'), 1)
        self.assertEqual(rendered.count("proxy_ssl_verify on;"), 11)
        self.assertEqual(rendered.count("proxy_ssl_name prp-test.micor.top;"), 11)
        self.assertEqual(rendered.count("proxy_pass https://127.0.0.1:18443;"), 11)
        self.assertEqual(rendered.count("if ($prp_stage_origin_ok = 0) { return 403; }"), 11)
        self.assertEqual(rendered.count('access_log off;'), 11)
        self.assertEqual(rendered.count('proxy_cache off;'), 11)
        self.assertEqual(rendered.count('Referrer-Policy "no-referrer"'), 11)
        self.assertIn("PENDING REVIEW ONLY", rendered)
        self.assertNotIn("location = /api/tasks", rendered)
        self.assertNotIn("location = /api/mcp ", rendered)
        self.assertNotIn("/api/mcp/approval/drafts", rendered)
        self.assertNotIn("/prp/me/mcp-approve", rendered)

    def test_mutation_method_walled_to_exact_endpoint(self):
        rendered = render_readonly_link_routes("/tmp/ca.pem")
        for path, verbs in REQUIRED_METHODS.items():
            self.assertIn(
                "location = " + path + " {\n    limit_except " + verbs + " { deny all; }",
                rendered,
            )
        self.assertIn("limit_except GET { deny all; }", rendered)

    def test_existing_review_only_full_approval_candidate_unchanged(self):
        # Refactor must NOT reduce or change the original broader artifact.
        before = render_approval_routes("/tmp/ca.pem")
        self.assertEqual(before.count("location = "), len(EXACT))
        self.assertEqual(before.count('location ~ "'), len(REGEX))
        self.assertIn('location = /api/mcp/clients', before)
        self.assertIn("/api/mcp/approval/drafts", before)
        self.assertNotEqual(before, render_readonly_link_routes("/tmp/ca.pem"))

    def test_fail_closed_ca_path_and_loopback_port(self):
        for path in ("relative.pem", "/tmp/../ca.pem", "/tmp/ca.pem\n",
                     "/tmp/ca.pem;proxy_ssl_verify off;"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                render_readonly_link_routes(path)
        for port in (-1, 443, 65536, "18443", True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                render_readonly_link_routes("/tmp/ca.pem", port)


if __name__ == "__main__":
    unittest.main()
