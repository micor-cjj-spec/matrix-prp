"""Offline preflight negative tests. No database, credentials or network."""
from io import StringIO
import contextlib
import json
from pathlib import Path
import tempfile
import unittest

import review_production_flyway_history as m


class ProductionFlywayHistoryReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = m.source_scripts()

    def history(self, latest=24):
        return {
            "schema": "matrix_prp",
            "history": [
                {
                    "installed_rank": n,
                    "version": str(n),
                    "script": self.scripts[n],
                    "checksum": (n * 10001) - 333,
                    "success": "PASS",
                }
                for n in range(1, latest + 1)
            ],
        }

    def check(self, obj):
        return m.analyze(obj, self.scripts)

    def test_expected_local_migrations_are_strict_1_to_28(self):
        self.assertEqual(set(self.scripts), set(range(1, 29)))
        self.assertEqual(self.scripts[24], "V24__vocal_song_library_and_assignments.sql")
        self.assertEqual(self.scripts[25], "V25__mcp_write_drafts.sql")
        self.assertEqual(self.scripts[28], "V28__mcp_first_party_oidc_link_flows.sql")

    def test_synthetic_v24_cannot_be_mistaken_for_signed_upgrade_approval(self):
        out = self.check(self.history())
        self.assertEqual(out["history_rows_checked"], 24)
        self.assertTrue(out["source_migration_names_match"])
        self.assertIn("CHECKSUMS_UNVERIFIED", out["decision"])
        self.assertIs(out["flyway_checksums_verified"], False)
        self.assertIs(out["deployment_permitted"], False)
        self.assertEqual(out["g0_b2_authorization"], "NOT_ESTABLISHED")

    def test_synthetic_v28_is_review_only_never_retroactive_approval(self):
        out = self.check(self.history(28))
        self.assertEqual(out["history_rows_checked"], 28)
        self.assertTrue(out["decision"].startswith("V28_"))
        self.assertIs(out["deployment_permitted"], False)

    def test_legacy_staging_v24_drafts_is_blocked(self):
        a = self.history(26)
        a["history"][23]["script"] = "V24__mcp_write_drafts.sql"
        self.assertEqual(self.check(a)["reason"], "MIGRATION_VERSION_OR_SCRIPT_DRIFT")

    def test_checksum_present_but_wrong_value_cannot_be_verified(self):
        a = self.history()
        a["history"][4]["checksum"] = 12345678
        self.assertIn("CHECKSUMS_UNVERIFIED", self.check(a)["decision"])
        # The verifier has no genuine trusted Flyway baseline; source
        # name matches are NEVER strong checksum acceptance.
        a["history"][4]["checksum"] = None
        self.assertEqual(self.check(a)["reason"], "HISTORY_ROW_INVALID_FAILED_OR_BASELINED")

    def test_failed_migration_blocks(self):
        a = self.history()
        a["history"][20]["success"] = "FAIL"
        self.assertEqual(self.check(a)["reason"], "HISTORY_ROW_INVALID_FAILED_OR_BASELINED")

    def test_baseline_or_nonversioned_entry_blocks(self):
        a = self.history()
        a["history"][0]["version"] = None
        self.assertEqual(self.check(a)["reason"], "HISTORY_ROW_INVALID_FAILED_OR_BASELINED")

    def test_partial_mcp_history_blocks(self):
        a = self.history(27)
        self.assertEqual(self.check(a)["reason"], "PARTIAL_OR_UNEXPECTED_MIGRATION_CHAIN")

    def test_missing_historical_migration_blocks(self):
        a = self.history()
        del a["history"][11]
        self.assertEqual(self.check(a)["reason"], "HISTORY_INSTALL_RANK_GAP_OR_BASELINE")

    def test_json_arrayagg_unordered_rows_still_valid_when_ranks_are_consistent(self):
        a = self.history()
        a["history"].reverse()
        out = self.check(a)
        self.assertEqual(out["history_rows_checked"], 24)
        self.assertTrue(out["source_migration_names_match"])
        self.assertIs(out["deployment_permitted"], False)

    def test_duplicate_version_and_install_rank_block(self):
        a = self.history()
        a["history"][10]["version"] = "10"
        a["history"][10]["script"] = self.scripts[10]
        self.assertEqual(self.check(a)["reason"], "DUPLICATE_MIGRATION_OR_INSTALL_RANK")
        a = self.history()
        a["history"][10]["installed_rank"] = 10
        self.assertEqual(self.check(a)["reason"], "DUPLICATE_MIGRATION_OR_INSTALL_RANK")

    def test_wrong_install_order_and_gaps_block(self):
        a = self.history()
        a["history"][7]["installed_rank"], a["history"][8]["installed_rank"] = (
            a["history"][8]["installed_rank"], a["history"][7]["installed_rank"]
        )
        self.assertEqual(self.check(a)["reason"], "HISTORY_NOT_IN_ASCENDING_INSTALL_ORDER")
        a = self.history()
        a["history"][0]["installed_rank"] = 2
        self.assertEqual(self.check(a)["reason"], "DUPLICATE_MIGRATION_OR_INSTALL_RANK")
        a = self.history()
        for item in a["history"]:
            item["installed_rank"] += 2
        self.assertEqual(self.check(a)["reason"], "HISTORY_INSTALL_RANK_GAP_OR_BASELINE")

    def test_unexpected_schema_or_unknown_history_shape_blocks(self):
        a = self.history()
        a["schema"] = "matrix_prp_mcp_stage"
        self.assertEqual(self.check(a)["reason"], "SCHEMA_UNVERIFIED_OR_REPORT_FORMAT_INVALID")
        a = self.history()
        a["history"][0]["extra_sensitive"] = "untrusted"
        self.assertEqual(self.check(a)["reason"], "HISTORY_ROW_SHAPE_INVALID")
        self.assertEqual(self.check({"schema": "matrix_prp", "history": []})["reason"],
                         "MISSING_OR_UNEXPECTED_HISTORY_ROWS")

    def test_no_sql_text_or_sensitive_row_echo_in_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator-review.json"
            a = self.history()
            a["history"][2]["script"] = "SENSITIVE_SQL_MARKER"
            path.write_text(json.dumps(a), encoding="utf-8")
            sink = StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(m.main(["--input", str(path)]), 2)
            out = sink.getvalue()
            self.assertNotIn("SENSITIVE_SQL_MARKER", out)
            self.assertIn("BLOCKED_OR_UNVERIFIED", out)
            self.assertNotIn(str(path), out)

    def test_cli_returns_review_only_for_valid_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(self.history()), encoding="utf-8")
            sink = StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(m.main(["--input", str(path)]), 3)
            out = json.loads(sink.getvalue())
            self.assertTrue(out["decision"].startswith("V24_"))
            self.assertIs(out["deployment_permitted"], False)
            self.assertIs(out["flyway_checksums_verified"], False)

    def test_opt_in_source_crc_reference_matches_only_identical_values(self):
        reference = m.source_crc32()
        self.assertEqual(set(reference), set(range(1, 29)))
        self.assertTrue(all(type(value) is int for value in reference.values()))
        a = self.history()
        for row in a["history"]:
            row["checksum"] = reference[int(row["version"])]
        result = m.analyze(a, self.scripts, verified_source_crc=reference)
        self.assertEqual(result["decision"], "V24_SOURCE_CRC_MATCH_REVIEW_ONLY")
        self.assertIs(result["flyway_checksums_verified"], True)
        self.assertIs(result["deployment_permitted"], False)
        a["history"][9]["checksum"] ^= 1
        self.assertEqual(
            m.analyze(a, self.scripts, verified_source_crc=reference)["reason"],
            "MIGRATION_CHECKSUM_DRIFT"
        )

    def test_source_crc_reference_requires_28_complete_integer_records(self):
        a = self.history()
        self.assertEqual(
            m.analyze(a, self.scripts, verified_source_crc={24: 7})["reason"],
            "CANDIDATE_REFERENCE_UNTRUSTED_OR_INCOMPLETE"
        )
        ref = m.source_crc32()
        ref[24] = "not-an-integer"
        self.assertEqual(
            m.analyze(a, self.scripts, verified_source_crc=ref)["reason"],
            "CANDIDATE_REFERENCE_UNTRUSTED_OR_INCOMPLETE"
        )

    def test_opt_in_cli_never_returns_release_approval_status_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            a = self.history()
            expected = m.source_crc32()
            for row in a["history"]:
                row["checksum"] = expected[int(row["version"])]
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(a), encoding="utf-8")
            sink = StringIO()
            with contextlib.redirect_stdout(sink):
                status = m.main(["--input", str(path), "--verify-source-crc"])
            self.assertEqual(status, 4)
            result = json.loads(sink.getvalue())
            self.assertEqual(result["decision"], "V24_SOURCE_CRC_MATCH_REVIEW_ONLY")
            self.assertIs(result["deployment_permitted"], False)
            self.assertIs(result["flyway_checksums_verified"], True)

    def test_sql_inventory_is_read_only_and_metadata_only(self):
        sql = (Path(__file__).resolve().parent
               / "production_flyway_metadata_readonly.sql").read_text(encoding="utf-8")
        body = "\n".join(line for line in sql.splitlines()
                         if not line.lstrip().startswith("--")).strip()
        self.assertEqual(body.count(";"), 1)
        self.assertTrue(body.upper().startswith("SELECT JSON_OBJECT("))
        self.assertIn("flyway_schema_history", body)
        self.assertNotIn("prp_tasks", body)
        self.assertNotIn("prp_users", body)
        for forbidden in ("UPDATE ", "DELETE ", "INSERT ", "ALTER ", "GRANT ",
                          "SET ", "LOCK ", "CREATE ", "DROP ", "INTO OUTFILE"):
            self.assertNotIn(forbidden, body.upper())


if __name__ == "__main__":
    unittest.main()
