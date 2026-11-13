"""SQL text contract; no network, MySQL, user data or Docker access."""
from pathlib import Path
import re
import unittest

SQL = Path(__file__).with_name("production_mysql_backup_consistency_readonly.sql")


class BackupConsistencyReadOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SQL.read_text(encoding="utf-8")
        cls.sql = "\n".join(
            row.split("--", 1)[0] for row in cls.source.splitlines())

    def test_fixed_single_readonly_select(self):
        text = self.sql
        self.assertEqual(text.count(";"), 1)
        self.assertTrue(text.strip().upper().startswith("WITH OBJECT_SUMMARY AS"))
        self.assertTrue(text.strip().endswith("FROM object_summary CROSS JOIN other_objects;"))
        for operation in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP",
                          "CREATE", "TRUNCATE", "REPLACE", "GRANT",
                          "REVOKE", "CALL", "EXECUTE", "OUTFILE", "INTO",
                          "LOCK", "FLUSH", "SET", "USE", "LOAD"):
            with self.subTest(operation=operation):
                self.assertIsNone(
                    re.search(r"\b" + operation + r"\b", text, re.I))

    def test_no_business_table_rows_or_secret_variable_values(self):
        text = self.sql
        self.assertEqual(text.count("TABLE_SCHEMA='matrix_prp'"), 1)
        self.assertEqual(text.count("TRIGGER_SCHEMA='matrix_prp'"), 1)
        self.assertEqual(text.count("ROUTINE_SCHEMA='matrix_prp'"), 1)
        self.assertEqual(text.count("EVENT_SCHEMA='matrix_prp'"), 1)
        self.assertIn("DATABASE()='matrix_prp'", text)
        self.assertIn("FROM information_schema.TABLES", text)
        self.assertIn("FROM information_schema.TRIGGERS", text)
        self.assertIn("FROM information_schema.ROUTINES", text)
        self.assertIn("FROM information_schema.EVENTS", text)
        self.assertEqual(len(re.findall(
            r"\bFROM flyway_schema_history\b", text, re.I)), 2)
        for forbidden in ("prp_users", "prp_tasks", "mysql.user",
                          "information_schema.COLUMNS", "@@GLOBAL.sql_log_bin",
                          "@@GLOBAL.super_read_only", "DATABASES;", "SHOW "):
            self.assertNotIn(forbidden, text)

    def test_counts_and_fail_closed_decision(self):
        s = self.sql
        for marker in ("base_tables_visible>0",
                       "innodb_tables_visible=base_tables_visible",
                       "non_innodb_or_unknown_tables_visible=0",
                       "(SELECT COUNT(*) FROM flyway_schema_history)=18",
                       "VISIBLE_BASE_TABLE_ENGINES_INNODB_REVIEW_ONLY",
                       "ELSE 'BLOCKED_OR_UNVERIFIED'",
                       "@@GLOBAL.log_bin", "@@GLOBAL.gtid_mode",
                       "'NO' AS backup_approved",
                       "'NO' AS deployment_permitted"):
            self.assertIn(marker, s)
        self.assertNotIn("'YES' AS backup_approved", s)
        self.assertNotIn("'YES' AS deployment_permitted", s)


if __name__ == "__main__":
    unittest.main()
