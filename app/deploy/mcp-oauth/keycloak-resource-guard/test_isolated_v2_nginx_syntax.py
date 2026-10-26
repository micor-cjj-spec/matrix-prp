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

    def test_shared_memory_error_subcategories_are_fixed_labels(self):
        checks = {
            'nginx: [emerg] zero size shared memory zone "secret_zone"':
                "ZERO_SIZE_OR_UNDEFINED_ZONE",
            'nginx: [emerg] zone "internal" is too small':
                "ZONE_TOO_SMALL",
            'nginx: [emerg] shared memory zone "internal" conflicts with already declared size':
                "ZONE_SIZE_CONFLICT",
            'nginx: [emerg] limit_req_zone "internal" is already bound':
                "ZONE_REDEFINITION",
            'nginx: [emerg] mmap() failed (12: Cannot allocate memory)':
                "SHM_ALLOCATION_FAILED",
        }
        for raw, expected in checks.items():
            with self.subTest(expected=expected):
                result = mod.classify_shared_memory_error(raw)
                self.assertEqual(result, expected)
                self.assertNotIn("secret_zone", result)
                self.assertNotIn("internal", result)

    def test_rate_limit_zone_inventory_identifies_unresolved_only(self):
        (self.root / "main.conf").write_text(
            "limit_req_zone $binary_remote_addr zone=global_a:10m rate=5r/s;\n"
            "limit_conn_zone $binary_remote_addr zone=conn_a:10m;\n"
        )
        (self.root / "test.conf").write_text(
            "server {\n"
            "limit_req zone=global_a burst=2;\n"
            "limit_req zone=zone_missing burst=3;\n"
            "limit_conn conn_a 2;\n"
            "limit_conn conn_missing 3;\n"
            "}\n"
        )
        result = mod.inspect_limit_zones(self.root)
        self.assertEqual(result["candidate_req_defined"], 1)
        self.assertEqual(result["candidate_req_referenced"], 2)
        self.assertEqual(result["candidate_req_missing_definitions"], 1)
        self.assertEqual(result["candidate_conn_defined"], 1)
        self.assertEqual(result["candidate_conn_referenced"], 2)
        self.assertEqual(result["candidate_conn_missing_definitions"], 1)
        self.assertNotIn("global_a", str(result))
        self.assertNotIn("zone_missing", str(result))

    def test_rate_limit_inventory_ignores_comment_lines(self):
        (self.root / "main.conf").write_text(
            "# limit_req_zone $remote_addr zone=fake:20m rate=1r/s;\n"
        )
        (self.root / "test.conf").write_text(
            "limit_req zone=real_missing burst=1;\n"
        )
        result = mod.inspect_limit_zones(self.root)
        self.assertEqual(result["candidate_req_defined"], 0)
        self.assertEqual(result["candidate_req_missing_definitions"], 1)

    def test_existing_active_zone_restored_without_touching_original(self):
        base = self.root / "etc/nginx"
        confd = base / "conf.d"
        confd.mkdir(parents=True)
        root = base / "nginx.conf"
        root.write_text("events {}\nhttp { include " + str(confd / "*.conf") + "; }\n")
        original = (
            "limit_req_zone $binary_remote_addr zone=approved_zone:10m rate=5r/s;\n"
            "server { return 403; }\n"
        )
        active = confd / "security.conf"
        active.write_text(original)
        (self.root / "main.conf").write_text("server { limit_req zone=approved_zone burst=2; }\n")
        (self.root / "test.conf").write_text(
            "limit_req zone=approved_zone burst=3;\n"
            "limit_req_zone $binary_remote_addr zone=other_zone:10m rate=2r/s;\n"
        )
        definition, scanned = mod.recover_single_active_rate_limit(
            self.root, root=root, base=base)
        self.assertEqual(definition,
                         "limit_req_zone $binary_remote_addr zone=approved_zone:10m rate=5r/s;")
        self.assertEqual(scanned, 2)
        self.assertEqual(active.read_text(), original)
        self.assertNotIn("server", definition)
        self.assertNotIn("burst", definition)

    def test_original_zone_rate_and_key_are_not_rewritten(self):
        base = self.root / "etc/nginx"
        base.mkdir(parents=True)
        root = base / "nginx.conf"
        original = "limit_req_zone $remote_addr zone=approved_zone:16m rate=9r/m;\n"
        root.write_text("events {}\nhttp {\n" + original + "}\n")
        (self.root / "main.conf").write_text("limit_req zone=approved_zone burst=4;\n")
        (self.root / "test.conf").write_text("")
        definition, _ = mod.recover_single_active_rate_limit(
            self.root, root=root, base=base)
        self.assertEqual(definition, original.strip())

    def test_duplicate_active_zone_definition_blocks(self):
        base = self.root / "etc/nginx"
        confd = base / "conf.d"
        confd.mkdir(parents=True)
        root = base / "nginx.conf"
        root.write_text("http { include " + str(confd / "*.conf") + "; }\n")
        for label in ("a", "b"):
            (confd / (label + ".conf")).write_text(
                "limit_req_zone $binary_remote_addr zone=x:10m rate=5r/s;\n")
        (self.root / "main.conf").write_text("limit_req zone=x burst=1;\n")
        (self.root / "test.conf").write_text("")
        with self.assertRaisesRegex(ValueError, "EXPECTED_EXACTLY_ONE_ACTIVE_ZONE_DEFINITION"):
            mod.recover_single_active_rate_limit(self.root, root=root, base=base)

    def test_zone_with_unreviewed_extra_token_blocks(self):
        base = self.root / "etc/nginx"
        base.mkdir(parents=True)
        root = base / "nginx.conf"
        root.write_text("limit_req_zone $binary_remote_addr "
                        "zone=x:10m rate=5r/s sync;\n")
        (self.root / "main.conf").write_text("limit_req zone=x burst=1;\n")
        (self.root / "test.conf").write_text("")
        with self.assertRaisesRegex(ValueError, "MATCHING_RATE_LIMIT_DEFINITION_UNREVIEWED"):
            mod.recover_single_active_rate_limit(self.root, root=root, base=base)

    def test_zone_not_defined_blocks_without_synthesizing(self):
        base = self.root / "etc/nginx"
        base.mkdir(parents=True)
        root = base / "nginx.conf"
        root.write_text("events {}\n")
        (self.root / "main.conf").write_text("limit_req zone=absent burst=2;\n")
        (self.root / "test.conf").write_text("")
        with self.assertRaisesRegex(ValueError, "EXPECTED_EXACTLY_ONE_ACTIVE_ZONE_DEFINITION"):
            mod.recover_single_active_rate_limit(self.root, root=root, base=base)

    def test_escaped_include_aborts_before_sandbox_nginx_test(self):
        base = self.root / "etc/nginx"
        base.mkdir(parents=True)
        root = base / "nginx.conf"
        root.write_text("http { include /etc/shadow; }\n")
        (self.root / "main.conf").write_text("limit_req zone=x burst=1;\n")
        (self.root / "test.conf").write_text("")
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_NGINX_INCLUDE_PATTERN"):
            mod.recover_single_active_rate_limit(self.root, root=root, base=base)

    def test_input_symlink_refused(self):
        target = self.root / "regular.conf"
        target.write_bytes(MAIN)
        link = self.root / "link.conf"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            mod.read_regular(link)

if __name__ == "__main__":
    unittest.main()
