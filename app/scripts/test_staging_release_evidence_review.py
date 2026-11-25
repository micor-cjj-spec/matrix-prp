import unittest
from test_release_evidence import fixture, A, B, D
from staging_release_evidence_review import build_review, REQUIRED_FINDINGS


def projection():
    return {"schemaVersion": 1, "source": "offline_unverified_staging_review",
            "state": "BLOCKED", "candidate": {"commit": A, "artifactDigest": D, "schema": 30},
            "bindingDigest": "sha256:" + "e" * 64, "readSmoke": "API_SMOKE_PASS",
            "apiPassed": 9, "checksExecuted": 11, "identityCorrelation": "CLAIMED_MATCH_ONLY",
            "findings": sorted(REQUIRED_FINDINGS), "deploymentAuthorized": False,
            "productionAuthorized": False, "releaseEligible": False, "liveVerified": False}


class StagingEvidenceReviewTests(unittest.TestCase):
    def test_full_claims_remain_held(self):
        r = build_review(fixture(True), projection())
        self.assertEqual(r["state"], "HELD")
        self.assertIn("hold:ACTIVE", r["blockers"])
        self.assertTrue(r["offline_staging_projection"]["candidate_match_claimed"])
        for k in ("deployment_authorized", "production_authorized", "release_eligible", "live_verified"):
            self.assertIs(r[k], False)

    def test_clear_hold_and_all_claims_still_blocked(self):
        b = fixture(True)
        b["hold"]["state"] = "clear"
        r = build_review(b, projection())
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("staging:OFFLINE_READ_SMOKE_NOT_UAT", r["blockers"])
        self.assertFalse(r["offline_staging_projection"]["ci_artifact_run_binding_verified"])

    def test_candidate_mismatch_kept_separate(self):
        for key, value in (("commit", B), ("artifactDigest", "sha256:" + "f"*64), ("schema", 31)):
            p = projection()
            p["candidate"][key] = value
            r = build_review(fixture(True), p)
            self.assertIn("staging:PROJECTION_CANDIDATE_MISMATCH", r["blockers"])
            self.assertFalse(r["offline_staging_projection"]["candidate_match_claimed"])

    def test_ci_and_artifact_inventory_preserve_failures(self):
        b = fixture(True)
        b["evidence"]["ci"]["all_jobs_success"] = False
        b["evidence"]["artifact"]["schema"] = 31
        r = build_review(b, projection())
        self.assertIn("ci:INCOMPLETE_OR_FAILED_CI", r["blockers"])
        self.assertIn("artifact:ARTIFACT_OR_SCHEMA_MISMATCH", r["blockers"])

    def test_missing_ci_artifact_not_filled_from_smoke(self):
        r = build_review(fixture(), projection())
        self.assertIn("ci:MISSING_EVIDENCE", r["blockers"])
        self.assertIn("artifact:MISSING_EVIDENCE", r["blockers"])

    def test_reject_claimed_authority_extra_keys_and_invalid_counts(self):
        for k, v in (("productionAuthorized", True), ("state", "READY"),
                     ("apiPassed", 8), ("bindingDigest", "fake"), ("extra", True)):
            p = projection()
            p[k] = v
            with self.assertRaises(ValueError):
                build_review(fixture(), p)

    def test_reject_missing_mandatory_findings(self):
        p = projection()
        p["findings"].remove("SOURCE_AUTHENTICITY_NOT_ESTABLISHED")
        with self.assertRaises(ValueError):
            build_review(fixture(), p)

    def test_incomplete_smoke_remains_blocked(self):
        p = projection()
        p.update(readSmoke="BLOCKED_NO_SESSION", apiPassed=0, checksExecuted=0,
                 identityCorrelation="INCOMPLETE")
        p["findings"].append("READ_SMOKE_NOT_PASS")
        r = build_review(fixture(True), p)
        self.assertEqual(r["offline_staging_projection"]["read_smoke_claimed"], "BLOCKED_NO_SESSION")
        self.assertIn("staging:OFFLINE_READ_SMOKE_NOT_UAT", r["blockers"])
