import unittest
from render_nginx import public_host, render


class OAuthNginxRouteTests(unittest.TestCase):
    def test_exact_three_public_paths_preserve_backend_api_prefix(self):
        text = render("mcp.staging.example.org")
        self.assertIn("location = /api/mcp {", text)
        self.assertIn("location = /api/mcp/link {", text)
        self.assertIn("location = /.well-known/oauth-protected-resource/api/mcp {", text)
        self.assertEqual(text.count("proxy_pass http://127.0.0.1:11000;"), 3)
        self.assertEqual(text.count("proxy_set_header Host mcp.staging.example.org;"), 3)
        self.assertEqual(text.count("proxy_set_header X-Forwarded-Proto https;"), 3)
        self.assertEqual(text.count("if ($host != mcp.staging.example.org) { return 421; }"), 3)
        self.assertNotIn("location /api/", text)
        self.assertNotIn("location /prp/", text)
        self.assertNotIn("proxy_pass http://127.0.0.1:11000/;", text)
        self.assertNotIn("location = /prp/api/mcp", text)

    def test_origin_host_validation_rejects_header_injection(self):
        for host in ("micor.top;return 200", "http://micor.top", "micor.top:443",
                     "127.0.0.1", "localhost", "evil.test/route",
                     "$host", "host\nInjected", "a..example.org", "-evil.test"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                public_host(host)

    def test_dns_hostname_case_normalized(self):
        self.assertEqual(public_host("MCP.STAGING.EXAMPLE.ORG"), "mcp.staging.example.org")


if __name__ == "__main__":
    unittest.main()
