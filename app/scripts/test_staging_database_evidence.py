import unittest
from test_release_evidence import fixture, A, B, D
from test_staging_release_evidence_review import projection
from test_staging_build_evidence import snapshot as build_snapshot
from test_staging_runtime_evidence import runtime, NOW
from staging_database_evidence import assess_database, RISK_FLAGS
from staging_release_evidence_review import build_review, unified_markdown

H = "sha256:" + "1" * 64
I = "sha256:" + "2" * 64
X = "sha256:" + "3" * 64
Y = "sha256:" + "4" * 64
P = "sha256:" + "5" * 64
S = "sha256:" + "6" * 64
T = "sha256:" + "7" * 64


def database():
    binding = dict(commit=A, artifact_digest=D, schema=30)
    migrations = [dict(version=30, sql_digest=S)]
    return {"environment": "prp-unified-396", "baseline_schema": 29,
            "baseline_history": H, "baseline_data_digest": I, "source_instance": X,
            "policy_digest": P, "expected_migrations": migrations,
            "migration": dict(binding, policy_digest=P, source_instance=X, before_schema=29,
                              before_history=H, after_history=Y, applied=[dict(migrations[0])],
                              failed_count=0, started_at=NOW-80, finished_at=NOW-60, validation="pass"),
            "backup": dict(binding, source_instance=X, baseline_schema=29, history_digest=H,
                           data_digest=I, backup_digest=T, created_at=NOW-100, checksum_review="pass"),
            "restore": dict(binding, backup_digest=T, target_instance=Y, restored_schema=29,
                            history_digest=H, data_digest=I, started_at=NOW-99,
                            finished_at=NOW-90, validation="pass", isolated=True,
                            rehearsal=dict(target_schema=30, policy_digest=P, applied=[dict(migrations[0])],
                                           failed_count=0, validation="pass", historical_rows="pass",
                                           historical_ddl="pass", new_tables="pass")),
            "risk": dict(binding, classification="HIGH_REVIEW", flags=dict.fromkeys(RISK_FLAGS, False),
                         reviewed_at=NOW-5, specialist_reviews={"database": "pass", "security": "pass"})}


