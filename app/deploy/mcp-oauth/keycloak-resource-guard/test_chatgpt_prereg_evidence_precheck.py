#!/usr/bin/env python3
"""Offline regression tests for the non-authorizing prereg evidence precheck."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name("chatgpt_prereg_evidence_precheck.py")
spec = importlib.util.spec_from_file_location("prereg_precheck", MODULE)
precheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(precheck)


def baseline():
    return {
        "realm": "prp-mcp", "client_count": 13,
        "chatgpt_client_count": 0, "backup_restore_passed": True,
        "restore_realm_client_count": 13,
        "restore_chatgpt_client_count": 0,
        "independent_b2_approval": False,
    }


class EvidenceTests(unittest.TestCase):
    def test_recorded_baseline_never_authorizes(self):
        result = precheck.evaluate(baseline())
        self.assertEqual(result["evidence_consistency"], "MATCHES_RECORDED_BASELINE")
        self.assertFalse(result["deployment_permitted"])
        self.assertIn("INDEPENDENT_APPROVAL_MISSING", result["findings"])

    def test_even_claimed_approval_cannot_authorize(self):
        evidence = baseline()
        evidence["independent_b2_approval"] = True
        result = precheck.evaluate(evidence)
        self.assertFalse(result["deployment_permitted"])

    def test_existing_exact_client_is_stop(self):
        evidence = baseline()
        evidence["chatgpt_client_count"] = 1
        result = precheck.evaluate(evidence)
        self.assertEqual(result["evidence_consistency"], "REVIEW_REQUIRED")

    def test_changed_client_count_is_stop(self):
        evidence = baseline()
        evidence["client_count"] = 14
        self.assertEqual(precheck.evaluate(evidence)["evidence_consistency"], "REVIEW_REQUIRED")

    def test_restore_failure_is_stop(self):
        evidence = baseline()
        evidence["backup_restore_passed"] = False
        self.assertEqual(precheck.evaluate(evidence)["evidence_consistency"], "REVIEW_REQUIRED")

    def test_wrong_realm_rejected(self):
        evidence = baseline()
        evidence["realm"] = "master"
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)

    def test_extra_fields_rejected(self):
        evidence = baseline()
        evidence["secret"] = "should never be accepted"
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)

    def test_boolean_count_rejected(self):
        evidence = baseline()
        evidence["client_count"] = True
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)


    def test_restore_client_count_drift_is_stop(self):
        evidence = baseline()
        evidence["restore_realm_client_count"] = 12
        self.assertEqual(precheck.evaluate(evidence)["evidence_consistency"], "REVIEW_REQUIRED")

    def test_restore_exact_client_collision_is_stop(self):
        evidence = baseline()
        evidence["restore_chatgpt_client_count"] = 1
        self.assertEqual(precheck.evaluate(evidence)["evidence_consistency"], "REVIEW_REQUIRED")

    def test_negative_count_rejected(self):
        evidence = baseline()
        evidence["chatgpt_client_count"] = -1
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)

    def test_nonboolean_approval_rejected(self):
        evidence = baseline()
        evidence["independent_b2_approval"] = "true"
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)

    def test_missing_field_rejected(self):
        evidence = baseline()
        del evidence["backup_restore_passed"]
        with self.assertRaises(ValueError):
            precheck.evaluate(evidence)

    def test_approval_claim_and_valid_baseline_still_no_go(self):
        evidence = baseline()
        evidence["independent_b2_approval"] = True
        result = precheck.evaluate(evidence)
        self.assertEqual(result["evidence_consistency"], "MATCHES_RECORDED_BASELINE")
        self.assertEqual(result["b2_authorization"], "BLOCKED_UNTIL_INDEPENDENT_REVIEW")
        self.assertFalse(result["deployment_permitted"])


if __name__ == "__main__":
    unittest.main()
