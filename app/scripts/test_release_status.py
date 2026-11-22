import unittest
from release_status import evaluate

SHA = "a" * 40


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
    def test_hold_always_blocks(self):
        d = payload()
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = SHA
        self.assertEqual(evaluate(d)["state"], "HELD")
        self.assertFalse(evaluate(d)["live_verified"])

    def test_green_ci_does_not_mean_live(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["approval"] = "pending"
        self.assertEqual(evaluate(d)["state"], "BLOCKED")

    def test_eligible_without_production_smoke_not_live(self):
        d = payload()
        d["publication_hold"] = False
        result = evaluate(d)
        self.assertEqual(result["state"], "READY_NOT_LIVE")
        self.assertTrue(result["release_eligible"])
        self.assertFalse(result["live_verified"])

    def test_live_requires_matching_deployed_commit_and_smoke(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = "b" * 40
        self.assertFalse(evaluate(d)["live_verified"])
        d["deployed_commit"] = SHA
        self.assertEqual(evaluate(d)["state"], "LIVE_VERIFIED")

    def test_failed_smoke_is_blocked_even_with_matching_deployment(self):
        for deployed in (None, SHA):
            with self.subTest(deployed=deployed):
                d = payload()
                d["publication_hold"] = False
                d["checks"]["production_smoke"] = "fail"
                d["deployed_commit"] = deployed
                result = evaluate(d)
                self.assertEqual(result["state"], "BLOCKED")
                self.assertFalse(result["release_eligible"])
                self.assertFalse(result["live_verified"])
                self.assertIn("production_smoke", result["blockers"])

    def test_successful_smoke_with_different_deployed_sha_is_blocked(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        d["deployed_commit"] = "b" * 40
        result = evaluate(d)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["release_eligible"])
        self.assertFalse(result["live_verified"])
        self.assertIn("deployed_commit_mismatch", result["blockers"])

    def test_successful_smoke_without_deployed_sha_is_blocked(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "pass"
        result = evaluate(d)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("deployed_commit_missing", result["blockers"])

    def test_skipped_smoke_is_not_live(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["production_smoke"] = "skipped"
        result = evaluate(d)
        self.assertEqual(result["state"], "READY_NOT_LIVE")
        self.assertFalse(result["live_verified"])

    def test_old_live_deployment_before_smoke_is_normal_preflight(self):
        d = payload()
        d["publication_hold"] = False
        d["deployed_commit"] = "b" * 40
        result = evaluate(d)
        self.assertEqual(result["state"], "READY_NOT_LIVE")
        self.assertTrue(result["release_eligible"])
        self.assertFalse(result["live_verified"])

    def test_hold_takes_precedence_over_smoke_failure(self):
        d = payload()
        d["checks"]["production_smoke"] = "fail"
        result = evaluate(d)
        self.assertEqual(result["state"], "HELD")
        self.assertIn("publication_hold", result["blockers"])
        self.assertIn("production_smoke", result["blockers"])

    def test_failed_backup_is_blocker(self):
        d = payload()
        d["publication_hold"] = False
        d["checks"]["backup_restore"] = "fail"
        self.assertIn("backup_restore", evaluate(d)["blockers"])

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


if __name__ == "__main__":
    unittest.main()
