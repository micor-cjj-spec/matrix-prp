#!/usr/bin/env python3
"""Offline tests for safe, read-only trace of Nginx limiter provenance."""
import tempfile
import unittest
from pathlib import Path

import trace_v2_limit_zone as mod

class LimitZoneTraceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / "etc" / "nginx"
        self.base.mkdir(parents=True)
        self.conf = self.base / "conf.d"
        self.conf.mkdir()
        self.root = self.base / "nginx.conf"
        self.root.write_text(
            "events {} \nhttp {\n  include " + str(self.conf / "*.conf") + ";\n}\n")

    def inspect(self, review_test):
        return mod.inspect(
            {"review_main": b"server { listen 443 ssl; }\n",
             "review_test": review_test.encode("utf-8")},
            active_root=self.root, base=self.base)

    def test_missing_rate_zone_defined_in_active_included_config(self):
        (self.conf / "security.conf").write_text(
            "limit_req_zone $binary_remote_addr zone=test_named_zone:10m rate=3r/s;\n")
        result = self.inspect("limit_req zone=test_named_zone burst=5;\n")
        self.assertEqual(result["status"], "MISSING_ZONE_DEFINED_IN_ACTIVE_INCLUDE_GRAPH")
        self.assertEqual(result["matching_definition_count"], 1)
        self.assertEqual(result["matching_definition_locations"], {"NGINX_CONF_D": 1})
        self.assertEqual(result["candidate_req_zone_missing_count"], 1)
        self.assertNotIn("test_named_zone", str(result))
        self.assertNotIn(str(self.root), str(result))

    def test_missing_zone_not_found_in_active_include_graph(self):
        (self.conf / "other.conf").write_text(
            "limit_req_zone $binary_remote_addr zone=other_zone:10m rate=3r/s;\n")
        result = self.inspect("limit_req zone=missing_zone burst=3;\n")
        self.assertEqual(result["status"], "MISSING_ZONE_NOT_DEFINED_IN_ACTIVE_INCLUDE_GRAPH")
        self.assertEqual(result["matching_definition_count"], 0)

    def test_missing_included_file_refuses_complete_graph_claim(self):
        self.root.write_text("http { include " + str(self.base / "absent.conf") + "; }\n")
        with self.assertRaisesRegex(ValueError, "REQUIRED_INCLUDE_MISSING"):
            self.inspect("limit_req zone=unresolved burst=5;\n")

    def test_include_outside_allowlist_fails_closed(self):
        self.root.write_text("http { include /tmp/unreviewed.conf; }\n")
        with self.assertRaisesRegex(ValueError, "INCLUDE_OUTSIDE_NGINX_TREE"):
            self.inspect("limit_req zone=unresolved burst=5;\n")

    def test_non_nginx_symlink_target_fails_closed(self):
        outside = Path(tempfile.mkdtemp()) / "bad.conf"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        self.addCleanup(lambda: outside.parent.rmdir())
        outside.write_text("limit_req_zone $remote_addr zone=a:10m rate=1r/s;\n")
        (self.conf / "alias.conf").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "INCLUDE_OUTSIDE_NGINX_TREE"):
            self.inspect("limit_req zone=a burst=3;\n")

    def test_explicit_zone_definition_satisfies_candidate(self):
        with self.assertRaisesRegex(ValueError, "EXPECTED_EXACTLY_ONE_MISSING_REQUEST_ZONE"):
            self.inspect(
                "limit_req_zone $binary_remote_addr zone=a:10m rate=2r/s;\n"
                "limit_req zone=a burst=2;\n")

    def test_syntax_preserves_multiline_limit_zone(self):
        raw = (b"limit_req_zone $binary_remote_addr\n"
               b" zone=multi_zone:10m rate=5r/s;\n"
               b"limit_req zone=multi_zone burst=3;\n")
        defs, refs, inc = mod.parse_config(raw)
        self.assertEqual(defs["req"], {"multi_zone"})
        self.assertEqual(refs["req"], {"multi_zone"})
        self.assertFalse(inc)

    def test_comments_cannot_invent_zone_definitions(self):
        raw = (b"# limit_req_zone $remote_addr zone=hide:10m rate=1r/s;\n"
               b"limit_req zone=hide burst=2;\n")
        defs, refs, _ = mod.parse_config(raw)
        self.assertFalse(defs["req"])
        self.assertEqual(refs["req"], {"hide"})

if __name__ == "__main__":
    unittest.main()
