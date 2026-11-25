import copy
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from release_approval_contract import (OfflineApprovals, MODE, CHAT, OWNER,
                                       CONTROLLER, ENVIRONMENT_REVIEWER, binding)
from release_evidence import GATES, REPO, ARTIFACT_GATES

A = "a" * 40
B = "b" * 40
D = "sha256:" + "c" * 64


def fixture(risk="FEATURE_REVIEW"):
    candidate = {"repository": REPO, "commit": A, "artifact_digest": D, "schema": 30}
    e = {}
    for gate in ("ci", "risk", "artifact", "staging", "migration", "backup_restore"):
        source, env, _ = GATES[gate]
        e[gate] = {"source": source, "environment": env, "commit": A, "status": "pass",
                   "ref": "synthetic:" + gate}
        if gate in ARTIFACT_GATES:
            e[gate].update(artifact_digest=D, schema=30)
    e["ci"].update(run_id=123, run_attempt=1, tested_commit=A, all_jobs_success=True)
    e["risk"]["risk"] = risk
    e["artifact"]["ref"] = "synthetic:artifact:456"
    specialist = ({"commit": A, "artifact_digest": D, "schema": 30, "status": "pass",
                   "ref": "synthetic:specialist"} if risk == "HIGH_REVIEW" else None)
    return {"mode": MODE, "action": "promote", "main_sha": A, "artifact_id": 456,
            "bundle": {"schema_version": 1, "candidate": candidate,
                       "hold": {"state": "clear", "commit": A, "ref": "synthetic:hold"},
                       "evidence": e}, "specialist_review": specialist}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.ledger = OfflineApprovals()
        self.snapshot = fixture()
        self.r = self.ledger.request(self.snapshot, CHAT, 1000, ttl=60)
        self.id = self.r["approval_id"]
        self.hash = self.r["binding_digest"]

    def approve(self, now=1001, snapshot=None, actor=OWNER):
        return self.ledger.approve(self.id, self.hash,
                                   self.snapshot if snapshot is None else snapshot, actor, now)

    def env(self, **changes):
        return dict({"approval_id": self.id, "binding_digest": self.hash,
                     "actor": ENVIRONMENT_REVIEWER, "status": "pass",
                     "ref": "synthetic:environment", "at": 1002}, **changes)

    def consume(self, now=1003, snapshot=None, env=None, actor=CONTROLLER):
        return self.ledger.consume(self.id, self.hash,
                                   self.snapshot if snapshot is None else snapshot,
                                   self.env() if env is None else env, actor, now)

    def test_success_is_simulation_only(self):
        self.approve()
        r = self.consume()
        self.assertEqual(r["state"], "SIMULATED_CONSUMED")
        self.assertEqual([x["event"] for x in r["audit"]],
                         ["REQUESTED", "APPROVED", "SIMULATED_CONSUMED"])
        self.assertEqual([x["sequence"] for x in r["audit"]], [1, 2, 3])
        for k in ("production_authorized", "deployment_authorized", "release_eligible", "live_verified"):
            self.assertIs(r[k], False)

    def test_owner_only_and_controller_only(self):
        with self.assertRaisesRegex(ValueError, "OWNER_DECISION"):
            self.approve(actor=CHAT)
        self.approve()
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_CONTROLLER"):
            self.consume(actor=OWNER)

    def test_cannot_consume_before_approval(self):
        with self.assertRaises(ValueError):
            self.consume()

    def test_double_click_and_replay(self):
        self.approve()
        self.consume()
        with self.assertRaisesRegex(ValueError, "ALREADY_CONSUMED"):
            self.consume(now=1004)
        with self.assertRaises(ValueError):
            self.approve(now=1005)

    def test_concurrent_consumption_once(self):
        self.approve()
        barrier = threading.Barrier(2)
        def worker():
            barrier.wait(timeout=3)
            try:
                return self.consume()["state"]
            except ValueError:
                return "REJECTED_REPLAY"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ["SIMULATED_CONSUMED", "REJECTED_REPLAY"])

    def test_duplicate_request_denied_even_after_consumption(self):
        self.approve()
        self.consume()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CANDIDATE"):
            self.ledger.request(self.snapshot, CHAT, 1004)

    def test_expiry_at_boundary_is_terminal(self):
        self.approve()
        with self.assertRaises(ValueError):
            self.consume(now=1060)
        r = self.ledger.inspect(self.id, self.hash, 1060)
        self.assertEqual(r["state"], "EXPIRED")
        self.assertEqual(r["audit"][-1]["event"], "EXPIRED")

    def test_rejected_cannot_approve_or_consume(self):
        r = self.ledger.reject(self.id, self.hash, OWNER, 1001)
        self.assertEqual(r["state"], "REJECTED")
        with self.assertRaises(ValueError):
            self.approve(now=1002)
        with self.assertRaises(ValueError):
            self.consume()

    def test_no_clock_rewind(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "REWOUND_CLOCK"):
            self.consume(now=1000)

    def test_expired_requested_not_approvable(self):
        with self.assertRaises(ValueError):
            self.approve(now=1060)
        self.assertEqual(self.ledger.inspect(self.id, self.hash, 1060)["state"], "EXPIRED")

    def test_stale_ci_attempt_or_evidence(self):
        changed = copy.deepcopy(self.snapshot)
        changed["bundle"]["evidence"]["ci"]["run_attempt"] = 2
        with self.assertRaisesRegex(ValueError, "CHANGED_EVIDENCE"):
            self.approve(snapshot=changed)
        self.approve()
        with self.assertRaisesRegex(ValueError, "CHANGED_EVIDENCE"):
            self.consume(snapshot=changed)

    def test_wrong_main_or_hold_blocks_at_consumption(self):
        self.approve()
        for change in ("main", "active", "unknown"):
            s = copy.deepcopy(self.snapshot)
            if change == "main":
                s["main_sha"] = B
            else:
                s["bundle"]["hold"]["state"] = change
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.consume(snapshot=s)

    def test_failed_skipped_missing_and_unclassified_evidence(self):
        for gate, status in (("ci", "fail"), ("staging", "skipped"), ("migration", "pending")):
            s = fixture()
            s["bundle"]["evidence"][gate]["status"] = status
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                binding(s)
        s = fixture("UNCLASSIFIED")
        with self.assertRaises(ValueError):
            binding(s)
        s = fixture()
        del s["bundle"]["evidence"]["backup_restore"]
        with self.assertRaises(ValueError):
            binding(s)

    def test_ci_job_false_and_schema_digest_mismatch(self):
        for gate, field, value in (("ci", "all_jobs_success", False),
                                   ("artifact", "schema", 31),
                                   ("staging", "artifact_digest", "sha256:" + "d"*64)):
            s = fixture()
            s["bundle"]["evidence"][gate][field] = value
            with self.subTest(gate=gate, field=field), self.assertRaises(ValueError):
                binding(s)

    def test_no_preasserted_approval_or_production_receipt(self):
        s = fixture()
        s["bundle"]["evidence"]["approval"] = dict(s["bundle"]["evidence"]["artifact"],
                                                  source="owner_decision", environment="production")
        with self.assertRaises(ValueError):
            binding(s)

    def test_high_risk_needs_bound_specialist_review(self):
        s = fixture("HIGH_REVIEW")
        binding(s)
        s["specialist_review"]["schema"] = 31
        with self.assertRaises(ValueError):
            binding(s)
        s["specialist_review"] = None
        with self.assertRaises(ValueError):
            binding(s)

    def test_environment_reviewer_freshness_and_binding(self):
        self.approve()
        for env in (self.env(actor=OWNER), self.env(status="fail"), self.env(at=999),
                    self.env(at=1004), self.env(approval_id="other"),
                    self.env(binding_digest="sha256:"+"e"*64)):
            with self.subTest(env=env), self.assertRaises(ValueError):
                self.consume(env=env)
        self.assertEqual(self.consume()["state"], "SIMULATED_CONSUMED")

    def test_wrong_digest_and_untrusted_refs(self):
        with self.assertRaises(ValueError):
            self.ledger.approve(self.id, "sha256:"+"e"*64, self.snapshot, OWNER, 1001)
        s = fixture()
        s["bundle"]["evidence"]["staging"]["ref"] = "real:stage"
        with self.assertRaises(ValueError):
            binding(s)

    def test_artifact_id_action_and_real_mode_rejected(self):
        for k,v in (("artifact_id",457), ("action","shell"), ("mode","production")):
            s = fixture()
            s[k] = v
            with self.subTest(key=k), self.assertRaises(ValueError):
                binding(s)

    def test_mutable_return_not_ledger_authority(self):
        self.r["state"] = "APPROVED"
        self.r["audit"].clear()
        with self.assertRaises(ValueError):
            self.consume()
        r = self.ledger.inspect(self.id,self.hash,1003)
        self.assertEqual(r["state"], "REQUESTED")
        self.assertEqual(len(r["audit"]), 1)

    def test_ttl_and_requester_bounds(self):
        for actor,ttl in ((OWNER,60),(CHAT,0),(CHAT,901),(CHAT,True)):
            with self.subTest(actor=actor,ttl=ttl), self.assertRaises(ValueError):
                OfflineApprovals().request(self.snapshot,actor,1000,ttl)


if __name__ == "__main__":
    unittest.main()
