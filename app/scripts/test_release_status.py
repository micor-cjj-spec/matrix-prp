import copy
import unittest

from release_status import evaluate

SHA = "a" * 40
OTHER_SHA = "b" * 40


def payload():
    return {
        "commit": SHA,
        "checks": {
            "ci": "pass",
            "staging": "pass",
            "migration": "pass",
            "backup_restore": "pass",
            "approval": "pass",
            "production_smoke": "pending",
        },
        "publication_hold": True,
        "deployed_commit": None,
    }


class ReleaseStatusTests(unittest.TestCase):
    def test_hold_always_blocks_even_with_everything_reported_pass(self):
        d = payload()
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = SHA
        r = evaluate(d)
        self.assertEqual(r["state"], "HELD")
        self.assertFalse(r["live_verified"])
        self.assertFalse(r["release_eligible"])

    def test_green_ci_does_not_mean_live(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["approval"] = "pending"
        self.assertEqual(evaluate(d)["state"], "BLOCKED")

    def test_eligible_without_production_smoke_not_live(self):
        d = payload()
        d["publication_hold"] = False
        r = evaluate(d)
        self.assertEqual(r["state"], "READY_NOT_LIVE")
        self.assertFalse(r["release_eligible"])
        self.assertTrue(r["preconditions_claimed_pass"])
        self.assertEqual(r["phase"], "PRECONDITIONS_CLAIMED_PASS")
        self.assertFalse(r["live_verified"])

    def test_old_deployed_sha_before_new_deploy_does_not_block_preflight(self):
        d = payload()
        d["publication_hold"] = False
        d["deployed_commit"] = OTHER_SHA
        self.assertEqual(evaluate(d)["state"], "READY_NOT_LIVE")

    def test_live_claim_requires_matching_deployed_commit_and_smoke(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = SHA
        r = evaluate(d)
        self.assertEqual(r["state"], "LIVE_CLAIMED_UNVERIFIED")
        self.assertTrue(r["live_claimed"])
        self.assertFalse(r["live_verified"])
        self.assertFalse(r["release_eligible"])
        self.assertEqual(r["evidence_trust"], "unverified_caller_assertions")
        self.assertFalse(r["deployment_authorized"])

    def test_failed_production_smoke_is_blocker_not_ready(self):
        for deployed in (None, SHA, OTHER_SHA):
            with self.subTest(deployed=deployed):
                d = payload()
                d["publication_hold"] = False
                d["checks"]["production_smoke"] = "fail"
                d["deployed_commit"] = deployed
                r = evaluate(d)
                self.assertEqual(r["state"], "BLOCKED")
                self.assertIn("production_smoke", r["blockers"])
                self.assertFalse(r["release_eligible"])
                self.assertFalse(r["live_verified"])

    def test_skipped_production_smoke_is_blocker_not_ready(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "skipped"
        r = evaluate(d)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("production_smoke", r["blockers"])

    def test_successful_smoke_missing_deployed_commit_is_blocked(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        r = evaluate(d)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("deployed_commit_missing", r["blockers"])

    def test_successful_smoke_mismatched_deployed_commit_is_blocked(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = OTHER_SHA
        r = evaluate(d)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("deployed_commit_mismatch", r["blockers"])
        self.assertFalse(r["live_verified"])

    def test_failed_backup_is_blocker(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["backup_restore"] = "fail"
        self.assertIn("backup_restore", evaluate(d)["blockers"])

    def test_held_takes_precedence_over_failed_smoke(self):
        d = payload()
        d["checks"]["production_smoke"] = "fail"
        r = evaluate(d)
        self.assertEqual(r["state"], "HELD")
        self.assertIn("production_smoke", r["blockers"])

    def test_missing_or_unknown_gate_rejected(self):
        d = payload()
        del d["checks"]["migration"]
        with self.assertRaises(ValueError):
            evaluate(d)
        d = payload()
        d["checks"]["arbitrary"] = "pass"
        with self.assertRaises(ValueError):
            evaluate(d)

    def test_invalid_hold_and_sha_rejected(self):
        d = payload()
        d["publication_hold"] = "false"
        with self.assertRaises(ValueError):
            evaluate(d)
        d = payload()
        d["commit"] = "main"
        with self.assertRaises(ValueError):
            evaluate(d)
        d = payload()
        d["deployed_commit"] = "A" * 40
        with self.assertRaises(ValueError):
            evaluate(d)

    def test_unknown_top_level_field_or_bad_gate_status_rejected(self):
        d = payload()
        d["proof"] = "trust me"
        with self.assertRaises(ValueError):
            evaluate(d)
        d = payload()
        d["checks"]["ci"] = True
        with self.assertRaises(ValueError):
            evaluate(d)

    def test_ci_and_staging_phases_are_explicit(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["ci"] = "fail"
        self.assertEqual(evaluate(d)["phase"], "CI_FAILED")
        d["checks"]["ci"] = "pending"
        self.assertEqual(evaluate(d)["phase"], "CI_UNVERIFIED")
        d["checks"]["ci"] = "pass"
        d["checks"]["staging"] = "pending"
        self.assertEqual(evaluate(d)["phase"], "STAGING_UNVERIFIED")

    def test_never_claim_authorized_deploy(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = SHA
        self.assertFalse(evaluate(d)["deployment_authorized"])


if __name__ == "__main__":
    unittest.main()
