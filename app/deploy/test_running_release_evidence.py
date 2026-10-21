"""ENG-03F: verify synthetic host/JAR evidence without a production connection."""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import copy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import collect_running_release_evidence as host
import reconcile_running_release as reviewer

COMMIT = "a" * 40
ID = "r123456789-1"
JAR = b"synthetic packaged jar bytes"
CONTROLLER = b"synthetic controller bytes"
DIGEST = hashlib.sha256(JAR).hexdigest()
CONTROLLER_SHA = hashlib.sha256(CONTROLLER).hexdigest()


def metadata():
    return {
        "id": ID, "commit": COMMIT, "schema_version": 23,
        "backend_source": "b" * 40, "web_source": "c" * 64,
        "files": {"backend.jar": DIGEST, "web/index.html": "d" * 64},
    }


class FakeEvidenceFixture:
    def __init__(self, temp):
        self.root = Path(temp)
        self.base = self.root / "releases"
        self.base.mkdir()
        self.release = self.base / ID
        self.release.mkdir()
        self.jar = self.release / "backend.jar"
        self.jar.write_bytes(JAR)
        self.raw = json.dumps(metadata(), sort_keys=True).encode()
        (self.release / "release.json").write_bytes(self.raw)
        (self.base / "current").symlink_to(ID)
        self.controller = self.root / "controller"
        self.controller.write_bytes(CONTROLLER)
        self.proc = self.root / "proc"
        (self.proc / "123").mkdir(parents=True)
        self.cmdline = self.proc / "123" / "cmdline"
        self.cmdline.write_bytes(b"/usr/bin/java\x00-jar\x00" + str(self.jar).encode() + b"\x00")
        self.manifest = json.dumps({"approved_controller": {"sha256": CONTROLLER_SHA}}).encode()
        self.systemctl = SimpleNamespace(
            returncode=0, stdout=b"ActiveState=active\nMainPID=123\n")

    def gather(self):
        # The collector is deliberately root-only and otherwise has fixed
        # host paths; the patch replaces paths with synthetic fixtures.
        with patch.object(host, "BASE", self.base), \
             patch.object(host, "CONTROLLER", self.controller), \
             patch.object(host, "PROC", self.proc), \
             patch.object(host.os, "geteuid", return_value=0), \
             patch.object(host.subprocess, "run", return_value=self.systemctl), \
             patch.object(host, "safe_digest", wraps=host.safe_digest), \
             patch.object(host, "stat", wraps=stat):
            # The fake controller is not root-owned; mock only lstat metadata.
            original_lstat = Path.lstat
            def fake_lstat(p):
                value = original_lstat(p)
                if p == self.controller:
                    return SimpleNamespace(st_uid=0, st_gid=0,
                                           st_mode=stat.S_IFREG | 0o755, st_nlink=1)
                return value
            with patch.object(host.Path, "lstat", fake_lstat):
                return host.collect()


