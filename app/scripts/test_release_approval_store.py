import copy
import multiprocessing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_approval_contract import CHAT, OWNER, CONTROLLER, ENVIRONMENT_REVIEWER
from release_approval_store import PersistentOfflineApprovals
from test_release_approval_contract import fixture


def consume_worker(directory, approval_id, binding, snapshot, env, barrier, queue):
    try:
        store = PersistentOfflineApprovals(directory)
        barrier.wait(timeout=10)
        result = store.consume(approval_id, binding, snapshot, env, CONTROLLER, 1003)
        queue.put(result["state"])
    except ValueError as exc:
        queue.put(str(exc))
    except Exception as exc:
        queue.put("UNEXPECTED:" + type(exc).__name__)


class PersistentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-")
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.store = PersistentOfflineApprovals(self.dir)
        self.snapshot = fixture()
        self.record = self.store.request(self.snapshot, CHAT, 1000, 60)
        self.id = self.record["approval_id"]
        self.binding = self.record["binding_digest"]

    def fresh(self):
        return PersistentOfflineApprovals(self.dir)

    def approve(self):
        return self.fresh().approve(self.id, self.binding, self.snapshot, OWNER, 1001)

    def env(self):
        return {"approval_id": self.id, "binding_digest": self.binding,
                "actor": ENVIRONMENT_REVIEWER, "status": "pass",
                "ref": "synthetic:environment", "at": 1002}

    def consume(self, store=None, now=1003):
        return (store or self.fresh()).consume(self.id, self.binding, self.snapshot,
                                                self.env(), CONTROLLER, now)

    def test_reopen_preserves_record_and_audit(self):
        self.approve()
        r = self.consume()
        self.assertEqual(r["state"], "SIMULATED_CONSUMED")
        self.assertEqual(self.fresh().inspect(self.id, self.binding, 1004), r)
        self.assertEqual([e["event"] for e in r["audit"]],
                         ["REQUESTED", "APPROVED", "SIMULATED_CONSUMED"])
        self.assertFalse(r["deployment_authorized"])

    def test_reopen_rejects_replay_and_duplicate(self):
        self.approve()
        self.consume()
        with self.assertRaisesRegex(ValueError, "ALREADY_CONSUMED"):
            self.consume(now=1004)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CANDIDATE"):
            self.fresh().request(self.snapshot, CHAT, 1005)

    def test_two_independent_processes_only_one_consumes(self):
        self.approve()
        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        queue = ctx.Queue()
        children = [ctx.Process(target=consume_worker,
                    args=(str(self.dir),self.id,self.binding,self.snapshot,self.env(),barrier,queue))
                    for _ in range(2)]
        try:
            for p in children:
                p.start()
            results = [queue.get(timeout=20) for _ in children]
            self.assertCountEqual(results, ["SIMULATED_CONSUMED", "NOT_APPROVED_OR_ALREADY_CONSUMED"])
            for p in children:
                p.join(5)
                self.assertEqual(p.exitcode, 0)
        finally:
            for p in children:
                if p.pid is not None:
                    if p.is_alive():
                        p.terminate()
                    p.join(5)
            queue.close()
            queue.join_thread()
        r = self.fresh().inspect(self.id,self.binding,1004)
        self.assertEqual(sum(e["event"]=="SIMULATED_CONSUMED" for e in r["audit"]),1)

    def test_expiry_is_durable_even_when_consume_denied(self):
        self.approve()
        with self.assertRaises(ValueError):
            self.consume(now=1060)
        r = self.fresh().inspect(self.id,self.binding,1060)
        self.assertEqual(r["state"], "EXPIRED")
        self.assertEqual(r["audit"][-1]["event"], "EXPIRED")

    def test_reject_persists_and_remains_terminal(self):
        self.fresh().reject(self.id,self.binding,OWNER,1001)
        with self.assertRaises(ValueError):
            self.fresh().approve(self.id,self.binding,self.snapshot,OWNER,1002)
        self.assertEqual(self.fresh().inspect(self.id,self.binding,1002)["state"],"REJECTED")

    def test_transaction_failure_rolls_back_consumption(self):
        self.approve()
        s = self.fresh()
        with patch.object(s,"_save",side_effect=sqlite3.OperationalError("synthetic failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.consume(s)
        self.assertEqual(self.fresh().inspect(self.id,self.binding,1003)["state"],"APPROVED")
        self.assertEqual(self.consume(now=1004)["state"],"SIMULATED_CONSUMED")

    def test_invalid_request_does_not_advance_persistent_clock(self):
        with self.assertRaises(ValueError):
            self.fresh().approve(self.id,"sha256:"+"f"*64,self.snapshot,OWNER,99999)
        self.approve()
        self.consume()

    def test_stale_snapshot_and_environment_block_after_reopen(self):
        self.approve()
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["evidence"]["ci"]["run_attempt"] = 2
        with self.assertRaises(ValueError):
            self.fresh().consume(self.id,self.binding,changed,self.env(),CONTROLLER,1003)
        env = dict(self.env(),status="fail")
        with self.assertRaises(ValueError):
            self.fresh().consume(self.id,self.binding,self.snapshot,env,CONTROLLER,1003)
        self.assertEqual(self.fresh().inspect(self.id,self.binding,1003)["state"],"APPROVED")

    def test_ledger_capacity_fails_closed(self):
        s = fixture()
        s["bundle"]["candidate"]["artifact_digest"] = "sha256:"+"e"*64
        for gate in ("artifact","staging","migration","backup_restore"):
            s["bundle"]["evidence"][gate]["artifact_digest"] = s["bundle"]["candidate"]["artifact_digest"]
        with patch("release_approval_store.MAX_RECORDS",1):
            with self.assertRaisesRegex(ValueError,"LEDGER_FULL"):
                self.fresh().request(s,CHAT,1001)
        self.assertEqual(self.fresh().inspect(self.id,self.binding,1001)["state"],"REQUESTED")

    def test_corrupt_database_cannot_forge_authorization(self):
        conn = sqlite3.connect(self.store.path)
        try:
            raw = conn.execute("SELECT payload FROM rehearsal_state").fetchone()[0]
            conn.execute("UPDATE rehearsal_state SET payload=?",
                         (raw.replace('"deployment_authorized":false','"deployment_authorized":true'),))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaisesRegex(ValueError,"INVALID_LEDGER_RECORD"):
            self.fresh()

    def test_non_scratch_and_foreign_db_rejected(self):
        with tempfile.TemporaryDirectory() as wrong:
            with self.assertRaises(ValueError):
                PersistentOfflineApprovals(wrong)
        with tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-") as foreign:
            path = Path(foreign)/"prp-p3-rehearsal.sqlite3"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE unrelated (id INTEGER)")
            conn.close()
            with self.assertRaisesRegex(ValueError,"FOREIGN_DATABASE"):
                PersistentOfflineApprovals(foreign)

    def test_symlink_db_rejected(self):
        with tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-") as other:
            (Path(other)/"prp-p3-rehearsal.sqlite3").symlink_to(self.store.path)
            with self.assertRaises(ValueError):
                PersistentOfflineApprovals(other)


if __name__ == "__main__":
    unittest.main()
