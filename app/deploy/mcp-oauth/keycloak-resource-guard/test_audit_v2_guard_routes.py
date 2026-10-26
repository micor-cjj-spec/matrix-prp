#!/usr/bin/env python3
"""Synthetic, no-network regressions for pinned V2 Nginx route inventory."""
import unittest
import audit_v2_guard_routes as audit

def vhost(name, dest="http://127.0.0.1:18082"):
    return (f"""# quote and commented routes should not be counted
server {{
    listen 443 ssl http2;
    listen [::]:443 ssl;
    server_name {name};
    if ($host != {name}) {{ return 421; }}
    location = /api/mcp {{ proxy_pass {dest}; }}
    location /other {{ return 404; }}
}}
server {{
    listen 80;
    listen [::]:80;
    return 421;
}}
""").encode()

class RouteInventorySafetyTests(unittest.TestCase):
    def test_exact_pinned_staging_route_aggregate(self):
        main = vhost("micor.top", "http://127.0.0.1:11000")
        test = (vhost("prp-test.micor.top")+
                b"# synthetic V2 route\n"
                b"location = /api/mcp/link { proxy_pass http://127.0.0.1:18082; }\n")
        result = audit.inspect({"review_main":main, "review_test":test})
        self.assertEqual(result["status"], "PINNED_V2_ROUTE_SURFACE_INVENTORIED")
        self.assertEqual(result["candidate_main"]["listen_directives"], 4)
        self.assertEqual(result["candidate_test"]["explicit_loopback_v2_proxy_pass"], 2)
        self.assertEqual(result["candidate_main"]["host_mismatch_reject_421_mentions"], 2)
        self.assertFalse(result["http_tls_sni_h2_ipv6_behavior_proven"])
        self.assertFalse(result["guard_install_or_reload_authorized"])

    def test_comments_and_quote_delimiters_ignored(self):
        nodes = audit.parse(b'server { set $a "alpha;{secret}"; # proxy_pass http://evil;\n'
                            b'location = /api/mcp { return 421; } }\n')
        values = list(audit.walk(nodes))
        self.assertEqual(sum(n[0] == "proxy_pass" for n in values), 0)
        self.assertEqual(sum(n[0] == "return" for n in values), 1)
        self.assertEqual(nodes[0][2][0][1], ("$a","alpha;{secret}"))

    def test_nested_unterminated_brace_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "NGINX_MISSING_CLOSING_BRACE"):
            audit.parse(b"server { location / { return 421; }\n")

    def test_unterminated_quote_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNTERMINATED_NGINX_QUOTE"):
            audit.parse(b'server { return "unclosed; }\n')

    def test_active_legacy_mcp_target_in_review_refused(self):
        main = vhost("micor.top","http://127.0.0.1:11000")
        test = vhost("prp-test.micor.top")+b"\nproxy_pass http://127.0.0.1:18081;\n"
        with self.assertRaisesRegex(ValueError,"V2_BACKEND_TARGET_DRIFT"):
            audit.inspect({"review_main":main,"review_test":test})

    def test_wrong_v2_proxy_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "V2_BACKEND_TARGET_DRIFT"):
            audit.inspect({"review_main":vhost("micor.top","http://127.0.0.1:11000"),
                           "review_test":vhost("prp-test.micor.top")})

    def test_no_network_or_host_info_ever_output(self):
        result = audit.inspect({
            "review_main":vhost("private.micor.top","http://127.0.0.1:11000"),
            "review_test":vhost("private.micor.top")+
                          b"location = /api/mcp/link { proxy_pass http://127.0.0.1:18082; }\n"
        })
        rendered = str(result)
        self.assertNotIn("private.micor.top",rendered)
        self.assertNotIn("/etc/",rendered)

if __name__ == "__main__":
    unittest.main()