class DatabaseEvidenceTests(unittest.TestCase):
    def check(self, s):
        return assess_database(fixture()["candidate"], s, NOW)

    def test_all_consistent_never_verified(self):
        r = self.check(database())
        self.assertTrue(all(r["correlation_claimed"].values()))
        for k in ("migration_verified", "restore_verified", "risk_verified",
                  "deployment_authorized", "production_authorized", "live_verified"):
            self.assertIs(r[k], False)

    def test_no_migration_history_unchanged(self):
        s = database()
        s.update(baseline_schema=30, expected_migrations=[])
        s["migration"].update(before_schema=30, after_history=H, applied=[])
        s["backup"]["baseline_schema"] = s["restore"]["restored_schema"] = 30
        s["restore"]["rehearsal"]["applied"] = []
        self.assertTrue(all(self.check(s)["correlation_claimed"].values()))

    def test_missing_receipts(self):
        s = database()
        for k in ("migration", "backup", "restore", "risk"):
            s[k] = None
        self.assertFalse(any(self.check(s)["correlation_claimed"].values()))

    def test_gap_and_downgrade(self):
        for baseline in (28, 31):
            s = database()
            s["baseline_schema"] = baseline
            self.assertIn("MIGRATION_PLAN_VERSION_GAP_OR_DOWNGRADE", self.check(s)["findings"]["migration"])

    def test_wrong_checksum_or_policy(self):
        s = database()
        s["migration"]["applied"][0]["sql_digest"] = P
        s["migration"]["policy_digest"] = S
        findings = self.check(s)["findings"]["migration"]
        self.assertIn("MIGRATION_VERSION_OR_CHECKSUM_MISMATCH", findings)
        self.assertIn("MIGRATION_BASELINE_OR_POLICY_MISMATCH", findings)

    def test_failed_and_history_transition(self):
        s = database()
        s["migration"].update(failed_count=1, after_history=H)
        findings = self.check(s)["findings"]["migration"]
        self.assertIn("FLYWAY_VALIDATION_NOT_PASS", findings)
        self.assertIn("MIGRATION_HISTORY_TRANSITION_MISMATCH", findings)

    def test_candidate_mismatch(self):
        s = database()
        for k in ("migration", "backup", "restore", "risk"):
            s[k]["commit"] = B
        self.assertFalse(any(self.check(s)["correlation_claimed"].values()))

    def test_backup_after_migration_and_failed_checksum(self):
        s = database()
        s["backup"].update(created_at=NOW-80, checksum_review="fail")
        findings = self.check(s)["findings"]["backup_restore"]
        self.assertIn("BACKUP_NOT_FRESH_PRE_MIGRATION", findings)
        self.assertIn("BACKUP_CHECKSUM_NOT_PASS", findings)

    def test_restore_wrong_backup_and_same_instance(self):
        s = database()
        s["restore"].update(backup_digest=P, target_instance=X)
        findings = self.check(s)["findings"]["backup_restore"]
        self.assertIn("RESTORE_BACKUP_OR_CANDIDATE_MISMATCH", findings)
        self.assertIn("RESTORE_TARGET_NOT_ISOLATED", findings)

    def test_rehearsal_must_finish_strictly_before_migration(self):
        for start, finish in ((NOW-10, NOW-1), (NOW-95, NOW-80), (NOW-90, NOW-70)):
            with self.subTest(start=start, finish=finish):
                s = database()
                s["restore"].update(started_at=start, finished_at=finish)
                r = self.check(s)
                self.assertFalse(r["correlation_claimed"]["backup_restore"])
                self.assertIn("RESTORE_REHEARSAL_NOT_BEFORE_MIGRATION", r["findings"]["backup_restore"])

    def test_missing_migration_cannot_establish_rehearsal_order(self):
        s = database()
        s["migration"] = None
        self.assertIn("RESTORE_REHEARSAL_NOT_BEFORE_MIGRATION",
                      self.check(s)["findings"]["backup_restore"])

    def test_missing_target_rehearsal(self):
        s = database()
        s["restore"]["rehearsal"] = None
        self.assertIn("TARGET_MIGRATION_REHEARSAL_MISSING", self.check(s)["findings"]["backup_restore"])

    def test_rehearsal_wrong_candidate_policy_or_sql(self):
        for key, value in (("target_schema", 31), ("policy_digest", S),
                           ("applied", [{"version":30, "sql_digest":P}])):
            with self.subTest(key=key):
                s = database()
                s["restore"]["rehearsal"][key] = value
                self.assertIn("REHEARSAL_TARGET_OR_POLICY_MISMATCH",
                              self.check(s)["findings"]["backup_restore"])

    def test_rehearsal_preservation_checks_fail_closed(self):
        for key, value in (("failed_count", 1), ("validation", "fail"),
                           ("historical_rows", "fail"), ("historical_ddl", "skipped"),
                           ("new_tables", "pending")):
            with self.subTest(key=key):
                s = database()
                s["restore"]["rehearsal"][key] = value
                self.assertIn("REHEARSAL_PRESERVATION_NOT_PASS",
                              self.check(s)["findings"]["backup_restore"])

    def test_reject_unsafe_rehearsal_shape(self):
        s = database()
        s["restore"]["rehearsal"]["authorized"] = True
        with self.assertRaises(ValueError):
            self.check(s)

    def test_restore_data_drift_or_skipped(self):
        s = database()
        s["restore"].update(data_digest=S, validation="skipped")
        findings = self.check(s)["findings"]["backup_restore"]
        self.assertIn("RESTORE_BASELINE_INTEGRITY_MISMATCH", findings)
        self.assertIn("RESTORE_VALIDATION_NOT_PASS", findings)

    def test_future_stale_and_inverted_windows(self):
        s = database()
        s["migration"]["started_at"] = NOW+1
        s["backup"]["created_at"] = NOW-86401
        s["restore"]["finished_at"] = NOW+1
        r = self.check(s)["findings"]
        self.assertIn("MIGRATION_TIME_INVALID", r["migration"])
        self.assertIn("BACKUP_NOT_FRESH_PRE_MIGRATION", r["backup_restore"])
        self.assertIn("RESTORE_TIME_INVALID", r["backup_restore"])

    def test_high_risk_cannot_be_downgraded_or_skip_review(self):
        s = database()
        s["risk"].update(classification="FEATURE_REVIEW",
                         specialist_reviews={"database": "pass", "security": "skipped"})
        findings = self.check(s)["findings"]["risk"]
        self.assertIn("RISK_UNCLASSIFIED_OR_UNDERRATED", findings)
        self.assertIn("HIGH_RISK_SPECIALIST_REVIEW_INCOMPLETE", findings)

    def test_privilege_change_high_risk_without_migration(self):
        s = database()
        s.update(baseline_schema=30, expected_migrations=[])
        s["migration"].update(before_schema=30, after_history=H, applied=[])
        s["backup"]["baseline_schema"] = s["restore"]["restored_schema"] = 30
        s["restore"]["rehearsal"]["applied"] = []
        s["risk"]["flags"]["oauth_scope_change"] = True
        s["risk"]["classification"] = "NO_RUNTIME_CHANGE"
        self.assertIn("RISK_UNCLASSIFIED_OR_UNDERRATED", self.check(s)["findings"]["risk"])

    def test_reject_production_and_unknown_keys(self):
        for k, v in (("environment", "production"), ("authorization", True)):
            s = database()
            s[k] = v
            with self.assertRaises(ValueError):
                self.check(s)

    def test_reject_wrong_type_and_receipt_injection(self):
        s = database()
        s["risk"]["flags"]["permission_change"] = 1
        with self.assertRaises(ValueError):
            self.check(s)
        s = database()
        s["restore"]["raw_sql"] = "not allowed"
        with self.assertRaises(ValueError):
            self.check(s)


