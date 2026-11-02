#!/usr/bin/env python3
"""No host mutation, synthetic Nginx fixtures and fail-closed lineage check."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("review_v2_nginx_lineage.py")
spec = importlib.util.spec_from_file_location("review_v2_nginx_lineage", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class NginxV2LineageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        self.paths = {name: directory / (name + ".conf")
                      for name in ("active", "backup", "guard_only", "b2_candidate")}
        self.baseline = b"location /api/mcp { proxy_pass http://127.0.0.1:18081; }\n" + (
            b"location /.well-known/oauth-protected-resource/api/mcp { "
            b"proxy_pass http://127.0.0.1:18081; }\n"
        )
        self.guard = b"# hardened guard\n" + self.baseline
        self.b2 = b"# b2 review\n" + self.baseline.replace(
            b"127.0.0.1:18081", b"127.0.0.1:18082", 1
        )
        self.original_hashes = tool.EXPECTED.copy()
        tool.EXPECTED.update({
            "backup": hashlib.sha256(self.baseline).hexdigest(),
            "guard_only": hashlib.sha256(self.guard).hexdigest(),
            "b2_candidate": hashlib.sha256(self.b2).hexdigest(),
        })
        self.addCleanup(lambda: (tool.EXPECTED.clear(), tool.EXPECTED.update(self.original_hashes)))
        self.paths["backup"].write_bytes(self.baseline)
        self.paths["guard_only"].write_bytes(self.guard)
        self.paths["b2_candidate"].write_bytes(self.b2)
        self.paths["active"].write_bytes(self.baseline.replace(
            b"127.0.0.1:18081", b"127.0.0.1:18082"
        ))

    def check_no_approval(self, result):
        self.assertFalse(result["guard_only_install_approved"])
        self.assertFalse(result["b2_cutover_approved"])
        self.assertTrue(result["no_write_or_reload"])
        self.assertTrue(result["no_config_content_printed"])

    def test_exact_port_only_change(self):
        result = tool.inspect(self.paths)
        self.assertEqual(result["status"], "ACTIVE_PORT_ONLY_CHANGE_FROM_PINNED_BACKUP")
        self.assertTrue(result["normalized_active_matches_historical_backup"])
        self.assertEqual(result["route_counts"]["active"]["v2_18082"], 2)
        self.assertEqual(result["route_counts"]["backup"]["old_18081"], 2)
        self.assertEqual(result["guard_v2_projection_status"], "HYPOTHETICAL_NOT_TESTED_OR_APPROVED")
        self.check_no_approval(result)

    def test_extra_security_change_must_not_be_labeled_port_only(self):
        self.paths["active"].write_bytes(self.paths["active"].read_bytes() +
                                         b"# guard bypass inserted\n")
        result = tool.inspect(self.paths)
        self.assertEqual(result["status"], "ACTIVE_HAS_ADDITIONAL_DIFFS_REVIEW_REQUIRED")
        self.assertFalse(result["normalized_active_matches_historical_backup"])
        self.check_no_approval(result)
        self.assertNotIn("guard bypass", json.dumps(result))

    def test_candidate_tamper_blocks_projection(self):
        self.paths["guard_only"].write_bytes(self.guard + b"unknown\n")
        result = tool.inspect(self.paths)
        self.assertEqual(result["status"], "HISTORIC_SOURCE_DRIFT_REFUSE_PROJECTION")
        self.assertIsNone(result["guard_v2_review_only_projection_sha256"])
        self.check_no_approval(result)

    def test_backup_tamper_blocks_comparison(self):
        self.paths["backup"].write_bytes(self.baseline + b"extra\n")
        result = tool.inspect(self.paths)
        self.assertEqual(result["status"], "HISTORIC_SOURCE_DRIFT_REFUSE_PROJECTION")
        self.assertFalse(result["normalized_active_matches_historical_backup"])
        self.check_no_approval(result)

    def test_symlink_refused(self):
        self.paths["active"].unlink()
        self.paths["active"].symlink_to(self.paths["backup"])
        result = tool.inspect(self.paths)
        self.assertEqual(result["status"], "MISSING_UNSAFE_OR_OVERSIZE_SOURCE")
        self.check_no_approval(result)

    def test_no_raw_config_or_extra_keys_in_output(self):
        self.paths["active"].write_bytes(self.paths["active"].read_bytes() +
                                         b"set $api_secret password=redacted-in-tool;\n")
        result = tool.inspect(self.paths)
        self.assertNotIn("api_secret", json.dumps(result))
        self.assertNotIn("password", json.dumps(result))
        self.check_no_approval(result)


if __name__ == "__main__":
    unittest.main()
