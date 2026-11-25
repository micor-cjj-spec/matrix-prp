import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from snapshot_contract import *

NOW = 1795588800
BEFORE = b"cpu 100 0 20 1000 20 0 0 0 5 0\n"
AFTER = b"cpu 120 0 30 1060 30 0 0 0 15 0\n"
MEM = b"MemTotal: 8192 kB\nMemAvailable: 4096 kB\n"
HEALTH = b'{"code":"SUCCESS","data":{"status":"UP","service":"matrix-prp-backend","secret":"not returned"}}'

def sample(at=NOW):
    return build_snapshot(observed_at=at, cpu_before=BEFORE, cpu_after=AFTER,
        meminfo=MEM, statvfs_fixture=SimpleNamespace(f_frsize=1024, f_blocks=100,
        f_bfree=40, f_bavail=30), http_status=200, http_body=HEALTH)

class ContractTests(unittest.TestCase):
    def test_cpu_guest_not_double_counted(self):
        self.assertEqual(cpu_usage(BEFORE, AFTER), {"usagePercent":30.0})
    def test_cpu_counter_reset_or_no_delta_unknown(self):
        for a,b in ((AFTER, BEFORE),(BEFORE,BEFORE),(b"",AFTER),(None,AFTER)):
            self.assertIsNone(cpu_usage(a,b))
    def test_cpu_invalid_counters(self):
        for raw in (b"cpu0 1 2 3 4 5 6 7 8", b"cpu 1 -2 3 4 5 6 7 8", b"x"*65537):
            self.assertIsNone(cpu_usage(raw,AFTER))
    def test_memory_valid(self):
        self.assertEqual(memory_usage(MEM), {"totalBytes":8388608,"availableBytes":4194304,"usagePercent":50.0})
    def test_memory_no_available_or_duplicate(self):
        for raw in (b"MemTotal: 1 kB", MEM+MEM, b"MemTotal: 1 kB\nMemAvailable: 2 kB"):
            self.assertIsNone(memory_usage(raw))
    def test_disk_reserved_blocks(self):
        self.assertEqual(sample()["disk"], {"totalBytes":102400,"usedBytes":61440,"freeBytes":30720,"usagePercent":60.0})
    def test_disk_invalid_counter(self):
        for stats in (None,SimpleNamespace(f_frsize=1,f_blocks=1,f_bfree=2,f_bavail=2)):
            self.assertIsNone(disk_usage(stats))
    def test_health_projection(self):
        self.assertEqual(application_health(200,HEALTH),{"backend":"reachable","readiness":"unknown"})
        self.assertNotIn(b"secret", encode(sample()))
    def test_health_unknown_on_invalid_or_unauthorized(self):
        for status,body in ((401,HEALTH),(200,b"{}"),(200,b"x"*2049),(200,b'{"code":"SUCCESS","code":"SUCCESS"}'),(None,HEALTH)):
            self.assertEqual(application_health(status,body),UNKNOWN_APP)
    def test_probe_error_not_host_down(self):
        self.assertEqual(application_health(503,b"")["backend"],"probe_error")
    def test_fresh(self):
        self.assertEqual(query_snapshot(encode(sample()),NOW+119)["status"],"fresh")
    def test_stale_omits_values(self):
        value=query_snapshot(encode(sample()),NOW+120)
        self.assertEqual(value["status"],"stale")
        self.assertEqual(value["ageSeconds"],120)
        self.assertIsNone(value["disk"])
        self.assertEqual(value["application"],UNKNOWN_APP)
    def test_future_boundary(self):
        self.assertEqual(query_snapshot(encode(sample(NOW+5)),NOW)["ageSeconds"],0)
        self.assertEqual(query_snapshot(encode(sample(NOW+6)),NOW)["status"],"unavailable")
    def test_invalid_time(self):
        for now in (None,True,-1,1.2):
            self.assertEqual(query_snapshot(encode(sample()),now)["status"],"unavailable")
    def test_unknown_and_duplicate_field(self):
        for raw in (encode(sample())[:-1]+b',"extra":1}', b'{"schemaVersion":1,'+encode(sample())[1:]):
            self.assertEqual(query_snapshot(raw,NOW)["status"],"unavailable")
    def test_invalid_values_and_cross_field_consistency(self):
        for change in ({"cpu":{"usagePercent":True}},{"cpu":{"usagePercent":101}},
            {"memory":{"totalBytes":100,"availableBytes":101,"usagePercent":0}},
            {"disk":{"totalBytes":100,"usedBytes":50,"freeBytes":51,"usagePercent":50}},
            {"application":{"backend":"reachable","readiness":"ready"}}, {"environment":"production"}):
            with self.subTest(change=change),self.assertRaises(InvalidSnapshot):
                encode(dict(sample(),**change))
    def test_partial_metrics_allowed(self):
        self.assertEqual(query_snapshot(encode(dict(sample(),cpu=None)),NOW)["status"],"fresh")
    def test_malformed_oversized_and_nonfinite(self):
        for raw in (b"",b"x"*8193,b'{"cpu":NaN}',b"\xff"):
            self.assertEqual(query_snapshot(raw,NOW)["status"],"unavailable")

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.path=self.dir/"status.json"
        self.store=SnapshotStore(self.dir)
    def test_missing_then_atomic_write_read(self):
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
        self.store.write(sample())
        self.assertEqual(self.store.read(NOW)["status"],"fresh")
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(list(self.dir.iterdir()),[self.path])
    def test_reject_symlink_and_hardlink(self):
        other=self.dir/"other"
        other.write_bytes(encode(sample()))
        other.chmod(0o600)
        self.path.symlink_to(other)
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
        self.path.unlink()
        os.link(other,self.path)
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
    def test_reject_parent_symlink_and_public_directory(self):
        with tempfile.TemporaryDirectory() as p:
            alias=Path(p)/"alias"
            alias.symlink_to(self.dir)
            self.assertEqual(SnapshotStore(alias).read(NOW)["status"],"unavailable")
        self.dir.chmod(0o755)
        try:
            self.assertEqual(self.store.read(NOW)["status"],"unavailable")
        finally:
            self.dir.chmod(0o700)
    def test_fifo_does_not_block(self):
        os.mkfifo(self.path,0o600)
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
    def test_bad_mode_and_truncation(self):
        self.store.write(sample())
        self.path.chmod(0o644)
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
        self.path.chmod(0o600)
        self.path.write_bytes(b"{")
        self.assertEqual(self.store.read(NOW)["status"],"unavailable")
    def test_invalid_write_leaves_previous(self):
        self.store.write(sample())
        with self.assertRaises(InvalidSnapshot):
            self.store.write(dict(sample(),environment="production"))
        self.assertEqual(self.store.read(NOW)["status"],"fresh")
    def test_concurrent_readers_see_complete_snapshots(self):
        self.store.write(sample())
        failures=[]
        def reader():
            for _ in range(80):
                got=self.store.read(NOW+1)
                if got["status"]!="fresh" or got["disk"]["totalBytes"]!=102400:
                    failures.append(got)
        threads=[threading.Thread(target=reader) for _ in range(3)]
        for t in threads:t.start()
        for i in range(20):self.store.write(sample(NOW+i%2))
        for t in threads:t.join()
        self.assertEqual(failures,[])