class UnifiedOfflineChainTests(unittest.TestCase):
    def chain(self, bundle=None, db=None, stage=None, build=None):
        names, snap = build_snapshot()
        return build_review(bundle if bundle is not None else fixture(True), projection(),
                            build_snapshot=build if build is not None else snap, expected_jobs=names, now=NOW,
                            runtime_snapshot=stage if stage is not None else runtime(), runtime_now=NOW,
                            database_snapshot=db if db is not None else database(), database_now=NOW)

    def test_full_assertions_held_and_unified_report(self):
        r = self.chain()
        self.assertEqual(r["state"], "HELD")
        self.assertIn("hold:ACTIVE", r["blockers"])
        self.assertIn("approval:INDEPENDENT_HUMAN_PROOF_NOT_ESTABLISHED", r["blockers"])
        for key in ("offline_staging_projection", "offline_build_review", "offline_runtime_review",
                    "offline_database_review"):
            self.assertIn(key, r)
        for k in ("release_eligible", "deployment_authorized", "production_authorized", "live_verified"):
            self.assertIs(r[k], False)
        md = unified_markdown(r)
        self.assertIn("V29 -> V30", md)
        self.assertIn("HIGH_REVIEW", md)
        self.assertIn("NOT AUTHORIZED", md)

    def test_clear_hold_still_blocked_and_claimed_gate_downgraded(self):
        b = fixture(True)
        b["hold"]["state"] = "clear"
        r = self.chain(bundle=b)
        self.assertEqual(r["state"], "BLOCKED")
        for g in ("migration", "backup_restore", "risk", "approval"):
            row = next(x for x in r["gates"] if x["gate"] == g)
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["underlying_claimed_status"], "pass")

    def test_preserve_failure_and_cross_gate_risk_mismatch(self):
        b = fixture(True)
        b["evidence"]["backup_restore"]["status"] = "fail"
        b["evidence"]["risk"]["risk"] = "FEATURE_REVIEW"
        r = self.chain(bundle=b)
        self.assertIn("backup_restore:REPORTED_FAIL", r["blockers"])
        self.assertIn("risk:INVENTORY_RISK_CLASSIFICATION_MISMATCH", r["blockers"])
        self.assertFalse(r["offline_database_review"]["correlation_claimed"]["risk"])

    def test_migration_after_runtime_observation(self):
        s = database()
        s["migration"]["finished_at"] = NOW-20
        r = self.chain(db=s)
        self.assertIn("migration:MIGRATION_NOT_BEFORE_UAT", r["blockers"])
        self.assertFalse(r["offline_database_review"]["correlation_claimed"]["migration"])

    def test_late_rehearsal_blocks_combined_report_and_markdown(self):
        s = database()
        s["restore"].update(started_at=NOW-10, finished_at=NOW-1)
        r = self.chain(db=s)
        finding = "backup_restore:RESTORE_REHEARSAL_NOT_BEFORE_MIGRATION"
        self.assertFalse(r["offline_database_review"]["correlation_claimed"]["backup_restore"])
        self.assertIn(finding, r["blockers"])
        self.assertIn(finding, unified_markdown(r))
        self.assertFalse(r["production_authorized"])

    def test_multiple_failures_preserved_in_one_report(self):
        names, snap = build_snapshot()
        snap["ci"]["jobs"][0]["conclusion"] = "skipped"
        stage = runtime()
        stage["before"]["compose_match"] = False
        db = database()
        db["restore"]["validation"] = "fail"
        r = self.chain(db=db, stage=stage, build=snap)
        for reason in ("build:CI_JOB_NOT_EXACT_SUCCESS", "runtime:COMPOSE_SOURCE_MISMATCH",
                       "backup_restore:RESTORE_VALIDATION_NOT_PASS", "hold:ACTIVE"):
            self.assertIn(reason, r["blockers"])
            self.assertIn(reason, unified_markdown(r))

    def test_missing_sections_and_no_unsafe_report_render(self):
        r = build_review(fixture(True), projection())
        for gate in ("build", "runtime", "migration", "backup_restore", "risk"):
            self.assertIn(gate + ":OFFLINE_REVIEW_MISSING", r["blockers"])
        self.assertIn("Missing", unified_markdown(r))
        r["production_authorized"] = True
        with self.assertRaises(ValueError):
            unified_markdown(r)

    def test_incomplete_parameters_fail_closed(self):
        with self.assertRaises(ValueError):
            build_review(fixture(), projection(), database_now=NOW)


if __name__ == "__main__":
    unittest.main()
