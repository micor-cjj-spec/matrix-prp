"""Real MySQL 8.4 rehearsal on an intentionally isolated, disposable CI schema.

The test refuses any user-supplied host/database. It cannot target PRP production.
No source-tree Flyway migration is added and no controller/publisher is changed.
"""
import os
import subprocess
import unittest

from expand_candidate import parse_candidate
from expand_review_contract import sha, create_review_contract, verify_review_contract

_TEST_DB = "matrix_prp_expand_verify"
_HOST = "127.0.0.1"
_USER = "matrix_prp"
_ADD_SQL = (b"ALTER TABLE prp_expand_fixture "
            b"ADD COLUMN source_platform VARCHAR(32) NULL, "
            b"ALGORITHM=INSTANT;")


@unittest.skipUnless(os.getenv("PRP_EXPAND_MYSQL_TEST") == "1",
                     "requires explicit disposable MySQL CI rehearsal")
class ExpandCandidateMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Refuse even an accidentally enabled local/prod run.
        if os.getenv("CI") != "true" or os.getenv("MYSQL_PWD") != "ci-app-password":
            raise RuntimeError("Only the synthetic GitHub CI MySQL credentials are permitted")

    def sql(self, statement: str) -> str:
        command = [
            "mysql", "--protocol=TCP", "-h", _HOST, "-u", _USER,
            "--default-character-set=utf8mb4", "-N", "-B",
            _TEST_DB,
        ]
        process = subprocess.run(command, input=statement, text=True,
                                 capture_output=True, check=True, timeout=20)
        return process.stdout.strip()

    def setUp(self):
        self.sql("DROP TABLE IF EXISTS prp_expand_fixture;")
        self.sql("CREATE TABLE prp_expand_fixture ("
                 "id BIGINT PRIMARY KEY, owner_user_id BIGINT NOT NULL, "
                 "note VARCHAR(30) NOT NULL"
                 ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        self.sql("INSERT INTO prp_expand_fixture VALUES "
                 "(1,101,'alpha'), (2,102,'beta');")

    def tearDown(self):
        self.sql("DROP TABLE IF EXISTS prp_expand_fixture;")

    def snapshot(self, *, added: bool):
        # Observe the actual MySQL 8.4 metadata rather than constructing it from
        # the expected contract. All queries target only the fixed CI test table.
        rows = self.sql("SELECT id,owner_user_id,HEX(note) "
                        "FROM prp_expand_fixture ORDER BY id;")
        fields = self.sql(
            "SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,"
            "COALESCE(COLUMN_DEFAULT,'<NULL>'),EXTRA,ORDINAL_POSITION "
            "FROM information_schema.COLUMNS WHERE "
            "TABLE_SCHEMA=DATABASE() AND TABLE_NAME='prp_expand_fixture' "
            "ORDER BY ORDINAL_POSITION;")
        columns = []
        for line in fields.splitlines():
            name, column_type, nullable, default, extra, ordinal = line.split("\\t")
            columns.append({
                "name": name, "type": column_type, "nullable": nullable == "YES",
                "default": None if default == "<NULL>" else default,
                "extra": extra, "ordinal": int(ordinal),
            })
        index_data = self.sql(
            "SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,NON_UNIQUE,INDEX_TYPE "
            "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='prp_expand_fixture' ORDER BY INDEX_NAME,SEQ_IN_INDEX;")
        constraints = self.sql(
            "SELECT CONSTRAINT_NAME,CONSTRAINT_TYPE FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='prp_expand_fixture' "
            "ORDER BY CONSTRAINT_NAME;")
        triggers = self.sql(
            "SELECT TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION,ACTION_STATEMENT "
            "FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() "
            "AND EVENT_OBJECT_TABLE='prp_expand_fixture' ORDER BY TRIGGER_NAME;")
        return {
            "table": "prp_expand_fixture",
            "mysql_version": self.sql("SELECT VERSION();"),
            "schema_version": 23,  # synthetic base for the candidate-only rehearsal
            "source_commit": "a" * 40,  # synthetic CI identity, never production attestation
            "columns": columns, "row_count": int(self.sql("SELECT COUNT(*) FROM prp_expand_fixture;")),
            "old_rows_sha256": sha(rows.encode("utf-8")),
            "indexes_sha256": sha(index_data.encode("utf-8")),
            "constraints_sha256": sha(constraints.encode("utf-8")),
            "triggers_sha256": sha(triggers.encode("utf-8")),
            "added_column_nonnull_count": (
                int(self.sql("SELECT COUNT(*) FROM prp_expand_fixture "
                             "WHERE source_platform IS NOT NULL;")) if added else None
            ),
        }

    def test_instant_nullable_column_keeps_original_records_and_ownership(self):
        before = self.sql("SELECT id,owner_user_id,HEX(note) "
                          "FROM prp_expand_fixture ORDER BY id;")
        metadata_before = self.snapshot(added=False)
        review_contract = create_review_contract(
            _ADD_SQL, metadata_before, source_commit="a" * 40, target_schema_version=24)
        candidate = parse_candidate(_ADD_SQL)
        self.assertEqual(candidate.table, "prp_expand_fixture")
        self.sql(_ADD_SQL.decode("ascii"))
        after = self.sql("SELECT id,owner_user_id,HEX(note) "
                         "FROM prp_expand_fixture ORDER BY id;")
        self.assertEqual(after, before)
        metadata_after = self.snapshot(added=True)
        evidence = verify_review_contract(
            review_contract, _ADD_SQL, metadata_before, metadata_after)
        self.assertEqual(evidence["classification"], "READY_FOR_SPECIALIST_REVIEW")
        self.assertFalse(evidence["production_authorized"])
        self.assertEqual(evidence["row_count_preserved"], 2)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM prp_expand_fixture;"), "2")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM prp_expand_fixture "
                                  "WHERE source_platform IS NOT NULL;"), "0")
        self.assertEqual(self.sql("SELECT IS_NULLABLE "
                                  "FROM information_schema.COLUMNS WHERE "
                                  "TABLE_SCHEMA=DATABASE() AND "
                                  "TABLE_NAME='prp_expand_fixture' AND "
                                  "COLUMN_NAME='source_platform';"), "YES")
        # A second replay must fail; versioned migration bookkeeping is mandatory.
        with self.assertRaises(subprocess.CalledProcessError):
            self.sql(_ADD_SQL.decode("ascii"))


if __name__ == "__main__":
    unittest.main()
