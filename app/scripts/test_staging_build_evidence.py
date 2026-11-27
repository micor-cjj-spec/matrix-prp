import unittest
from test_release_evidence import fixture, A, B, D
from staging_build_evidence import assess_build, CORE_JOBS
from staging_release_evidence_review import build_review
from test_staging_release_evidence_review import projection

NOW = 1700000100
TREE = "d" * 40


def snapshot():
    names = sorted(CORE_JOBS | {"mcp-extra"})
    jobs = [{"id": i+1, "name": n, "run_id": 123, "attempt": 1, "head": A,
             "status": "completed", "conclusion": "success"} for i,n in enumerate(names)]
    return names, {"candidate_tree": TREE,
        "ci": {"repository": "micor-cjj-spec/matrix-prp", "run_id": 123,
               "attempt": 1, "latest_run_id": 123, "latest_attempt": 1,
               "head": A, "tested_tree": TREE, "status": "completed",
               "conclusion": "success", "total_count": len(jobs), "jobs": jobs},
        "artifact": {"repository": "micor-cjj-spec/matrix-prp", "artifact_id": 99,
                     "run_id": 456, "attempt": 1, "witness_commit": B,
                     "source_commit": A, "source_tree": TREE, "archive_digest": D,
                     "schema": 30, "witness_status": "completed", "witness_conclusion": "success",
                     "expires_at": NOW+100, "observed_at": NOW-10,
                     "archive_review": "checksums_claimed_pass"}}


class BuildEvidenceTests(unittest.TestCase):
    def check(self, s, names):
        return assess_build(fixture()["candidate"], s, names, NOW)

    def test_distinct_witness_allowed_but_no_authority(self):
        n,s = snapshot()
        r = self.check(s,n)
        self.assertTrue(r["candidate_match_claimed"])
        self.assertEqual(r["findings"], ["INDEPENDENT_PROVENANCE_NOT_ESTABLISHED"])
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIs(r["ci_artifact_run_binding_verified"], False)

    def test_wrong_source_tree_and_archive(self):
        for key, v in (("source_commit", B), ("source_tree", B), ("archive_digest", "sha256:"+"e"*64), ("schema", 31)):
            n,s = snapshot()
            s["artifact"][key] = v
            self.assertIn("ARTIFACT_CANDIDATE_MISMATCH", self.check(s,n)["findings"])

    def test_later_run_or_attempt_supersedes(self):
        for key,v in (("latest_run_id", 124), ("latest_attempt", 2)):
            n,s = snapshot()
            s["ci"][key] = v
            self.assertIn("CI_RUN_SUPERSEDED", self.check(s,n)["findings"])

    def test_missing_duplicate_and_unknown_jobs(self):
        for change in (lambda j:j.pop(), lambda j:j.append(dict(j[0])),
                       lambda j:j[0].update(name="unexpected")):
            n,s = snapshot()
            change(s["ci"]["jobs"])
            self.assertIn("CI_JOB_INVENTORY_MISMATCH", self.check(s,n)["findings"])

    def test_job_attempt_head_and_skipped(self):
        for key,v in (("attempt", 2), ("head", B), ("conclusion", "skipped"), ("run_id", 999)):
            n,s = snapshot()
            s["ci"]["jobs"][0][key] = v
            self.assertIn("CI_JOB_NOT_EXACT_SUCCESS", self.check(s,n)["findings"])

    def test_ci_tree_mismatch_and_not_success(self):
        n,s = snapshot()
        s["ci"].update(tested_tree=B, conclusion="failure")
        r = self.check(s,n)
        self.assertIn("CI_CANDIDATE_OR_TREE_MISMATCH", r["findings"])
        self.assertIn("CI_NOT_SUCCESS", r["findings"])

    def test_expired_and_future_artifact(self):
        for key,v in (("expires_at", NOW), ("observed_at", NOW+1)):
            n,s = snapshot()
            s["artifact"][key] = v
            self.assertIn("ARTIFACT_EXPIRED_OR_FUTURE", self.check(s,n)["findings"])

    def test_conflicting_same_run_identity(self):
        n,s = snapshot()
        s["artifact"]["run_id"] = 123
        self.assertIn("ARTIFACT_RUN_IDENTITY_CONFLICT", self.check(s,n)["findings"])

    def test_checksum_and_witness_failure(self):
        n,s = snapshot()
        s["artifact"].update(archive_review="failed", witness_conclusion="failure")
        r = self.check(s,n)
        self.assertIn("ARTIFACT_CHECKSUM_REVIEW_INCOMPLETE", r["findings"])
        self.assertIn("ARTIFACT_WITNESS_NOT_SUCCESS", r["findings"])

    def test_invalid_expected_inventory_and_unsafe_fields(self):
        n,s = snapshot()
        with self.assertRaises(ValueError):
            self.check(s, ["mcp-extra"]*6)
        s["artifact"]["production_authorized"] = True
        with self.assertRaises(ValueError):
            self.check(s,n)

    def test_combined_review_keeps_hold_and_staging_failure(self):
        n,s = snapshot()
        b = fixture(True)
        b["evidence"]["staging"]["status"] = "fail"
        r = build_review(b, projection(), build_snapshot=s, expected_jobs=n, now=NOW)
        self.assertEqual(r["state"], "HELD")
        self.assertIn("staging:REPORTED_FAIL", r["blockers"])
        self.assertIn("staging:OFFLINE_READ_SMOKE_NOT_UAT", r["blockers"])
        self.assertFalse(r["offline_build_review"]["ci_artifact_run_binding_verified"])
        self.assertFalse(r["production_authorized"])

    def test_combined_review_detects_inventory_ci_mismatch(self):
        n,s = snapshot()
        b = fixture(True)
        b["evidence"]["ci"]["run_attempt"] = 2
        r = build_review(b, projection(), build_snapshot=s, expected_jobs=n, now=NOW)
        self.assertIn("build:INVENTORY_CI_RUN_MISMATCH", r["blockers"])
