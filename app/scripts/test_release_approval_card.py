import copy
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from release_approval_contract import CHAT, OWNER, CONTROLLER, ENVIRONMENT_REVIEWER, MODE
from release_approval_store import PersistentOfflineApprovals, FLAGS
from release_approval_card import render_card, submit_decision, CARD_KIND
from test_release_approval_contract import fixture


class CardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-")
        self.addCleanup(temp.cleanup)
        self.directory = temp.name
        self.store = PersistentOfflineApprovals(self.directory)
        self.snapshot = fixture()
        record = self.store.request(self.snapshot, CHAT, 1000, 60)
        self.id = record["approval_id"]
        self.binding = record["binding_digest"]

    def card(self, now=1001, snapshot=None):
        return render_card(self.store, self.id, self.binding,
                           self.snapshot if snapshot is None else snapshot, now)

    def envelope(self, decision="approve", **changes):
        return dict({"approval_id": self.id, "binding_digest": self.binding,
                     "decision": decision}, **changes)

    def decide(self, decision="approve", now=1002, snapshot=None, actor=OWNER, envelope=None):
        return submit_decision(self.store, self.envelope(decision) if envelope is None else envelope,
                               self.snapshot if snapshot is None else snapshot, actor, now)

    def test_card_exact_binding_and_nonauthorizing_fields(self):
        card = self.card()
        self.assertEqual(card["kind"], CARD_KIND)
        self.assertEqual(card["mode"], MODE)
        self.assertEqual(card["candidate"], self.snapshot["bundle"]["candidate"])
        self.assertEqual(card["artifact_id"], self.snapshot["artifact_id"])
        self.assertEqual(card["binding_digest"], self.binding)
        self.assertEqual(card["ci_run_attempt"], 1)
        self.assertEqual(card["expires_at"], 1060)
        self.assertEqual(card["available_decisions"], ["approve", "reject"])
        self.assertEqual(len(card["gates"]), 6)
        self.assertTrue(all(card[k] is False for k in FLAGS))
        self.assertNotIn("consume", card["available_decisions"])

    def test_approve_never_consumes(self):
        with patch.object(self.store, "consume", side_effect=AssertionError("not a card action")):
            card = self.decide()
        self.assertEqual(card["state"], "APPROVED")
        self.assertIsNone(card["consumed_at"])
        self.assertEqual(card["available_decisions"], [])
        record = self.store.inspect(self.id,self.binding,1003)
        self.assertEqual([e["event"] for e in record["audit"]], ["REQUESTED","APPROVED"])

    def test_reject_terminal(self):
        card = self.decide("reject")
        self.assertEqual(card["state"],"REJECTED")
        self.assertEqual(card["available_decisions"],[])
        with self.assertRaises(ValueError):
            self.decide(now=1003)

    def test_double_approval_and_stale_reject_denied(self):
        self.decide()
        for decision in ("approve","reject"):
            with self.subTest(decision=decision), self.assertRaises(ValueError):
                self.decide(decision,now=1003)
        self.assertEqual(self.card(now=1004)["state"],"APPROVED")

    def test_concurrent_opposite_clicks_exactly_one_decision(self):
        barrier = threading.Barrier(2)
        def worker(decision):
            store = PersistentOfflineApprovals(self.directory)
            barrier.wait(timeout=5)
            try:
                return submit_decision(store,self.envelope(decision),self.snapshot,OWNER,1002)["state"]
            except ValueError:
                return "DENIED"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker,("approve","reject")))
        self.assertEqual(results.count("DENIED"),1)
        record = self.store.inspect(self.id,self.binding,1003)
        self.assertIn(record["state"], ("APPROVED","REJECTED"))
        self.assertEqual(len(record["audit"]),2)

    def test_expired_card_and_expired_click(self):
        with self.assertRaises(ValueError):
            self.decide(now=1060)
        card = self.card(now=1061)
        self.assertEqual(card["state"],"EXPIRED")
        self.assertEqual(card["available_decisions"],[])

    def test_stale_snapshot_never_displays_or_decides(self):
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["evidence"]["ci"]["run_attempt"] = 2
        with self.assertRaisesRegex(ValueError,"STALE_OR_CHANGED"):
            self.card(snapshot=changed)
        for decision in ("approve","reject"):
            with self.subTest(decision=decision),self.assertRaises(ValueError):
                self.decide(decision,snapshot=changed)
        self.assertEqual(self.card(now=1003)["state"],"REQUESTED")

    def test_hold_and_gate_failure_blocks(self):
        for change in ("hold","staging"):
            snapshot = copy.deepcopy(self.snapshot)
            if change == "hold":
                snapshot["bundle"]["hold"]["state"] = "active"
            else:
                snapshot["bundle"]["evidence"]["staging"]["status"] = "fail"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.decide(snapshot=snapshot)

    def test_envelope_cannot_supply_actor_clock_or_execute_action(self):
        for extra in ({"actor":OWNER},{"now":1002},{"decision":"consume"},
                      {"decision":"dispatch"},{"binding_digest":"sha256:"+"f"*64},
                      {"approval_id":"unknown"},{"decision":[]}, {"decision":None}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.decide(envelope=dict(self.envelope(),**extra))
        for actor in (CHAT,CONTROLLER):
            with self.subTest(actor=actor),self.assertRaises(ValueError):
                self.decide(actor=actor)

    def test_failed_storage_never_returns_approval(self):
        with patch.object(self.store,"_save",side_effect=sqlite3.OperationalError("synthetic failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.decide()
        self.assertEqual(self.card(now=1003)["state"],"REQUESTED")

    def test_separate_controller_consumption_card_is_terminal(self):
        self.decide()
        env = {"approval_id":self.id,"binding_digest":self.binding,"actor":ENVIRONMENT_REVIEWER,
               "status":"pass","ref":"synthetic:environment","at":1003}
        self.store.consume(self.id,self.binding,self.snapshot,env,CONTROLLER,1004)
        card = self.card(now=1005)
        self.assertEqual(card["state"],"SIMULATED_CONSUMED")
        self.assertEqual(card["available_decisions"],[])
        self.assertTrue(all(card[k] is False for k in FLAGS))

    def test_high_risk_card_shows_bound_specialist_review(self):
        snapshot = fixture("HIGH_REVIEW")
        with tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-") as directory:
            store = PersistentOfflineApprovals(directory)
            record = store.request(snapshot,CHAT,1000)
            card = render_card(store,record["approval_id"],record["binding_digest"],snapshot,1001)
            self.assertEqual(card["risk"],"HIGH_REVIEW")
            self.assertEqual(card["specialist_review"],snapshot["specialist_review"])

    def test_card_is_not_authority(self):
        card = self.card()
        card["candidate"]["schema"] = 999
        card["gates"].clear()
        with self.assertRaises(ValueError):
            self.decide(envelope=card)
        self.assertEqual(self.card(now=1003)["candidate"]["schema"],30)


if __name__ == "__main__":
    unittest.main()
