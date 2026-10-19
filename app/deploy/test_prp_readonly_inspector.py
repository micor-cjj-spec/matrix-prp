"""Privacy, fixed-command and fail-closed regression tests for PRP inspection."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import prp_readonly_report as host
import validate_inspection as client


def sample():
    from datetime import datetime, timezone
    return {
        "schema_version": 1,
        "observed_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "service": {"active_state": "active", "sub_state": "running",
                    "exit_status": 0, "restart_count": 3},
        "components": {
            k: {"trusted_file": True, "sha256": "a" * 64}
            for k in host.FILES
        },
        "deployment_diagnostic": {
            "state": "no_log", "code": "NO_DIAGNOSTIC",
            "stage": "unknown", "exception": None, "timestamp_utc": None,
        },
        "journal": {
            "state": "available", "scanned_lines": 2, "error_lines": 1,
            "timeout_lines": 1, "database_lines": 0, "oom_lines": 0,
        },
    }


class ReadOnlyInspectionTests(unittest.TestCase):
    def test_schema_accepts_bounded_fixed_metadata(self):
        self.assertEqual(client.validate(sample())["service"]["active_state"], "active")

    def test_rejects_raw_log_and_extra_fields(self):
        obj = sample()
        obj["raw_logs"] = "password=private"
        with self.assertRaises(ValueError):
            client.validate(obj)
        obj.pop("raw_logs")
        obj["service"]["raw_output"] = "SECRET"
        with self.assertRaises(ValueError):
            client.validate(obj)

    def test_duplicate_json_fields_are_not_accepted(self):
        raw = '{"schema_version":1,"schema_version":2}'
        with self.assertRaises(ValueError):
            json.loads(raw, object_pairs_hook=client.unique_pairs)

    def test_rejects_forged_types_and_digest(self):
        obj = sample()
        obj["components"]["controller"]["sha256"] = "../../etc/shadow"
        with self.assertRaises(ValueError):
            client.validate(obj)
        obj = sample()
        obj["journal"]["scanned_lines"] = True
        with self.assertRaises(ValueError):
            client.validate(obj)
        obj = sample()
        obj["journal"]["error_lines"] = 101
        with self.assertRaises(ValueError):
            client.validate(obj)

    def test_journal_is_aggregate_only(self):
        lines = ("2026 ERROR timeout password=s3cr3t user=123\n"
                 "INFO query customer_id=42\n").encode()
        with patch.object(host, "fixed_command", return_value=lines):
            report = host.journal_counts()
        self.assertEqual(report["scanned_lines"], 2)
        self.assertEqual(report["error_lines"], 1)
        self.assertEqual(report["timeout_lines"], 1)
        self.assertNotIn("s3cr3t", json.dumps(report))
        self.assertNotIn("customer_id", json.dumps(report))

    def test_invalid_root_helper_json_never_echoed(self):
        with patch.object(host, "fixed_command",
                          return_value=b'{"danger":"secret","state":"available"}'):
            data = host.deployment_diagnostic()
        self.assertEqual(data["code"], "DIAGNOSTIC_UNAVAILABLE")
        self.assertNotIn("secret", json.dumps(data))

    def test_fixed_file_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "original")
            target.write_bytes(b"test-secret")
            shortcut = Path(directory, "link")
            shortcut.symlink_to(target)
            self.assertEqual(host.approved_file_digest(str(shortcut))["trusted_file"], False)

    def test_file_hash_returns_only_digest_for_trusted_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "source")
            path.write_bytes(b"no-record-data-should-leak")
            trusted = SimpleNamespace(st_mode=stat.S_IFREG | 0o755,
                                      st_uid=0, st_nlink=1, st_size=path.stat().st_size)
            with patch.object(host.os, "fstat", return_value=trusted):
                result = host.approved_file_digest(str(path))
        self.assertTrue(result["trusted_file"])
        self.assertRegex(result["sha256"], r"^[a-f0-9]{64}$")
        self.assertNotIn("no-record-data", json.dumps(result))

    def test_invalid_report_failure_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            input_file = Path(directory, "bad.json")
            safe = Path(directory, "safe.json")
            summary = Path(directory, "summary.md")
            manifest = Path(directory, "manifest.json")
            input_file.write_text('{"secret":"password=abc"}', encoding="utf-8")
            manifest.write_text("{}")
            args = [
                "validate_inspection.py", "--input", str(input_file),
                "--output", str(safe), "--summary", str(summary),
                "--manifest", str(manifest),
            ]
            import sys
            with patch.object(sys, "argv", args):
                self.assertEqual(client.main(), 1)
            emitted = safe.read_text() + summary.read_text()
            self.assertNotIn("password", emitted)
            self.assertEqual(json.loads(safe.read_text())["production_gate_passed"], False)

    def test_gateway_denies_unknown_or_injected_commands(self):
        gateway = Path(__file__).with_name("prp-inspect-gateway.sh")
        for cmd in ("", "shell", "report; id", "report --file /etc/shadow", "status"):
            env = {**os.environ, "SSH_ORIGINAL_COMMAND": cmd}
            result = subprocess.run(["/bin/sh", str(gateway)], env=env,
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
