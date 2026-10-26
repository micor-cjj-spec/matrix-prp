#!/usr/bin/env python3
"""Synthetic offline safety tests for isolated_v2_nginx_syntax.py."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import isolated_v2_nginx_syntax as mod

MAIN = b"""map $http_host $prp_review_flag {
    default 0;
}
server {
    listen 443 ssl;
    server_name micor.top;
    ssl_certificate /etc/letsencrypt/live/micor.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/micor.top/privkey.pem;
    access_log /var/log/nginx/production-access.log combined;
    error_log /var/log/nginx/production-error.log warn;
    location / { return 200; }
}
"""
TEST = b"""server {
    listen 443 ssl;
    server_name prp-test.micor.top;
    ssl_certificate /etc/letsencrypt/live/test/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/test/privkey.pem;
    location = /api/mcp {
        proxy_pass http://127.0.0.1:18082;
    }
}
"""

class IsolatedSyntaxSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.inputs = {"review_main": MAIN, "review_test": TEST}

    def test_certificates_and_logs_replaced_but_v2_route_preserved(self):
        counts = mod.prepare(self.inputs, self.root)
        main = (self.root / "main.conf").read_text()
        test = (self.root / "test.conf").read_text()
        self.assertIn(str(self.root / "cert.pem"), main)
        self.assertIn(str(self.root / "key.pem"), main)
        self.assertNotIn("/etc/letsencrypt/live/", main + test)
        self.assertNotIn("/var/log/nginx/", main + test)
        self.assertIn("access_log off;", main)
        self.assertIn("error_log stderr warn;", main)
        self.assertIn("127.0.0.1:18082", test)
        self.assertEqual(counts["tls_replacements"], 4)
        self.assertEqual(counts["log_replacements"], 2)

    def test_compact_inline_private_key_fails_closed(self):
        main = b"server { ssl_certificate_key /etc/letsencrypt/live/test/privkey.pem; }"
        with self.assertRaisesRegex(ValueError, "UNREWRITTEN_KEY"):
            mod.prepare({"review_main": main, "review_test": TEST}, self.root)

    def test_external_upstream_fails_closed(self):
        main = MAIN + b"\nproxy_pass https://unreviewed.example.org/api;\n"
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_PROXY_UPSTREAM"):
            mod.prepare({"review_main": main, "review_test": TEST}, self.root)

    def test_compact_inline_external_upstream_fails_closed(self):
        main = MAIN + b"\nlocation / { proxy_pass https://unreviewed.example.org/api; }\n"
        with self.assertRaisesRegex(ValueError, "UNREWRITTEN_PROXY_UPSTREAM"):
            mod.prepare({"review_main": main, "review_test": TEST}, self.root)

    def test_log_without_own_line_fails_closed(self):
        main = MAIN + b"\nlocation / { access_log /var/log/nginx/leak.log combined; }\n"
        with self.assertRaisesRegex(ValueError, "UNREWRITTEN_ACCESS_LOG"):
            mod.prepare({"review_main": main, "review_test": TEST}, self.root)

    def test_including_live_conf_d_is_never_allowed(self):
        main = MAIN + b"\ninclude /etc/nginx/conf.d/*.conf;\n"
        with self.assertRaisesRegex(ValueError, "UNSAFE_INCLUDE"):
            mod.prepare({"review_main": main, "review_test": TEST}, self.root)

    def test_runtime_pins_reject_any_byte_drift(self):
        fake = {}
        for name in mod.FILES:
            p = self.root / (name + ".conf")
            p.write_bytes(TEST if name == "review_test" else MAIN)
            fake[name] = (p, hashlib.sha256(p.read_bytes()).hexdigest())
        fake["review_main"] = (fake["review_main"][0], "0" * 64)
        with patch.object(mod, "FILES", fake):
            with self.assertRaisesRegex(ValueError, "PINNED_SHA256_DRIFT"):
                mod.inspect_sources()

    def test_sanitized_nginx_error_categories_never_echo_secrets(self):
        raw = (
            'nginx: [emerg] invalid number of arguments in "map" directive '
            'in /root/prp-mcp-cimd-stage-b/syntax-only-v2-private/test.conf:47 '
            'client_secret=SENSITIVE_TEST_SECRET'
        )
        result = mod.classify_nginx_failure(raw)
        self.assertEqual(result["error_family"], "INVALID_ARGUMENT_COUNT")
        self.assertEqual(result["sandbox_source_role"], "REVIEW_TEST")
        self.assertEqual(result["sandbox_line"], 47)
        self.assertTrue(result["raw_error_redacted"])
        self.assertNotIn("SENSITIVE_TEST_SECRET", str(result))
        self.assertNotIn("/root/", str(result))

    def test_sanitized_unknown_error_does_not_expose_content(self):
        raw = "nginx: [emerg] SOME_PRIVATE_VALUE unusual problem happened"
        result = mod.classify_nginx_failure(raw)
        self.assertEqual(result["error_family"], "UNCLASSIFIED")
        self.assertNotIn("SOME_PRIVATE_VALUE", str(result))
        self.assertIsNone(result["sandbox_source_role"])

    def test_sandbox_log_unknown_log_format_classification(self):
        message = ('nginx: [emerg] unknown log format "custom-format" '
                   'in /root/private/include-1.conf:21')
        result = mod.classify_nginx_failure(message)
        self.assertEqual(result["error_family"], "UNKNOWN_LOG_FORMAT")
        self.assertEqual(result["sandbox_source_role"], "REVIEW_INCLUDED_DEPENDENCY")
        self.assertEqual(result["sandbox_line"], 21)

    def test_input_symlink_refused(self):
        target = self.root / "regular.conf"
        target.write_bytes(MAIN)
        link = self.root / "link.conf"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            mod.read_regular(link)

if __name__ == "__main__":
    unittest.main()
