#!/usr/bin/env python3
"""No-network create-only candidate tests; sources and output are synthetic."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_v2_raw_uri_review as mod

REVIEW_TEST = b"""limit_req_zone $binary_remote_addr zone=synthetic:10m rate=5r/s;
server {
 listen 443 ssl;
 location = /api/mcp {
     proxy_pass http://127.0.0.1:18082;
 }
 location = /.well-known/oauth-protected-resource/api/mcp {
     proxy_pass http://127.0.0.1:18082;
 }
 location / { return 404; }
}
server { listen 80; return 421; }
"""

class PreparedV2RawUriReviewTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.sources = {
            "active_main": b"server {listen 443 ssl; return 404;}\n",
            "active_test": b"server {listen 443 ssl; return 404;}\n",
            "review_main": b"server {listen 443 ssl; return 421;}\n",
            "review_test": REVIEW_TEST,
        }
        self.pins = {key: (Path("/unused/" + key), hashlib.sha256(raw).hexdigest())
                     for key, raw in self.sources.items()}

    def prepare(self):
        with patch.object(mod.pins, "FILES", self.pins):
            return mod.build(self.sources)

    def test_only_two_review_vhosts_created_and_main_is_unchanged(self):
        before = self.sources.copy()
        generated, report = self.prepare()
        self.assertEqual(set(generated), {mod.MAIN_FILENAME, mod.TEST_FILENAME})
        self.assertEqual(generated[mod.MAIN_FILENAME], before["review_main"])
        after = generated[mod.TEST_FILENAME]
        self.assertEqual(after.count(b"if ($request_uri !="), 2)
        self.assertEqual(after.count(b"proxy_pass http://127.0.0.1:18082;"), 2)
        self.assertEqual(before, self.sources)
        self.assertEqual(report["review_test_candidate_sha256"],
                         hashlib.sha256(after).hexdigest())
        self.assertEqual(report["status"], "REVIEW_ONLY_V2_RAW_URI_CANDIDATE_PREPARED")
        self.assertFalse(report["candidate_runtime_tested"])
        self.assertFalse(report["release_approved"])
        self.assertFalse(report["host_guard_install_authorized"])
        self.assertFalse(report["manifest_authorized"])
        self.assertFalse(report["active_configuration_changed"])

    def test_can_only_create_fresh_private_review_directory(self):
        generated, report = self.prepare()
        dest = self.root / "review-only-v2-guard-rawuri-synthetic"
        mod.create_review(dest, generated, report, root=self.root)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o700)
        self.assertEqual(set(p.name for p in dest.iterdir()),
                         set(generated) | {"review-report.json"})
        self.assertEqual((dest / mod.TEST_FILENAME).stat().st_mode & 0o777, 0o600)
        saved = json.loads((dest / "review-report.json").read_text())
        self.assertFalse(saved["release_approved"])
        self.assertEqual((dest / mod.TEST_FILENAME).read_bytes(),
                         generated[mod.TEST_FILENAME])
        with self.assertRaises(FileExistsError):
            mod.create_review(dest, generated, report, root=self.root)

    def test_never_writes_to_arbitrary_or_etc_paths(self):
        generated, report = self.prepare()
        for dest in (self.root / "misc",
                     self.root / "review-only-v2-guard-rawuri" / "etc",
                     Path("/etc/nginx/conf.d/review-only-v2-guard-rawuri")):
            with self.subTest(dest=str(dest)):
                with self.assertRaises(ValueError):
                    mod.create_review(dest, generated, report, root=self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_source_checksum_drift_is_hard_failure(self):
        self.sources["review_test"] += b"\n# unseen change\n"
        with self.assertRaisesRegex(ValueError, "REVIEW_ONLY_SOURCE_SHA256_MISMATCH"):
            self.prepare()

    def test_extra_keys_block_unbounded_file_input(self):
        self.sources["unreviewed"] = b"data"
        with self.assertRaisesRegex(ValueError, "REVIEW_ONLY_SOURCE_SET_MISMATCH"):
            self.prepare()

    def test_no_extra_candidate_server_is_accepted(self):
        self.sources["review_test"] += b"server { listen 8080; return 404; }\n"
        self.pins["review_test"] = (Path("/unused/test"),
                                   hashlib.sha256(self.sources["review_test"]).hexdigest())
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_CANDIDATE_SERVER_LAYOUT"):
            self.prepare()

if __name__ == "__main__":
    unittest.main()
