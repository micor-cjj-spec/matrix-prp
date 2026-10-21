"""Real MySQL 8.4 rehearsal on an intentionally isolated, disposable CI schema.

The test refuses any user-supplied host/database. It cannot target PRP production.
No source-tree Flyway migration is added and no controller/publisher is changed.
"""
import os
import subprocess
import unittest

from expand_candidate import parse_candidate

_TEST_DB = "matrix_prp_expand_verify"
_HOST = "127.0.0.1"
_USER = "matrix_prp"
_ADD_SQL = (b"ALTER TABLE prp_expand_fixture "
            b"ADD COLUMN source_platform VARCHAR(32) NULL, "
            b"ALGORITHM=INSTANT, LOCK=NONE;")


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

    def test_instant_nullable_column_keeps_original_records_and_ownership(self):
        before = self.sql("SELECT id,owner_user_id,HEX(note) "
                          "FROM prp_expand_fixture ORDER BY id;")
        candidate = parse_candidate(_ADD_SQL)
        self.assertEqual(candidate.table, "prp_expand_fixture")
        self.sql(_ADD_SQL.decode("ascii"))
        after = self.sql("SELECT id,owner_user_id,HEX(note) "
                         "FROM prp_expand_fixture ORDER BY id;")
        self.assertEqual(after, before)
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
