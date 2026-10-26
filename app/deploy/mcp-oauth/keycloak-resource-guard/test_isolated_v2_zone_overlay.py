#!/usr/bin/env python3
"""Security regressions for exact one-zone import into disposable nginx -t."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import isolated_v2_zone_overlay as mod

SOURCE = b"limit_req_zone $binary_remote_addr zone=prp_demo:10m rate=5r/s;\n"

class V2ZoneOverlayTests(unittest.TestCase):
    def test_exact_single_zone_copied_unchanged(self):
        stmt = mod.parse_sanitized_definition(SOURCE, "prp_demo")
        self.assertEqual(stmt, SOURCE.decode().strip())

    def test_missing_zone_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "EXPECTED_ONE"):
            mod.parse_sanitized_definition(SOURCE, "other_zone")

    def test_duplicate_declarations_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "EXPECTED_ONE"):
            mod.parse_sanitized_definition(SOURCE * 2, "prp_demo")

    def test_reject_unreviewed_expression(self):
        src = b'limit_req_zone "$remote_addr:$uri" zone=prp_demo:10m rate=5r/s;\n'
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_SYNTAX"):
            mod.parse_sanitized_definition(src, "prp_demo")

    def test_reject_other_directives_on_same_line(self):
        src = (b"limit_req_zone $remote_addr zone=prp_demo:10m rate=5r/s;"
               b" proxy_pass http://127.0.0.1:18082;\n")
        self.assertEqual(mod.parse_sanitized_definition(src, "prp_demo"),
                         "limit_req_zone $remote_addr zone=prp_demo:10m rate=5r/s;")
        # The only bytes eligible for injection are the single zone statement.

    def test_multiline_zone_is_normalized_without_semantic_changes(self):
        src = (b"limit_req_zone $binary_remote_addr\n"
               b" zone=prp_demo:10m\n rate=5r/s;\n")
        stmt = mod.parse_sanitized_definition(src, "prp_demo")
        self.assertEqual(stmt, SOURCE.decode().strip())

    def test_unknown_optional_modifier_fails_closed(self):
        src = b"limit_req_zone $binary_remote_addr zone=prp_demo:10m rate=5r/s sync;\n"
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_SYNTAX"):
            mod.parse_sanitized_definition(src, "prp_demo")

    def test_find_source_requires_pinned_provenance(self):
        with patch.object(mod.syntax, "inspect_sources", return_value={}):
            with patch.object(mod.lineage, "inspect", return_value={"status": "NO_MATCH"}):
                with self.assertRaisesRegex(ValueError, "NOT_APPROVED"):
                    mod.find_verified_source()

    def test_unique_live_definition_is_bound_to_matching_zone(self):
        active_path = Path("/etc/nginx/conf.d/demo.conf")
        candidate_sources = {
            "review_main": b"server { listen 443 ssl; }\n",
            "review_test": b"limit_req zone=prp_demo burst=3;\n",
        }
        trace_report = {
            "status": "MISSING_ZONE_DEFINED_IN_ACTIVE_INCLUDE_GRAPH",
            "candidate_req_zone_missing_count": 1,
            "candidate_conn_zone_missing_count": 0,
            "matching_definition_locations": {"NGINX_CONF_D": 1},
            "matching_definition_count": 1,
        }
        actual_set = {active_path: ({"req": {"prp_demo"}, "conn": set()},
                                    {"req": set(), "conn": set()})}
        with patch.object(mod.syntax, "inspect_sources", return_value=candidate_sources), \
             patch.object(mod.lineage, "inspect", return_value=trace_report), \
             patch.object(mod.lineage, "collect", return_value=actual_set), \
             patch.object(mod.lineage, "category", return_value="NGINX_CONF_D"), \
             patch.object(mod.lineage, "safe_read", return_value=SOURCE):
            out = mod.find_verified_source()
        self.assertEqual(out[1], active_path)
        self.assertEqual(out[2], hashlib.sha256(SOURCE).hexdigest())
        self.assertEqual(out[3], SOURCE.decode().strip())

    def test_symlink_and_scope_not_inferred_from_green_syntax(self):
        self.assertFalse("release_approved" in SOURCE.decode())

if __name__ == "__main__":
    unittest.main()
