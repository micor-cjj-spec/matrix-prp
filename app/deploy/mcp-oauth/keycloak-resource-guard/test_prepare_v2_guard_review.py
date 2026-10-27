#!/usr/bin/env python3
"""Negative tests proving a V2 review pair cannot silently modify live Nginx."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("prepare_v2_guard_review.py")
spec = importlib.util.spec_from_file_location("prepare_v2_guard_review", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def hash_of(raw):
    return hashlib.sha256(raw).hexdigest()


class V2GuardReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.paths = {name: self.root / (name + ".conf")
                      for name in mod.DEFAULT_FILES}
        self.baseline_main = b"server_name micor.top;\n# fixed map and guard\n"
        self.baseline_test = (b"location /api/mcp { proxy_pass http://127.0.0.1:18081; }\n"
                              b"location /oauth-protected-resource { proxy_pass http://127.0.0.1:18081; }\n")
        self.guard_main = b"server_name micor.top;\n# hardened map and guard\n"
        self.guard_test = b"# hardened header policy\n" + self.baseline_test
        self.active_test = self.baseline_test.replace(mod.OLD, mod.NEW)
        self.data = {
            "active_main": self.baseline_main,
            "active_test": self.active_test,
            "backup_main": self.baseline_main,
            "backup_test": self.baseline_test,
            "guard_main": self.guard_main,
            "guard_test": self.guard_test,
        }
        self.pinned = {name: hash_of(value) for name, value in self.data.items()}
        self.pinned["projected_test"] = hash_of(self.guard_test.replace(mod.OLD, mod.NEW))
        for name, value in self.data.items():
            self.paths[name].write_bytes(value)

    def build(self):
        return mod.build_review(self.paths, self.pinned)

    def test_exact_pinned_sources_prepare_only_two_review_files(self):
        before = {name: path.read_bytes() for name, path in self.paths.items()}
        artifacts, report = self.build()
        self.assertEqual(set(artifacts), {
            "micor.top.guard-v2.REVIEW.conf", "prp-test.guard-v2.REVIEW.conf"
        })
        self.assertEqual(artifacts["micor.top.guard-v2.REVIEW.conf"], self.guard_main)
        self.assertEqual(artifacts["prp-test.guard-v2.REVIEW.conf"],
                         self.guard_test.replace(mod.OLD, mod.NEW))
        self.assertEqual(report["status"], "REVIEW_ONLY_PINNED_PAIR_PREPARED")
        self.assertFalse(report["nginx_syntax_tested"])
        self.assertFalse(report["public_security_acceptance_passed"])
        self.assertFalse(report["host_guard_install_authorized"])
        self.assertFalse(report["b2_cutover_authorized"])
        self.assertFalse(report["active_configuration_changed"])
        self.assertEqual(before, {name: path.read_bytes() for name, path in self.paths.items()})

    def test_write_only_to_brand_new_private_sibling_directory(self):
        artifacts, report = self.build()
        out = self.root / "review-only-v2-guard-fixture"
        mod.write_review(self.root, out, artifacts, report)
        self.assertEqual(set(p.name for p in out.iterdir()),
                         set(artifacts) | {"review-report.json"})
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        self.assertEqual((out / "review-report.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse(json.loads((out / "review-report.json").read_text())
                         ["host_guard_install_authorized"])
        with self.assertRaises(FileExistsError):
            mod.write_review(self.root, out, artifacts, report)

    def test_forbid_output_under_etc_or_wrong_parent(self):
        artifacts, report = self.build()
        with self.assertRaises(ValueError):
            mod.write_review(self.root, self.root / "etc/nginx", artifacts, report)
        with self.assertRaises(ValueError):
            mod.write_review(self.root, self.root / "anything", artifacts, report)
        self.assertFalse((self.root / "anything").exists())

    def test_any_extra_active_edit_cannot_build_candidate(self):
        self.paths["active_test"].write_bytes(self.active_test + b"# extra bypass\n")
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            self.build()
        self.pinned["active_test"] = hash_of(self.paths["active_test"].read_bytes())
        with self.assertRaisesRegex(ValueError, "ACTIVE_V2_NOT_EXACT_PORT_ONLY_LINEAGE"):
            self.build()

    def test_guard_candidate_tamper_denied(self):
        self.paths["guard_test"].write_bytes(self.guard_test + b"location /admin {}\n")
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            self.build()

    def test_wrong_projection_denied(self):
        self.pinned["projected_test"] = hash_of(b"wrong")
        with self.assertRaisesRegex(ValueError, "V2_GUARD_PROJECTION_SHA_MISMATCH"):
            self.build()

    def test_symlink_source_is_denied(self):
        self.paths["guard_main"].unlink()
        self.paths["guard_main"].symlink_to(self.paths["backup_main"])
        with self.assertRaises(OSError):
            self.build()

    def test_no_receipt_files_can_be_generated(self):
        artifacts, report = self.build()
        names = set(artifacts) | {"review-report.json"}
        self.assertNotIn("approved-install.safe.json", names)
        self.assertNotIn("fresh-b2-restore.safe.json", names)
        self.assertFalse(report["manifest_authorized"])


if __name__ == "__main__":
    unittest.main()
