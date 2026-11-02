import tempfile
from pathlib import Path
import unittest
from prepare_env import make_config
from render_tls import render, write_once
from check_env import check


class StagingTLSVHostTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config("prp-test.micor.top", "auth-test.micor.top", "stage_admin")

    def test_strictly_segregated_https_upstreams(self):
        config = render(self.config)
        self.assertEqual(config.count("listen 443 ssl;"), 2)
        self.assertIn("server_name prp-test.micor.top;", config)
        self.assertIn("server_name auth-test.micor.top;", config)
        self.assertEqual(config.count("proxy_pass http://127.0.0.1:18081;"), 1)
        self.assertEqual(config.count("proxy_pass http://127.0.0.1:18080;"), 1)
        self.assertNotIn("127.0.0.1:11000", config)
        self.assertNotIn("matrix-mysql", config)
        self.assertIn("if ($host != prp-test.micor.top) { return 421; }", config)
        self.assertIn("if ($host != auth-test.micor.top) { return 421; }", config)
        self.assertIn("location ^~ /admin/ { return 404; }", config)
        self.assertIn("location ^~ /realms/master/ { return 404; }", config)
        self.assertIn("ssl_certificate /etc/letsencrypt/live/prp-test.micor.top/fullchain.pem;", config)
        self.assertIn("ssl_certificate /etc/letsencrypt/live/auth-test.micor.top/fullchain.pem;", config)

    def test_auth_hostname_rejects_nginx_injection(self):
        for auth in ("https://auth-test.micor.top;include evil.conf",
                     "https://auth-test.micor.top:8080",
                     "https://auth_test.micor.top",
                     "https://micor.top", "https://localhost",
                     "https://auth-test.micor.top/other"):
            modified = dict(self.config)
            modified["PRP_STAGE_AUTH_PUBLIC_URL"] = auth
            with self.subTest(auth=auth), self.assertRaises(ValueError):
                check(modified)

    def test_generator_refuses_overwriting_existing_config(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "tls.conf"
            write_once(target, render(self.config))
            with self.assertRaises(FileExistsError):
                write_once(target, render(self.config))

    def test_live_host_is_forbidden(self):
        self.config["PRP_STAGE_PUBLIC_HOST"] = "micor.top"
        self.config["PRP_STAGE_PUBLIC_URL"] = "https://micor.top"
        self.config["PRP_STAGE_MCP_RESOURCE"] = "https://micor.top/api/mcp"
        with self.assertRaisesRegex(ValueError, "non-production"):
            render(self.config)


if __name__ == "__main__":
    unittest.main()
