"""Offline, non-network attestation of the V25–V28 metadata-only preflight.

The tests read candidate Git SQL files only. They never connect to MySQL.
Even a positive review query is NOT a migration, restore or approval.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = Path(__file__).with_name("production_v24_mcp_ddl_shape_readonly.sql")
MIGRATIONS = ROOT / "backend/src/main/resources/db/migration"
TARGETS = (
    "V25__mcp_write_drafts.sql",
    "V26__mcp_client_grants.sql",
    "V27__mcp_identity_links.sql",
    "V28__mcp_temporary_client_grant_expiry.sql",
)


class ProductionMcpDdlReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL_FILE.read_text(encoding="utf-8")
        cls.migrations = [ (MIGRATIONS / name).read_text(encoding="utf-8")
                           for name in TARGETS ]

    def test_fixed_target_schema_and_no_business_data_read(self):
        sql = self.sql
        statements = "\n".join(
            line.split("--", 1)[0] for line in sql.splitlines())
        self.assertEqual(statements.count(";"), 1)
        self.assertTrue(statements.strip().upper().startswith("WITH FACTS AS ("))
        self.assertTrue(statements.rstrip().endswith("FROM facts;"))
        self.assertIn("DATABASE() = 'matrix_prp'", statements)
        self.assertIn("history_rows = 18", statements)
        self.assertIn("successful_history_rows = 18", statements)
        self.assertIn("proposed_version_history_rows = 0", statements)
        self.assertIn("'NO' AS deployment_permitted", statements)
        self.assertIn("V25_V28_FK_DDL_SHAPE_MATCH_REVIEW_ONLY", statements)
        for keyword in (
            "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE",
            "TRUNCATE", "GRANT", "REVOKE", "REPLACE", "CALL", "EXEC",
            "LOAD", "OUTFILE", "INTO", "LOCK", "USE",
        ):
            with self.subTest(keyword=keyword):
                self.assertIsNone(re.search(r"\b" + keyword + r"\b",
                                            statements, flags=re.I))
        self.assertNotRegex(statements, r"(?i)\bFROM\s+prp_(?:users|tasks)\b")
        self.assertEqual(len(re.findall(r"\bFROM\s+flyway_schema_history\b",
                                        statements, flags=re.I)), 3)

    def test_new_table_and_fk_names_derived_from_real_migrations(self):
        source = "\n".join(self.migrations)
        tables = set(re.findall(r"(?im)^CREATE TABLE\s+(\w+)", source))
        constraints = set(re.findall(
            r"(?i)\bCONSTRAINT\s+(\w+)\s+FOREIGN KEY", source))
        self.assertEqual(len(tables), 5)
        self.assertEqual(len(constraints), 5)
        self.assertEqual(source.count("REFERENCES prp_users(id)"), 4)
        self.assertEqual(source.count("REFERENCES prp_mcp_client_grants(user_id,client_id)"), 1)
        self.assertIn("owner_signed_bigint_id", self.sql)
        self.assertIn("owner_table_innodb", self.sql)
        self.assertIn("owner_primary_columns = 1", self.sql)
        self.assertIn("owner_partition_count = 0", self.sql)
        self.assertIn("proposed_table_name_collisions = 0", self.sql)
        self.assertIn("proposed_fk_name_collisions = 0", self.sql)
        for name in sorted(tables | constraints):
            with self.subTest(name=name):
                self.assertIn("'" + name + "'", self.sql)
        quoted = set(re.findall(r"'(prp_mcp_[a-z_]+|fk_(?:prp_)?mcp_[a-z_]+)'", self.sql))
        self.assertEqual(quoted, tables | constraints)

    def test_new_migration_changes_are_additive_only(self):
        combined = "\n".join(self.migrations)
        clean = "\n".join(
            line.split("--", 1)[0] for line in combined.splitlines())
        statements = [item.strip() for item in clean.split(";") if item.strip()]
        self.assertEqual(len(statements), 5)
        self.assertTrue(all(item.startswith("CREATE TABLE prp_mcp_")
                            for item in statements))
        # Foreign key ON DELETE CASCADE is valid additive DDL; only DML
        # *statements* are disallowed, not the DELETE keyword in an FK.
        for statement in statements:
            with self.subTest(statement=statement[:36]):
                self.assertNotRegex(
                    statement, r"(?im)^\\s*(?:UPDATE|DELETE|INSERT|ALTER|DROP|TRUNCATE)\\b")
        self.assertEqual(clean.count("ON DELETE CASCADE"), 5)

    def test_return_is_review_only_and_fails_closed(self):
        self.assertIn("ELSE 'BLOCKED_OR_UNVERIFIED'", self.sql)
        self.assertNotIn("deployment_permitted = 'YES'", self.sql)
        self.assertIn("'NO' AS deployment_permitted", self.sql)
        self.assertIn("AND owner_id_primary_member = 1", self.sql)
        self.assertIn("AND owner_primary_columns = 1", self.sql)
        self.assertIn("AND owner_signed_bigint_id = 1", self.sql)
        self.assertIn("AND proposed_table_name_collisions = 0", self.sql)
        self.assertIn("AND proposed_fk_name_collisions = 0", self.sql)


if __name__ == "__main__":
    unittest.main()
