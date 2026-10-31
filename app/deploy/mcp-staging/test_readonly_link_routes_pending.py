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
    "/prp/me/mcp-link/callback": "GET",
    "/api/mcp/identity/oidc/start": "POST",
    "/api/mcp/identity/oidc/finish": "POST",
    "/prp/favicon.svg": "GET",
    "/prp/icon.svg": "GET",
    "/prp/manifest.webmanifest": "GET",
    "/prp/sw.js": "GET",
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
        self.assertEqual(set(READONLY_LINK_EXACT).difference(EXACT), {
            "/prp/me/mcp-link/callback",
            "/api/mcp/identity/oidc/start",
            "/api/mcp/identity/oidc/finish",
            "/prp/favicon.svg",
            "/prp/icon.svg",
            "/prp/manifest.webmanifest",
            "/prp/sw.js",
        })
        self.assertTrue(set(READONLY_LINK_REGEX).issubset(REGEX))

    def test_rendered_proxy_remains_private_secure_and_noncacheable(self):
        rendered = render_readonly_link_routes()
        self.assertEqual(rendered.count("location = "), 17)
        self.assertEqual(rendered.count('location ~ "'), 1)
        self.assertEqual(rendered.count("proxy_pass http://127.0.0.1:18082;"), 18)
        self.assertNotIn("proxy_pass https://127.0.0.1:18443;", rendered)
        self.assertNotIn("proxy_pass http://127.0.0.1:18081;", rendered)
        self.assertNotIn("proxy_ssl_name", rendered)
        self.assertNotIn("proxy_ssl_trusted_certificate", rendered)
        self.assertNotIn("proxy_ssl_verify", rendered)
        self.assertEqual(rendered.count("if ($prp_stage_origin_ok = 0) { return 403; }"), 18)
        self.assertEqual(rendered.count('access_log off;'), 18)
        self.assertEqual(rendered.count('proxy_cache off;'), 18)
        self.assertEqual(rendered.count('Referrer-Policy "no-referrer"'), 18)
        self.assertIn("PENDING REVIEW ONLY", rendered)
        self.assertNotIn("location = /api/tasks", rendered)
        self.assertNotIn("location = /api/mcp ", rendered)
        self.assertNotIn("/api/mcp/approval/drafts", rendered)
        self.assertNotIn("/prp/me/mcp-approve", rendered)

    def test_vite_dotted_asset_names_without_path_aliases(self):
        import re
        pattern = next(iter(READONLY_LINK_REGEX))
        for accepted in (
            "/prp/assets/vendor.element-plus.B22Q.js",
            "/prp/assets/index-aB29_.js",
            "/prp/assets/icons.123.woff2",
        ):
            self.assertIsNotNone(re.fullmatch(pattern, accepted))
        for rejected in (
            "/prp/assets/foo..js",
            "/prp/assets/../.env",
            "/prp/assets/nested/file.12.js",
            "/prp/assets/%2e%2e.js",
            "/prp/assets/file.js.map",
            "/prp/assets/evil.php",
        ):
            self.assertIsNone(re.fullmatch(pattern, rejected))
        for root_resource in (
            "/prp/favicon.svg",
            "/prp/icon.svg",
            "/prp/manifest.webmanifest",
            "/prp/sw.js",
        ):
            self.assertEqual(READONLY_LINK_EXACT[root_resource], "GET")

    def test_raw_uri_checks_present_only_in_v2_first_party_routes(self):
        rendered = render_readonly_link_routes()
        self.assertEqual(rendered.count('if ($request_uri !~ "'), 18)
        self.assertIn('^/prp/me/mcp', rendered)
        self.assertIn('^/api/mcp/identity/oidc/start', rendered)
        self.assertIn('^/prp/assets/', rendered)
        self.assertNotIn('if ($request_uri !~ "', render_approval_routes('/tmp/ca.pem'))

    def test_explicit_method_guard_denies_implicit_nginx_head(self):
        reviewed = render_readonly_link_routes()
        # Nginx limit_except GET implicitly admits HEAD; this review
        # generator must explicitly deny HEAD for every GET-only location.
        self.assertEqual(reviewed.count('if ($request_method !~ "'), 18)
        reviewed_verbs = list(READONLY_LINK_EXACT.values()) + list(READONLY_LINK_REGEX.values())
        for verb_set in ("GET", "POST", "GET POST"):
            pattern = 'if ($request_method !~ "^(?:' + "|".join(verb_set.split()) + ')$")'
            self.assertEqual(reviewed.count(pattern), reviewed_verbs.count(verb_set))
        self.assertNotIn('if ($request_method !~ "', render_approval_routes('/tmp/ca.pem'))

    def test_mutation_method_walled_to_exact_endpoint(self):
        rendered = render_readonly_link_routes()
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
        self.assertNotEqual(before, render_readonly_link_routes())

    def test_reject_legacy_stage_and_oauth_tls_redirects(self):
        for port in (18081, 18443, -1, 443, 65536, "18082", None, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                render_readonly_link_routes(port)
        with self.assertRaises(TypeError):
            render_readonly_link_routes(trusted_ca="/tmp/ca.pem")

    def test_broad_approval_candidate_pairing_route_is_explicit_and_tls_pinned(self):
        # PR #95 added one review-only POST pairing endpoint to the older
        # 10-exact + 4-regex candidate. It must NOT leak into V2 task-only
        # first-party allowlists or become a generic /api/mcp/* proxy.
        legacy = render_approval_routes("/tmp/ca.pem")
        self.assertEqual(len(EXACT), 11)
        self.assertEqual(len(REGEX), 4)
        self.assertEqual(EXACT["/api/mcp/clients/pairing"], "POST")
        self.assertIn(
            "location = /api/mcp/clients/pairing {\n    limit_except POST { deny all; }",
            legacy,
        )
        self.assertNotIn("/api/mcp/clients/pairing", READONLY_LINK_EXACT)
        self.assertNotIn("location = /api/mcp/clients/pairing", render_readonly_link_routes())
        self.assertNotIn("location ^~ /api/mcp/", legacy)
        expected_routes = len(EXACT) + len(REGEX)
        self.assertEqual(expected_routes, 15)
        self.assertEqual(legacy.count("proxy_pass https://127.0.0.1:18443;"), expected_routes)
        self.assertEqual(legacy.count("proxy_ssl_verify on;"), expected_routes)
        self.assertEqual(legacy.count("proxy_ssl_name prp-test.micor.top;"), expected_routes)
        self.assertNotIn("proxy_pass http://127.0.0.1:18082;", legacy)
        for bad in ("/tmp/../ca.pem", "/tmp/ca.pem\\n",
                    "/tmp/ca.pem;proxy_ssl_verify off;", "relative.pem"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                render_approval_routes(bad)

    def test_v2_url_cannot_use_foreign_host_or_broad_api_routes(self):
        rendered = render_readonly_link_routes()
        self.assertIn("proxy_set_header Host prp-test.micor.top;", rendered)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", rendered)
        self.assertNotIn("proxy_pass http://127.0.0.1:18081;", rendered)
        self.assertNotIn("location ^~ /api/", rendered)
        self.assertNotIn("location = /api/finance", rendered)
        self.assertNotIn("location = /api/mcp/approval/drafts", rendered)


if __name__ == "__main__":
    unittest.main()
