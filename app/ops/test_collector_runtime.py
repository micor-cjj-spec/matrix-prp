import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import collector_runtime as collector
from snapshot_contract import unavailable
from test_snapshot_contract import BEFORE, AFTER, MEM, NOW

class CollectorTests(unittest.TestCase):
    def test_fixed_source_allowlist_has_only_proc_metrics(self):
        self.assertEqual(collector.PROC_SOURCES,{"stat":"/proc/stat","meminfo":"/proc/meminfo"})
        self.assertEqual(collector.PROC_LIMITS,{"stat":512,"meminfo":65536})
        self.assertEqual(collector.ENABLE_MARKER,"ALLOW_HOST_METRICS")
        self.assertEqual(collector.MARKER_CONTENT,b"host-metrics=approved\n")
        with patch("collector_runtime.os.open") as opener:
            with self.assertRaises(OSError):
                collector.read_fixed_proc("/etc/passwd")
            opener.assert_not_called()


    def test_proc_stat_reader_returns_only_aggregate_cpu_line(self):
        import stat
        payload=b"cpu 100 0 20 1000 20 0 0 0 5 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"
        with patch("collector_runtime.os.open",return_value=42), \
             patch("collector_runtime.os.fstat",return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_uid=0,st_gid=0)), \
             patch("collector_runtime.os.read",side_effect=[payload,b""]), \
             patch("collector_runtime.os.close"):
            self.assertEqual(collector.read_fixed_proc("stat"),b"cpu 100 0 20 1000 20 0 0 0 5 0\n")


    def test_proc_reader_rejects_non_root_owned_proc_source(self):
        import stat
        with patch("collector_runtime.os.open",return_value=42), patch("collector_runtime.os.fstat",return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_uid=1000,st_gid=0)), patch("collector_runtime.os.close"):
            with self.assertRaises(OSError):
                collector.read_fixed_proc("meminfo")

    def test_collect_once_uses_two_cpu_samples_and_fixed_disk_adapter(self):
        samples=iter([BEFORE,AFTER,MEM])
        proc=Mock(side_effect=lambda name: next(samples))
        disk=SimpleNamespace(f_frsize=1024,f_blocks=100,f_bfree=40,f_bavail=30)
        writer=Mock()
        sleeps=[]
        result=collector.collect_once(proc_reader=proc,disk_reader=lambda:disk,
            sleeper=sleeps.append,wall_clock=lambda:NOW,writer=writer)
        self.assertEqual(sleeps,[1])
        self.assertEqual([c.args[0] for c in proc.call_args_list],["stat","stat","meminfo"])
        self.assertEqual(result["cpu"]["usagePercent"],30.0)
        self.assertEqual(result["memory"]["usagePercent"],50.0)
        self.assertEqual(result["disk"]["usagePercent"],60.0)
        self.assertEqual(result["application"],{"backend":"unknown","readiness":"unknown"})
        writer.write.assert_called_once_with(result)

    def test_probe_failures_become_unknown_without_aborting_collection(self):
        writer=Mock()
        result=collector.collect_once(proc_reader=Mock(side_effect=OSError("secret path")),
            disk_reader=Mock(side_effect=OSError("secret disk")),sleeper=lambda _:None,
            wall_clock=lambda:NOW,writer=writer)
        self.assertIsNone(result["cpu"])
        self.assertIsNone(result["memory"])
        self.assertIsNone(result["disk"])
        self.assertEqual(result["application"],{"backend":"unknown","readiness":"unknown"})
        writer.write.assert_called_once()

    def test_live_collection_marker_off_is_default_fail_closed(self):
        with patch("collector_runtime._open_directory",side_effect=FileNotFoundError):
            self.assertFalse(collector.live_collection_enabled())

    def test_main_does_not_read_host_without_marker(self):
        with patch("collector_runtime.live_collection_enabled",return_value=False),patch("collector_runtime.acquire_single_writer_lock") as lock,patch("collector_runtime.read_fixed_proc") as proc:
            self.assertEqual(collector.main(),78)
            lock.assert_not_called()
            proc.assert_not_called()

    def test_busy_lock_skips_duplicate_collection(self):
        with patch("collector_runtime.live_collection_enabled",return_value=True),patch("collector_runtime.acquire_single_writer_lock",return_value=None),patch("collector_runtime.read_fixed_proc") as proc:
            self.assertEqual(collector.main(),0)
            proc.assert_not_called()

    def test_collector_never_imports_network_or_process_execution(self):
        import ast
        from pathlib import Path
        tree=ast.parse((Path(__file__).parent/"collector_runtime.py").read_text())
        forbidden={"subprocess","socket","urllib","http","requests","shlex"}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:self.assertNotIn(alias.name.split(".")[0],forbidden)
            if isinstance(node,ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],forbidden)