class RunningReleaseEvidenceTests(unittest.TestCase):
    def test_synthetic_read_only_host_report_binds_process_and_current_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            report = fixture.gather()
            self.assertEqual(report["release"]["commit"], COMMIT)
            self.assertEqual(report["release"]["backend_jar_sha256"], DIGEST)
            self.assertTrue(report["process_jar_path_verified"])
            self.assertFalse(report["production_authorized"])
            self.assertFalse(report["independent_attestation_completed"])
            self.assertNotIn("cmdline", json.dumps(report))
            self.assertNotIn(str(fixture.jar), json.dumps(report))
            self.assertNotIn("synthetic packaged jar", json.dumps(report))

    def test_offline_reconciliation_matches_only_submitted_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            report = fixture.gather()
            passed = reviewer.verify(json.dumps(report).encode(), fixture.raw, fixture.manifest)
            self.assertEqual(passed["classification"],
                             "MATCHES_SUPPLIED_METADATA_REVIEW_REQUIRED")
            self.assertFalse(passed["live_host_independently_attested"])
            self.assertFalse(passed["real_production_jar_verification_completed"])
            self.assertFalse(passed["production_authorized"])
            self.assertEqual(passed["backend_jar_sha256"], DIGEST)

    def test_read_only_collector_rejects_service_pointer_and_file_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            fixture.cmdline.write_bytes(
                b"/usr/bin/java\x00-jar\x00/etc/another.jar\x00")
            with self.assertRaises(ValueError):
                fixture.gather()
            fixture.cmdline.write_bytes(
                b"/usr/bin/java\x00-jar\x00" + str(fixture.jar).encode() + b"\x00")
            fixture.jar.write_bytes(b"tampered JAR")
            with self.assertRaises(ValueError):
                fixture.gather()
            fixture.jar.write_bytes(JAR)
            (fixture.base / "current").unlink()
            (fixture.base / "current").symlink_to("../outside")
            with self.assertRaises((ValueError, FileNotFoundError)):
                fixture.gather()
            (fixture.base / "current").unlink()
            (fixture.base / "current").symlink_to(ID)
            fixture.systemctl.stdout = b"ActiveState=inactive\nMainPID=123\n"
            with self.assertRaises(ValueError):
                fixture.gather()

    def test_reconciliation_rejects_stale_and_all_forged_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            before = fixture.gather()
            invalid = [
                lambda d: d.update(production_authorized=True),
                lambda d: d.update(independent_attestation_completed=True),
                lambda d: d.update(service_active=False),
                lambda d: d.update(process_jar_path_verified=False),
                lambda d: d.update(source="NETWORK_UNVERIFIED"),
                lambda d: d.update(schema_version=True),
                lambda d: d.update(observed_utc="2000-01-01T00:00:00Z"),
                lambda d: d["release"].update(id="other-release"),
                lambda d: d["release"].update(commit="b" * 40),
                lambda d: d["release"].update(schema_version=22),
                lambda d: d["release"].update(backend_jar_sha256="0" * 64),
                lambda d: d["release"].update(release_metadata_sha256="0" * 64),
                lambda d: d.update(controller_sha256="0" * 64),
                lambda d: d.update(private_content="password=example"),
                lambda d: d["release"].update(secret="not permitted"),
            ]
            for i, mutate in enumerate(invalid):
                observed = copy.deepcopy(before)
                mutate(observed)
                with self.subTest(i=i), self.assertRaises(ValueError):
                    reviewer.verify(json.dumps(observed).encode(), fixture.raw, fixture.manifest)
            for bytes_ in (
                b'{"x":1,"x":2}', b'{}', b'{', b' ' * 8193,
                json.dumps(before).encode() + b"{}",
            ):
                with self.subTest(raw=bytes_[:10]), self.assertRaises(ValueError):
                    reviewer.verify(bytes_, fixture.raw, fixture.manifest)
            with self.assertRaises(ValueError):
                reviewer.verify(json.dumps(before).encode(), fixture.raw,
                                json.dumps({"approved_controller": {"sha256": "0" * 64}}).encode())
            with self.assertRaises(ValueError):
                reviewer.verify(json.dumps(before).encode(), fixture.raw + b" ", fixture.manifest)

    def test_false_source_commit_or_schema_never_establishes_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            evidence = fixture.gather()
            for altered in [dict(metadata(), commit="b" * 40),
                            dict(metadata(), schema_version=24)]:
                with self.subTest(altered=altered["commit"]), self.assertRaises(ValueError):
                    reviewer.verify(json.dumps(evidence).encode(),
                                    json.dumps(altered).encode(), fixture.manifest)

    def test_safe_failure_cli_never_echoes_untrusted_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            a = folder / "observed.json"
            b = folder / "release.json"
            c = folder / "manifest.json"
            a.write_text('{"secret":"private-password"}')
            b.write_bytes(json.dumps(metadata()).encode())
            c.write_text(json.dumps({"approved_controller": {"sha256": CONTROLLER_SHA}}))
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(reviewer.main([
                    "--observation", str(a), "--release", str(b), "--manifest", str(c)
                ]), 2)
            self.assertNotIn("private-password", output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["production_authorized"], False)


if __name__ == "__main__":
    unittest.main()
