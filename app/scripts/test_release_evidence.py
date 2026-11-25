import unittest
from release_evidence import GATES, ARTIFACT_GATES, inventory, markdown

A = "a" * 40
B = "b" * 40
D = "sha256:" + "c" * 64


def fixture(complete=False):
    d = {"schema_version": 1,
         "candidate": {"repository": "micor-cjj-spec/matrix-prp", "commit": A,
                       "artifact_digest": D, "schema": 30},
         "hold": {"state": "active", "commit": A, "ref": "git:hold"},
         "evidence": {}}
    if complete:
        for g, (source, env, _) in GATES.items():
            e = {"source": source, "environment": env, "commit": A,
                 "status": "pass", "ref": "fixture:" + g}
            if g in ARTIFACT_GATES:
                e.update(artifact_digest=D, schema=30)
            if g == "risk":
                e["risk"] = "HIGH_REVIEW"
            if g == "ci":
                e.update(run_id=123, run_attempt=1, tested_commit=A, all_jobs_success=True)
            d["evidence"][g] = e
    return d


class ReleaseEvidenceTests(unittest.TestCase):
    def test_empty_evidence_reports_missing_and_held(self):
        r = inventory(fixture())
        self.assertEqual(r["state"], "HELD")
        self.assertEqual(len(r["gates"]), 9)
        self.assertIn("ci:MISSING_EVIDENCE", r["blockers"])

    def test_all_claims_cannot_override_hold(self):
        self.assertEqual(inventory(fixture(True))["state"], "HELD")

    def test_full_claims_never_authorize_or_prove_live(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        r = inventory(d)
        self.assertEqual(r["state"], "LIVE_CLAIMED_UNVERIFIED")
        for field in ("deployment_authorized", "release_eligible", "live_verified"):
            self.assertFalse(r[field])

    def test_stale_hold_is_unknown_not_clear(self):
        d = fixture(True)
        d["hold"].update(state="clear", commit=B)
        r = inventory(d)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("hold:UNKNOWN", r["blockers"])

    def test_explicit_unknown_hold_blocks(self):
        d = fixture(True)
        d["hold"]["state"] = "unknown"
        self.assertIn("hold:UNKNOWN", inventory(d)["blockers"])

    def test_stale_staging_receipt_blocks(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        d["evidence"]["staging"]["commit"] = B
        self.assertIn("staging:STALE_CANDIDATE", inventory(d)["blockers"])

    def test_artifact_schema_mismatch_blocks(self):
        for field, value in [("artifact_digest", "sha256:" + "d" * 64), ("schema", 31)]:
            d = fixture(True)
            d["evidence"]["backup_restore"][field] = value
            self.assertIn("backup_restore:ARTIFACT_OR_SCHEMA_MISMATCH", inventory(d)["blockers"])

    def test_pr_head_not_tested_merge_sha(self):
        d = fixture(True)
        d["evidence"]["ci"]["tested_commit"] = B
        self.assertIn("ci:TESTED_SHA_MISMATCH", inventory(d)["blockers"])

    def test_green_subset_does_not_count(self):
        d = fixture(True)
        d["evidence"]["ci"]["all_jobs_success"] = False
        self.assertIn("ci:INCOMPLETE_OR_FAILED_CI", inventory(d)["blockers"])

    def test_unclassified_risk_blocks(self):
        d = fixture(True)
        d["evidence"]["risk"]["risk"] = "UNCLASSIFIED"
        self.assertIn("risk:RISK_UNCLASSIFIED", inventory(d)["blockers"])

    def test_docs_only_risk_does_not_waive_release_gates(self):
        d = fixture(True)
        d["evidence"]["risk"]["risk"] = "NO_RUNTIME_CHANGE"
        del d["evidence"]["staging"]
        self.assertIn("staging:MISSING_EVIDENCE", inventory(d)["blockers"])

    def test_candidate_without_artifact_cannot_bind_staging(self):
        d = fixture(True)
        d["candidate"]["artifact_digest"] = None
        self.assertIn("staging:ARTIFACT_OR_SCHEMA_MISMATCH", inventory(d)["blockers"])

    def test_wrong_environment_rejected(self):
        d = fixture(True)
        d["evidence"]["staging"]["environment"] = "production"
        with self.assertRaises(ValueError):
            inventory(d)

    def test_forged_authorization_key_rejected(self):
        d = fixture(True)
        d["evidence"]["approval"]["authorized"] = True
        with self.assertRaises(ValueError):
            inventory(d)

    def test_bad_reference_rejected(self):
        d = fixture(True)
        d["evidence"]["ci"]["ref"] = "foo|<script>"
        with self.assertRaises(ValueError):
            inventory(d)

    def test_preconditions_are_not_published(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        del d["evidence"]["publish"]
        del d["evidence"]["production_smoke"]
        r = inventory(d)
        self.assertEqual(r["state"], "PRECONDITIONS_CLAIMED_PASS")
        self.assertFalse(r["live_verified"])

    def test_publish_with_pending_smoke_not_live(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        del d["evidence"]["production_smoke"]
        self.assertEqual(inventory(d)["state"], "PUBLISH_CLAIMED_SMOKE_PENDING")

    def test_smoke_without_publish_is_blocked(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        del d["evidence"]["publish"]
        self.assertIn("production_smoke:PUBLISH_EVIDENCE_MISSING", inventory(d)["blockers"])

    def test_failed_smoke_blocks(self):
        d = fixture(True)
        d["hold"]["state"] = "clear"
        d["evidence"]["production_smoke"]["status"] = "fail"
        self.assertEqual(inventory(d)["state"], "BLOCKED")

    def test_output_preserves_ci_attempt_and_artifact_binding(self):
        r = inventory(fixture(True))
        rows = {row["gate"]: row for row in r["gates"]}
        self.assertEqual(rows["ci"]["asserted_binding"]["run_id"], 123)
        self.assertEqual(rows["ci"]["asserted_binding"]["run_attempt"], 1)
        self.assertEqual(rows["staging"]["asserted_binding"]["artifact_digest"], D)
        self.assertEqual(rows["staging"]["asserted_binding"]["schema"], 30)
        self.assertEqual(r["hold_binding"]["ref"], "git:hold")
        self.assertNotIn("offline_status", r)

    def test_external_url_reference_rejected(self):
        d = fixture(True)
        d["evidence"]["ci"]["ref"] = "https://example.invalid/receipt"
        with self.assertRaises(ValueError):
            inventory(d)

    def test_report_is_explicitly_unverified(self):
        self.assertIn("No release approval or LIVE verification", markdown(inventory(fixture())))


if __name__ == "__main__":
    unittest.main()
