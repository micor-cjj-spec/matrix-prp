import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from read_only_capacity import (
    parse_memory, parse_status, parse_systemd, safe_int, snapshot, assess,
)


MEMINFO = (
    "MemTotal:        8192000 kB\n"
    "MemAvailable:    1300000 kB\n"
    "SwapTotal:       2048000 kB\n"
    "SwapFree:        1970000 kB\n"
    "MemFree:          100000 kB\n"
)
UNIT = (
    "MainPID=1001\nActiveState=active\nSubState=running\n"
    "MemoryCurrent=1048576000\nMemoryMax=infinity\n"
    "TasksCurrent=140\nEnvironment=DO_NOT_EXPOSE_DB_PASSWORD\n"
)
STATUS = (
    "Name: java\nPid: 1001\nVmRSS: 880000 kB\nVmHWM: 960000 kB\n"
    "VmSize: 2380000 kB\nThreads: 74\n"
    "Environ: SECRET_TOKEN_DO_NOT_EXPOSE\n"
)


class ReadOnlyCapacityTests(unittest.TestCase):
    def test_allowlisted_meminfo_and_low_memory_warning(self):
        mem = parse_memory(MEMINFO)
        self.assertEqual(mem["MemTotal"], 8192000)
        self.assertNotIn("MemFree", mem)
        record = {
            "host": {
                "total_mib": 8000, "available_mib": 1269.5,
                "swap_total_mib": 2000, "swap_free_mib": 1923,
                "disk_free_gib": 40, "load1": 0.15,
            },
            "prp": {
                "active_state": "active", "main_pid_present": True, "rss_mib": 859,
            },
        }
        outcome = assess(record)
        self.assertFalse(outcome["safe_to_deploy"])
        self.assertEqual(outcome["assessment"], "manual_capacity_review_required")
        self.assertTrue(any("MemAvailable" in x for x in outcome["warnings"]))

    def test_unit_values_and_status_are_strictly_allowlisted(self):
        unit = parse_systemd(UNIT)
        self.assertNotIn("Environment", unit)
        self.assertEqual(unit["MainPID"], "1001")
        status = parse_status(STATUS)
        self.assertNotIn("Name", status)
        self.assertNotIn("Pid", status)
        self.assertNotIn("Environ", status)
        self.assertEqual(status["VmRSS"], 880000)
        self.assertEqual(status["Threads"], 74)
        self.assertIsNone(safe_int("infinity"))

    def test_injected_or_malformed_unit_name_is_rejected_before_execution(self):
        invoked = []
        for value in ("--all", "matrix-prp.service;whoami", "../matrix-prp.service",
                      "matrix-prp.service --show-environment", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                snapshot(unit=value, systemctl=lambda args: invoked.append(args) or UNIT)
        self.assertEqual(invoked, [])

    def test_fake_proc_snapshot_produces_no_secrets_or_pid_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "1001").mkdir()
            (root / "1001" / "status").write_text(STATUS)
            (root / "meminfo").write_text(MEMINFO)
            (root / "loadavg").write_text("0.21 0.10 0.08 1/250 1111")
            calls = []
            report = snapshot(proc_root=root, stat_path="/", systemctl=lambda args: calls.append(args) or UNIT)
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["prp"]["active_state"], "active")
            self.assertEqual(report["prp"]["rss_mib"], round(880000 / 1024, 1))
            self.assertTrue(report["prp"]["main_pid_present"])
            rendered = repr(report)
            for secret in ("DO_NOT_EXPOSE_DB_PASSWORD", "SECRET_TOKEN_DO_NOT_EXPOSE",
                           "Name: java", "MainPID", "1001", "matrix_prp"):
                self.assertNotIn(secret, rendered)
            self.assertFalse(assess(report)["safe_to_deploy"])

    def test_absent_jvm_rss_and_service_not_active_blocks_automatic_go(self):
        record = {
            "host": {"available_mib": 4096, "disk_free_gib": 50,
                     "swap_free_mib": 0, "swap_total_mib": 0},
            "prp": {"active_state": "inactive", "main_pid_present": False, "rss_mib": None},
        }
        result = assess(record)
        self.assertFalse(result["safe_to_deploy"])
        self.assertTrue(any("service" in msg for msg in result["warnings"]))
        self.assertTrue(any("RSS" in msg for msg in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
