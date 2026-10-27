#!/usr/bin/env python3
"""No-network tests for sanitized V2 route-level classification."""
import unittest

import audit_v2_route_semantics as mod

def pair(extra_test=b"", other_proxy=b""):
    main = (b"""
server {
 listen 443 ssl http2;
 listen [::]:443 ssl;
 if ($host != micor.top) { return 421; }
 location / { return 404; }
 location /api/ { return 403; }
}
server {
 listen 80;
 listen [::]:80;
 return 421;
}
""")
    test = (b"""
server {
 listen 443 ssl;
 listen [::]:443 ssl;
 if ($host != prp-test.micor.top) { return 421; }
 location = /api/mcp {
     proxy_pass http://127.0.0.1:18082;
 }
 location = /api/mcp/link {
     proxy_pass http://127.0.0.1:18082;
 }
 location / { return 404; }
 location /api/ { return 403; }
""" + extra_test + other_proxy + b"""
}
server {
 listen 80;
 listen [::]:80;
 return 421;
}
""")
    return {"review_main": main, "review_test": test}

class RouteSemanticsTests(unittest.TestCase):
    def test_exact_v2_destinations_and_denied_wide_prefixes(self):
        result = mod.inspect(pair())
        self.assertEqual(result["status"], "V2_ROUTE_SEMANTICS_INVENTORIED")
        self.assertEqual(result["test"]["v2_proxy_directives"], 2)
        self.assertEqual(result["test"]["v2_behind_exact_locations"], 2)
        self.assertEqual(result["test"]["v2_behind_non_exact_locations"], 0)
        self.assertEqual(result["test"]["broad_prefix_locations"], 2)
        self.assertEqual(result["test"]["broad_prefix_with_proxy"], 0)
        self.assertEqual(result["test"]["broad_prefix_returning_403_404"], 2)
        self.assertIn("TEST_VHOST_HTTP2_NOT_EXPLICITLY_DECLARED", result["findings"])
        self.assertFalse(result["security_runtime_acceptance_passed"])

    def test_broad_proxy_is_flagged_not_silently_approved(self):
        item = pair(other_proxy=b"location /api/ { proxy_pass http://127.0.0.1:11000; }\n")
        result = mod.inspect(item)
        self.assertEqual(result["test"]["broad_prefix_with_proxy"], 1)
        self.assertIn("BROAD_PREFIX_PROXY_REQUIRES_AUTHORIZATION_REVIEW", result["findings"])

    def test_external_proxy_identified_without_leaking_address(self):
        item = pair(extra_test=b"location /callback/ { proxy_pass https://private.example.test:443; }\n")
        result = mod.inspect(item)
        self.assertEqual(result["test"]["nonloopback_or_variable_upstream_directives"], 1)
        self.assertNotIn("private.example.test", str(result))
        self.assertIn("TEST_UPSTREAM_TARGETS_REQUIRE_MANUAL_REVIEW", result["findings"])

    def test_v2_in_non_exact_location_requires_review(self):
        raw = b"location /v2/ { proxy_pass http://127.0.0.1:18082; }\n"
        item = pair(extra_test=raw)
        with self.assertRaisesRegex(ValueError, "V2_BACKEND_TARGET_DRIFT"):
            mod.inspect(item)
        item["review_test"] = item["review_test"].replace(
            b"location = /api/mcp/link {\n     proxy_pass http://127.0.0.1:18082;\n }",
            b"location = /api/mcp/link { return 403; }")
        result = mod.inspect(item)
        self.assertEqual(result["test"]["v2_behind_non_exact_locations"], 1)
        self.assertIn("V2_TARGET_NOT_EXCLUSIVELY_EXACT_MATCHED", result["findings"])

    def test_comment_and_quoted_literals_not_parsed_as_upstreams(self):
        location = mod.audit.parse(
            b'location / { set $v "proxy_pass http://evil;"; # fake line\n'
            b'return 403; }\n')[0]
        result = mod.route_info(location)
        self.assertEqual(result["proxy"], 0)
        self.assertEqual(result["returns_403_or_404"], 1)

    def test_protected_resource_well_known_is_not_mcp_tool_endpoint(self):
        node = mod.audit.parse(
            b'location = /.well-known/oauth-protected-resource/api/mcp { return 200; }'
        )[0]
        info = mod.route_info(node)
        self.assertEqual(info["mcp_shape"], "EXACT_OAUTH_DISCOVERY")
        self.assertNotEqual(info["mcp_shape"], "EXACT_MCP")

    def test_exact_mcp_link_is_not_mcp_tool_endpoint(self):
        node = mod.audit.parse(
            b'location = /api/mcp/link { proxy_pass http://127.0.0.1:18082; }'
        )[0]
        self.assertEqual(mod.route_info(node)["mcp_shape"], "EXACT_MCP_LINK")

    def test_no_server_names_or_paths_in_result(self):
        result = mod.inspect(pair())
        rendered = str(result)
        self.assertNotIn("micor.top", rendered)
        self.assertNotIn("/api/mcp", rendered)
        self.assertFalse(result["guard_install_or_reload_authorized"])

if __name__ == "__main__":
    unittest.main()
