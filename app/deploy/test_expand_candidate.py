"""Strict negative cases: this does not change the production policy validator."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from expand_candidate import MAX_CANDIDATE_BYTES, main, parse_candidate
from migration_policy import migration_policy_sql_tables, migration_policy_validate


SQL = (b"ALTER TABLE prp_finance_transactions "
       b"ADD COLUMN source_platform VARCHAR(32) NULL, "
       b"ALGORITHM=INSTANT;")


class ExpandCandidateTests(unittest.TestCase):
    def test_candidate_report_is_explicitly_non_authorizing(self):
        candidate = parse_candidate(SQL)
        self.assertEqual(candidate.table, "prp_finance_transactions")
        self.assertEqual(candidate.column, "source_platform")
        self.assertEqual(candidate.column_type, "VARCHAR(32)")
        report = candidate.review_report()
        self.assertEqual(report["classification"], "SPECIALIST_REVIEW_REQUIRED")
        self.assertFalse(report["production_authorized"])
        self.assertTrue(report["controller_upgrade_required"])
        self.assertEqual(report["sql_sha256"], hashlib.sha256(SQL).hexdigest())
        self.assertEqual(report["algorithm"], "INSTANT")
        self.assertEqual(report["lock"], "IMPLICIT_DEFAULT")

    def test_eligible_types_and_whitespace(self):
        for typ in ("BIGINT", "INT", "DATE", "DATETIME(6)", "DECIMAL(18,2)",
                    "DECIMAL(2,0)", "VARCHAR(1)", "VARCHAR(1024)"):
            with self.subTest(typ=typ):
                sql = f"ALTER TABLE prp_people ADD COLUMN review_field {typ} NULL,\n ALGORITHM=INSTANT;".encode("ascii")
                self.assertEqual(parse_candidate(sql).column_type, typ)

    def test_forbidden_operations_modifiers_and_injection_fail_closed(self):
        cases = [
            SQL + b" DROP TABLE prp_users;",
            SQL + b" INSERT INTO prp_finance_transactions VALUES(1);",
            SQL.replace(b"ADD COLUMN", b"DROP COLUMN"),
            SQL.replace(b"ADD COLUMN", b"CHANGE COLUMN"),
            SQL.replace(b"ADD COLUMN", b"ADD INDEX"),
            SQL.replace(b" NULL,", b" NOT NULL,"),
            SQL.replace(b" NULL,", b" NULL DEFAULT NULL,"),
            SQL.replace(b" NULL,", b" NULL DEFAULT 'x',"),
            SQL.replace(b"ALGORITHM=INSTANT", b"ALGORITHM=COPY"),
            SQL.replace(b"ALGORITHM=INSTANT", b"ALGORITHM=INSTANT, LOCK=SHARED"),
            SQL.replace(b"ALGORITHM=INSTANT", b"ALGORITHM=INSTANT, LOCK=DEFAULT"),
            SQL.replace(b"prp_finance_transactions", b"other_schema.prp_finance_transactions"),
            SQL.replace(b"prp_finance_transactions", b"PRP_finance_transactions"),
            SQL.replace(b"source_platform", b"sourcePlatform"),
            SQL.replace(b"source_platform", b"`source_platform`"),
            SQL.replace(b"VARCHAR(32)", b"VARCHAR(0)"),
            SQL.replace(b"VARCHAR(32)", b"VARCHAR(1025)"),
            SQL.replace(b"VARCHAR(32)", b"VARCHAR(99999)"),
            SQL.replace(b"VARCHAR(32)", b"DECIMAL(2,3)"),
            SQL.replace(b"VARCHAR(32)", b"DECIMAL(39,2)"),
            SQL.replace(b"VARCHAR(32)", b"VARCHAR(32) AFTER id"),
            SQL.replace(b"VARCHAR(32)", b"VARCHAR(32), ADD COLUMN another INT"),
            SQL.replace(b"ALTER TABLE", b"ALTER /*unsafe*/ TABLE"),
            b"-- comment\n" + SQL,
            b"/*!50000 DROP TABLE prp_users */" + SQL,
            SQL[:-1],
            b"",
            SQL + b"\x00",
            SQL + "\u202e".encode("utf-8"),
            b" " * (MAX_CANDIDATE_BYTES + 1),
        ]
        for raw in cases:
            with self.subTest(sql=raw[:120]), self.assertRaises(ValueError):
                parse_candidate(raw)

    def test_current_production_create_empty_policy_still_rejects_candidate(self):
        # A successful offline preflight MUST NOT authorize the source migration.
        self.assertEqual(parse_candidate(SQL).column, "source_platform")
        with self.assertRaises(ValueError):
            migration_policy_sql_tables(SQL)
        forged = {"schema_version": 1, "rules": [
            {"version": 24, "file": "V24__source_platform.sql",
             "sha256": hashlib.sha256(SQL).hexdigest(),
             "mode": "create-empty", "tables": ["prp_finance_transactions"]}
        ]}
        with self.assertRaises(ValueError):
            migration_policy_validate(forged, {24: ("V24__source_platform.sql", SQL)})

    def test_report_json_and_input_failure_are_safe_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate_file = Path(tmp) / "candidate.sql"
            candidate_file.write_bytes(SQL)
            from io import StringIO
            from contextlib import redirect_stdout
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--sql", str(candidate_file)]), 0)
            report = json.loads(output.getvalue())
            self.assertFalse(report["production_authorized"])
            self.assertNotIn("user_data", report)
            self.assertEqual(report["sql_sha256"], hashlib.sha256(SQL).hexdigest())
            candidate_file.write_text("DROP TABLE prp_users;")
            with self.assertRaises(SystemExit) as failure:
                main(["--sql", str(candidate_file)])
            self.assertEqual(failure.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
