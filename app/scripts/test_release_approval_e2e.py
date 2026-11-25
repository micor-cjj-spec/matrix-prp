import copy
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from release_approval_contract import (CHAT, OWNER, CONTROLLER,
                                       ENVIRONMENT_REVIEWER, MODE)
from release_approval_store import PersistentOfflineApprovals, FLAGS
from release_approval_card import render_card, submit_decision
from test_release_approval_contract import fixture


class OfflineReleaseE2E(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-")
        self.addCleanup(temp.cleanup)
        self.directory = temp.name
        self.snapshot = fixture()
        self.store = PersistentOfflineApprovals(self.directory)
        self.request = self.store.request(self.snapshot, CHAT, 1000, 60)
        self.id = self.request["approval_id"]
        self.binding = self.request["binding_digest"]

    def reopen(self):
        return PersistentOfflineApprovals(self.directory)

    def card(self, now=1001, snapshot=None):
        return render_card(self.reopen(), self.id, self.binding,
                           self.snapshot if snapshot is None else snapshot, now)

    def envelope(self, decision="approve", **extra):
        return dict({"approval_id": self.id, "binding_digest": self.binding,
                     "decision": decision}, **extra)

    def decide(self, decision="approve", now=1001, snapshot=None, actor=OWNER):
        return submit_decision(self.reopen(), self.envelope(decision),
                               self.snapshot if snapshot is None else snapshot, actor, now)

    def environment(self, **extra):
        return dict({"approval_id": self.id, "binding_digest": self.binding,
                     "actor": ENVIRONMENT_REVIEWER, "status": "pass",
                     "ref": "synthetic:e2e-environment-review", "at": 1002}, **extra)

    def consume(self, now=1003, snapshot=None, environment=None):
        return self.reopen().consume(self.id, self.binding,
                    self.snapshot if snapshot is None else snapshot,
                    self.environment() if environment is None else environment,
                    CONTROLLER, now)

    def test_complete_request_card_approve_environment_consume_restart(self):
        first = self.card()
        self.assertEqual(first["state"], "REQUESTED")
        self.assertEqual(first["mode"], MODE)
        self.assertEqual(first["binding_digest"], self.binding)
        self.assertEqual(len(first["gates"]), 6)
        approved = self.decide()
        self.assertEqual(approved["state"], "APPROVED")
        self.assertIsNone(approved["consumed_at"])
        # A new adapter instance models a process restart between each phase.
        persisted = self.reopen().inspect(self.id,self.binding,1002)
        self.assertEqual(persisted["state"],"APPROVED")
        consumed = self.consume()
        self.assertEqual(consumed["state"],"SIMULATED_CONSUMED")
        final = self.card(now=1004)
        self.assertEqual(final["state"],"SIMULATED_CONSUMED")
        self.assertEqual(final["consumed_at"],1003)
        self.assertEqual([e["event"] for e in final_audit(self.reopen(),self.id,self.binding)],
                         ["REQUESTED","APPROVED","SIMULATED_CONSUMED"])
        self.assertTrue(all(final[k] is False for k in FLAGS))
        self.assertEqual(final["available_decisions"],[])
        self.assertNotIn("dispatch",final)
        self.assertNotIn("executor",final)

    def test_rejection_stops_entire_flow(self):
        card = self.decide("reject")
        self.assertEqual(card["state"],"REJECTED")
        self.assertEqual(card["available_decisions"],[])
        with self.assertRaises(ValueError):
            self.consume()
        self.assertEqual(self.card(now=1002)["state"],"REJECTED")

    def test_expiry_stops_card_decision_and_consumption(self):
        card = self.card(now=1060)
        self.assertEqual(card["state"],"EXPIRED")
        with self.assertRaises(ValueError):
            self.decide(now=1061)
        with self.assertRaises(ValueError):
            self.consume(now=1062)

    def test_candidate_change_between_card_and_owner_decision(self):
        self.card()
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["evidence"]["ci"]["run_attempt"] = 2
        with self.assertRaisesRegex(ValueError,"STALE_OR_CHANGED"):
            self.decide(snapshot=changed)
        self.assertEqual(self.card(now=1002)["state"],"REQUESTED")

    def test_candidate_change_after_approval_stops_consume(self):
        self.decide()
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["candidate"]["commit"] = "b"*40
        with self.assertRaises(ValueError):
            self.consume(snapshot=changed)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_changed_hold_stops_after_approval(self):
        self.decide()
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["hold"]["state"] = "active"
        with self.assertRaises(ValueError):
            self.consume(snapshot=changed)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_failed_required_gate_stops_after_approval(self):
        self.decide()
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["evidence"]["staging"]["status"] = "fail"
        with self.assertRaises(ValueError):
            self.consume(snapshot=changed)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_missing_high_risk_review_fails_before_request(self):
        changed = fixture("HIGH_REVIEW")
        changed["specialist_review"] = None
        with self.assertRaises(ValueError):
            self.reopen().request(changed,CHAT,1000)
        self.assertEqual(self.card()["state"],"REQUESTED")

    def test_high_risk_specialist_receipt_full_flow(self):
        high = fixture("HIGH_REVIEW")
        # Use a fresh isolated ledger so the setUp normal-risk candidate does not
        # intentionally trigger the duplicate-candidate guard.
        with tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-") as directory:
            store = PersistentOfflineApprovals(directory)
            req = store.request(high,CHAT,1000)
            card = render_card(PersistentOfflineApprovals(directory),req["approval_id"],
                               req["binding_digest"],high,1001)
            self.assertEqual(card["risk"],"HIGH_REVIEW")
            self.assertEqual(card["specialist_review"],high["specialist_review"])
            approved = submit_decision(PersistentOfflineApprovals(directory),
                {"approval_id":req["approval_id"],"binding_digest":req["binding_digest"],
                 "decision":"approve"},high,OWNER,1001)
            env = {"approval_id":req["approval_id"],"binding_digest":req["binding_digest"],
                   "actor":ENVIRONMENT_REVIEWER,"status":"pass",
                   "ref":"synthetic:high-risk-env","at":1002}
            done = PersistentOfflineApprovals(directory).consume(
                req["approval_id"],req["binding_digest"],high,env,CONTROLLER,1003)
            self.assertEqual(approved["state"],"APPROVED")
            self.assertEqual(done["state"],"SIMULATED_CONSUMED")
            self.assertFalse(done["production_authorized"])

    def test_environment_reviewer_mismatch_stops_consumption(self):
        self.decide()
        bad = self.environment(actor=OWNER)
        with self.assertRaises(ValueError):
            self.consume(environment=bad)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_stale_environment_digest_stops_consumption(self):
        self.decide()
        bad = self.environment(binding_digest="sha256:"+"f"*64)
        with self.assertRaises(ValueError):
            self.consume(environment=bad)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_double_click_and_competing_owner_decisions(self):
        self.decide("approve")
        for decision in ("approve","reject"):
            with self.subTest(decision=decision),self.assertRaises(ValueError):
                self.decide(decision,now=1002)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_two_concurrent_owner_clicks_have_one_terminal_result(self):
        barrier = threading.Barrier(2)
        def worker(decision):
            store = self.reopen()
            barrier.wait(timeout=5)
            try:
                return submit_decision(store,self.envelope(decision),self.snapshot,OWNER,1001)["state"]
            except ValueError:
                return "DENIED"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker,("approve","reject")))
        self.assertEqual(outcomes.count("DENIED"),1)
        card = self.card(now=1002)
        self.assertIn(card["state"],("APPROVED","REJECTED"))
        self.assertEqual(len(final_audit(self.reopen(),self.id,self.binding)),2)

    def test_storage_failure_does_not_emit_approved_card(self):
        store = self.reopen()
        with patch.object(store,"_save",side_effect=sqlite3.OperationalError("synthetic failure")):
            with self.assertRaises(sqlite3.OperationalError):
                submit_decision(store,self.envelope(),self.snapshot,OWNER,1001)
        self.assertEqual(self.card(now=1002)["state"],"REQUESTED")

    def test_duplicate_request_and_replay_denied_after_full_flow(self):
        self.decide()
        self.consume()
        with self.assertRaisesRegex(ValueError,"ALREADY_CONSUMED"):
            self.consume(now=1004)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_CANDIDATE"):
            self.reopen().request(self.snapshot,CHAT,1005)

    def test_environment_review_must_be_after_approval(self):
        self.decide()
        bad = self.environment(at=1000)
        with self.assertRaises(ValueError):
            self.consume(environment=bad)
        self.assertEqual(self.card(now=1003)["state"],"APPROVED")

    def test_all_lifecycle_outputs_remain_non_authorizing(self):
        pending = self.card()
        approved = self.decide()
        for state, card in (("REQUESTED",pending),("APPROVED",approved)):
            self.assertEqual(card["state"],state)
            self.assertTrue(all(card[k] is False for k in FLAGS))
        with tempfile.TemporaryDirectory(prefix="prp-p3-rehearsal-") as directory:
            snapshot = fixture()
            store = PersistentOfflineApprovals(directory)
            req = store.request(snapshot,CHAT,1000)
            rejected = submit_decision(store,{"approval_id":req["approval_id"],
                "binding_digest":req["binding_digest"],"decision":"reject"},snapshot,OWNER,1001)
            self.assertEqual(rejected["state"],"REJECTED")
            self.assertTrue(all(rejected[k] is False for k in FLAGS))


def final_audit(store, approval_id, binding):
    # Read the authoritative ledger snapshot; this helper has no side effects.
    return store.inspect(approval_id,binding,1004)["audit"]


if __name__ == "__main__":
    unittest.main()
