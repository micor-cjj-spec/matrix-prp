#!/usr/bin/env python3
"""Pure offline V2 candidate verification tests: no Nginx or public calls."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import patch

import verify_v2_raw_uri_review_artifact as mod


BASE = b"""limit_req_zone $binary_remote_addr zone=testzone:10m rate=5r/s;
server {
 listen 443 ssl;
 location = /api/mcp { proxy_pass http://127.0.0.1:18082; }
 location = /.well-known/oauth-protected-resource/api/mcp {
   proxy_pass http://127.0.0.1:18082;
 }
 location / { return 404; }
}
server { listen 80; return 421; }
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RawUriReviewVerificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        self.directory = self.root / "review-only-v2-guard-20261027-rawuri-01"
        self.directory.mkdir(mode=0o700)
        self.sources = {
            "active_main": b"active main\n",
            "active_test": b"active test\n",
            "review_main": b"review main\n",
            "review_test": BASE,
        }
        self.pins = {
            k: (self.root / (k + ".conf"), sha(v))
            for k, v in self.sources.items()
        }
        with patch.object(mod.isolated, "FILES", self.pins):
            self.generated, self.manifest = mod.candidate.build(self.sources)
        for name, raw in {
            **self.generated,
            "review-report.json": json.dumps(self.manifest).encode(),
        }.items():
            p = self.directory / name
            p.write_bytes(raw)
            p.chmod(0o600)

    def check(self):
        with patch.object(mod.isolated, "FILES", self.pins):
            files = mod.checked_files(self.directory, self.root)
            return mod.verify_artifact(
                files, self.sources,
                expected_main=sha(self.generated[mod.candidate.MAIN_FILENAME]),
                expected_test=sha(self.generated[mod.candidate.TEST_FILENAME]))

    def test_review_pair_exact_and_manifest_is_untouched(self):
        main, test, result = self.check()
        self.assertEqual(main, self.sources["review_main"])
        self.assertEqual(test, self.generated[mod.candidate.TEST_FILENAME])
        self.assertTrue(result["test_exactly_two_raw_uri_guards_against_old_review"])
        self.assertTrue(result["source_four_sha256_pins_verified"])
        self.assertTrue(result["review_manifest_provenance_verified"])
        self.assertEqual(test.count(b"if ($request_uri !="), 2)

    def test_drifted_review_candidate_blocks_even_if_it_is_readable(self):
        name = mod.candidate.TEST_FILENAME
        (self.directory / name).write_bytes(self.generated[name] + b"# injected\n")
        with self.assertRaisesRegex(ValueError, "NEW_REVIEW_CANDIDATE_SHA256_DRIFT"):
            self.check()

    def test_manifest_tamper_blocks(self):
        self.manifest["release_approved"] = True
        (self.directory / "review-report.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "REVIEW_MANIFEST_LINEAGE_DRIFT"):
            self.check()

    def test_unreviewed_extra_file_blocks(self):
        extra = self.directory / "unexpected.conf"
        extra.write_text("server {}")
        extra.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "REVIEW_DIRECTORY_CONTENTS_DRIFT"):
            mod.checked_files(self.directory, self.root)

    def test_symlink_and_non_private_artifacts_block(self):
        name = mod.candidate.MAIN_FILENAME
        original = self.directory / name
        linked = self.root / "linked"
        linked.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(linked)
        with self.assertRaisesRegex(ValueError, "REVIEW_FILE_METADATA_UNSAFE"):
            mod.checked_files(self.directory, self.root)
        original.unlink()
        original.write_bytes(self.generated[name])
        original.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "REVIEW_FILE_METADATA_UNSAFE"):
            mod.checked_files(self.directory, self.root)

    def test_review_directory_permissions_and_escape_block(self):
        self.directory.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "REVIEW_DIRECTORY_NOT_PRIVATE"):
            mod.checked_files(self.directory, self.root)
        with self.assertRaisesRegex(ValueError, "REVIEW_DIRECTORY_OUTSIDE_ALLOWED_PARENT"):
            mod.checked_files(self.root, self.root)

    def test_syntax_check_only_uses_nginx_t_and_synthetic_material(self):
        calls = []
        def mocked_run(argv, **kwargs):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        def mock_prepare(source, root):
            self.assertEqual(source["review_test"], self.generated[mod.candidate.TEST_FILENAME])
            self.assertEqual(source["review_main"], self.generated[mod.candidate.MAIN_FILENAME])
            (root / "main.conf").write_text("server { listen 8088; }\n")
            (root / "test.conf").write_text("server { listen 8089; }\n")
            return {"includes": 0, "tls_replacements": 0, "log_replacements": 0}
        with patch.object(mod.shutil, "which",
                          side_effect=lambda name: "/fake/" + name), \
             patch.object(mod.subprocess, "run", side_effect=mocked_run), \
             patch.object(mod.isolated, "prepare", side_effect=mock_prepare), \
             patch.object(mod.isolated, "recover_single_active_rate_limit",
                          return_value=("limit_req_zone $binary_remote_addr zone=x:10m rate=5r/s;", 6)):
            output = mod.check_nginx((
                self.generated[mod.candidate.MAIN_FILENAME],
                self.generated[mod.candidate.TEST_FILENAME]),
                self.sources, temp_parent=self.root)
        self.assertTrue(output["syntax_passed"])
        self.assertTrue(output["no_nginx_listener_started"])
        self.assertEqual(output["dependency_config_files_scanned"], 6)
        self.assertTrue(any("-t" in cmd for cmd in calls))
        self.assertFalse(any("-s" in cmd or "reload" in cmd or "daemon off;" in cmd for cmd in calls))

if __name__ == "__main__":
    unittest.main()
