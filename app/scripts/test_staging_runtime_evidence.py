import copy
import unittest
from test_release_evidence import fixture, A, B, D
from test_staging_release_evidence_review import projection
from staging_runtime_evidence import assess_runtime, CORE_UAT
from staging_release_evidence_review import build_review

NOW = 1700000100


def runtime():
    images = {k: "sha256:" + c*64 for k,c in zip(("backend","gateway","mysql"), "abc")}
    identity = {"commit": A, "artifact_digest": D, "schema": 30,
                "observed_at": NOW-40, "flyway_failed": 0, "compose_match": True,
                "services": {k: {"image": v, "config_digest": "sha256:"+"f"*64}
                             for k,v in images.items()}}
    after = copy.deepcopy(identity)
    after["observed_at"] = NOW-5
    return {"environment": "prp-unified-396", "expected_images": images, "before": identity,
            "after": after, "uat": {"kind": "stage_business", "commit": A, "artifact_digest": D,
                "schema": 30, "started_at": NOW-30, "finished_at": NOW-10,
                "smoke_binding_digest": projection()["bindingDigest"],
                "cases": dict.fromkeys(CORE_UAT,"pass")}}


class RuntimeEvidenceTests(unittest.TestCase):
    def check(self, s, p=None):
        return assess_runtime(fixture()["candidate"], p or projection(), s, NOW)

    def test_consistent_assertions_never_verify_runtime(self):
        r = self.check(runtime())
        self.assertTrue(r["runtime_correlation_claimed"])
        self.assertEqual(r["state"], "BLOCKED")
        for k in ("stage_verified","deployment_authorized","production_authorized","live_verified"):
            self.assertIs(r[k], False)

    def test_compose_mismatch_retained(self):
        s = runtime()
        s["before"]["compose_match"] = False
        self.assertIn("COMPOSE_SOURCE_MISMATCH", self.check(s)["findings"])

    def test_wrong_image_or_candidate(self):
        s = runtime()
        s["after"]["services"]["backend"]["image"] = "sha256:"+"e"*64
        s["after"]["commit"] = B
        r = self.check(s)
        self.assertIn("RUNTIME_IMAGE_MISMATCH", r["findings"])
        self.assertIn("RUNTIME_CANDIDATE_MISMATCH", r["findings"])

    def test_config_change_and_flyway_failure(self):
        s = runtime()
        s["after"]["services"]["backend"]["config_digest"] = "sha256:"+"e"*64
        s["after"]["flyway_failed"] = 1
        r = self.check(s)
        self.assertIn("RUNTIME_CHANGED_DURING_UAT", r["findings"])
        self.assertIn("FLYWAY_FAILURE_REPORTED", r["findings"])

    def test_missing_observation_or_uat(self):
        s = runtime()
        s["before"] = s["uat"] = None
        r = self.check(s)
        self.assertIn("RUNTIME_OBSERVATION_MISSING", r["findings"])
        self.assertIn("BUSINESS_UAT_MISSING", r["findings"])

    def test_synthetic_browser_not_live_business(self):
        s = runtime()
        s["uat"]["kind"] = "synthetic_browser"
        self.assertIn("SYNTHETIC_BROWSER_NOT_BUSINESS_UAT", self.check(s)["findings"])

    def test_skipped_business_cases_never_pass(self):
        s = runtime()
        s["uat"]["cases"]["owner_isolation"] = "skipped"
        self.assertIn("BUSINESS_UAT_INCOMPLETE", self.check(s)["findings"])

    def test_wrong_uat_binding(self):
        s = runtime()
        s["uat"]["smoke_binding_digest"] = "sha256:"+"a"*64
        s["uat"]["schema"] = 31
        r = self.check(s)
        self.assertIn("UAT_SMOKE_BINDING_MISMATCH", r["findings"])
        self.assertIn("UAT_CANDIDATE_MISMATCH", r["findings"])

    def test_stale_or_unbracketed(self):
        s = runtime()
        s["before"]["observed_at"] = NOW-901
        s["after"]["observed_at"] = NOW-20
        r = self.check(s)
        self.assertIn("RUNTIME_OBSERVATION_STALE_OR_FUTURE", r["findings"])
        self.assertIn("UAT_NOT_BRACKETED", r["findings"])

    def test_extra_fields_and_production_rejected(self):
        for key,value in (("environment","production"),("authorized",True)):
            s = runtime()
            s[key] = value
            with self.assertRaises(ValueError):
                self.check(s)

    def test_incomplete_smoke_cannot_correlate(self):
        p = projection()
        p["identityCorrelation"] = "INCOMPLETE"
        self.assertIn("UAT_SMOKE_INCOMPLETE", self.check(runtime(),p)["findings"])

    def test_combined_report_preserves_hold_and_blockers(self):
        s = runtime()
        s["before"]["compose_match"] = False
        r = build_review(fixture(True), projection(), runtime_snapshot=s, runtime_now=NOW)
        self.assertEqual(r["state"],"HELD")
        self.assertIn("hold:ACTIVE",r["blockers"])
        self.assertIn("runtime:COMPOSE_SOURCE_MISMATCH",r["blockers"])
        self.assertIs(r["production_authorized"],False)
