#!/usr/bin/env python3
"""No host mutation: injected temporary config and fake nginx -T response."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

path = Path(__file__).with_name("diagnose_live_nginx_guard.py")
spec = importlib.util.spec_from_file_location("diagnose_live_nginx_guard", path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReadOnlyNginxGuardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "stage"
        self.hostguard = self.root / "host-guard"
        self.hostguard.mkdir(parents=True)
        self.conf = Path(tmp.name) / "etc" / "nginx" / "conf.d"
        self.conf.mkdir(parents=True)
        self.previous = []
        sources = {"/etc/nginx/nginx.conf": sha(b"baseline-nginx")}
        candidates = {}
        for name, source in guard.CANDIDATES.items():
            blob = ("candidate-" + name).encode()
            (self.hostguard / source).write_bytes(blob)
            candidates[source] = sha(blob)
        (self.hostguard / "candidate-manifest.safe.json").write_text(
            json.dumps({"source_hashes": sources, "candidates": candidates}))
        self.manifest = candidates
        self.sources = sources

    def nginx_runner(self, cmd, *, capture_output, timeout, check):
        self.assertEqual(cmd, ["nginx", "-T"])
        self.assertTrue(capture_output)
        self.assertFalse(check)
        assert timeout <= 15
        expected_hashes = dict(self.sources)
        for name, source in guard.CANDIDATES.items():
            expected_hashes[str(self.conf / name)] = self.manifest[source]
        expected = list(expected_hashes)
        out = "".join("# configuration file " + n + ":\n" for n in expected)
        return subprocess.CompletedProcess(cmd, 0, out.encode(), b"SECRET=do-not-print")

    def inspect(self):
        return guard.classify(self.root, self.conf, self.nginx_runner)

    def assert_no_approval(self, doc):
        self.assertIs(doc["guard_install_authorized"], False)
        self.assertIs(doc["b2_cutover_authorized"], False)
        self.assertIs(doc["production_change_performed"], False)
        self.assertNotIn("SECRET", json.dumps(doc))

    def test_known_rollback_pair(self):
        # Artificial inputs cannot produce the historic hashes, so inject
        # the expected rollback checks for the test's isolated fixture.
        originals = guard.KNOWN_ROLLBACK.copy()
        try:
            for name in guard.CANDIDATES:
                blob = ("rollback-" + name).encode()
                (self.conf / name).write_bytes(blob)
                guard.KNOWN_ROLLBACK[name] = sha(blob)
            doc = self.inspect()
            self.assertEqual(doc["pair_state"], "KNOWN_ROLLBACK_PAIR")
            self.assert_no_approval(doc)
        finally:
            guard.KNOWN_ROLLBACK.clear()
            guard.KNOWN_ROLLBACK.update(originals)

    def test_exact_candidate_pair_still_no_permission(self):
        for name, source in guard.CANDIDATES.items():
            (self.conf / name).write_bytes((self.hostguard / source).read_bytes())
        doc = self.inspect()
        self.assertEqual(doc["pair_state"], "CANDIDATE_PAIR_MATCHES_HASHES")
        self.assertEqual(doc["nginx_config_inventory"], "ORDER_AND_PATHS_MATCH_MANIFEST")
        self.assert_no_approval(doc)

    def test_mixed_and_unknown(self):
        (self.conf / "micor.top.conf").write_bytes(b"unknown bytes")
        (self.conf / "prp-mcp-test.conf").write_bytes(
            (self.hostguard / guard.CANDIDATES["prp-mcp-test.conf"]).read_bytes())
        doc = self.inspect()
        self.assertEqual(doc["pair_state"], "UNRECOGNIZED_OR_INCOMPLETE")
        self.assertEqual(doc["files"]["micor.top.conf"]["active_state"], "UNRECOGNIZED_DRIFT")
        self.assert_no_approval(doc)

    def test_symlink_refused(self):
        for name, source in guard.CANDIDATES.items():
            (self.conf / name).symlink_to(self.hostguard / source)
        doc = self.inspect()
        self.assertEqual(doc["pair_state"], "UNRECOGNIZED_OR_INCOMPLETE")
        self.assert_no_approval(doc)

    def test_nginx_inventory_drift(self):
        for name, source in guard.CANDIDATES.items():
            (self.conf / name).write_bytes((self.hostguard / source).read_bytes())
        def extra(*args, **kwargs):
            return subprocess.CompletedProcess(["nginx", "-T"], 0,
                                               b"# configuration file /unknown.conf:\n", b"")
        doc = guard.classify(self.root, self.conf, extra)
        self.assertEqual(doc["nginx_config_inventory"], "INVENTORY_OR_ORDER_DRIFT")
        self.assert_no_approval(doc)

    def test_existing_vhost_keys_keep_manifest_order(self):
        # The original gate uses dict.update semantics. Do not add duplicate
        # vhost paths or silently accept a different nginx -T order.
        live_path = str(self.conf / "micor.top.conf")
        self.sources = {live_path: sha(b"historical-source"), **self.sources}
        manifest_path = self.hostguard / "candidate-manifest.safe.json"
        parsed = json.loads(manifest_path.read_text())
        parsed["source_hashes"] = self.sources
        manifest_path.write_text(json.dumps(parsed))
        for name, source in guard.CANDIDATES.items():
            (self.conf / name).write_bytes((self.hostguard / source).read_bytes())
        doc = self.inspect()
        self.assertEqual(doc["nginx_config_inventory"], "ORDER_AND_PATHS_MATCH_MANIFEST")
        self.assert_no_approval(doc)

    def test_missing_manifest_fails_closed(self):
        (self.hostguard / "candidate-manifest.safe.json").unlink()
        doc = self.inspect()
        self.assertEqual(doc["candidate_manifest"], "MISSING_OR_INVALID")
        self.assert_no_approval(doc)


if __name__ == "__main__":
    unittest.main()
