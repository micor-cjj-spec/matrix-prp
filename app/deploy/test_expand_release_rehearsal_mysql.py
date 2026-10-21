"""ENG-03C isolated MySQL rehearsal: restore, app SQL compatibility, metadata lock.

The test only addresses fixed disposable CI databases on 127.0.0.1 using
synthetic credentials. It does not connect to Matrix PRP production or use
business records. Tests are not a substitute for real production data review.
"""
import hashlib
import os
import select
import shutil
import subprocess
import time
import unittest

DB_SOURCE = "matrix_prp_expand_verify"
DB_RESTORE = "matrix_prp_expand_restore_verify"
TABLE = "prp_expand_compatibility_fixture"
ADD = (f"ALTER TABLE {TABLE} ADD COLUMN source_platform VARCHAR(32) NULL, "
       "ALGORITHM=INSTANT;")
OLD_COLUMNS = "id,owner_user_id,HEX(note)"
INITIAL_ROWS = "1\t101\t616C706861\n2\t102\t62657461"


@unittest.skipUnless(os.environ.get("PRP_EXPAND_MYSQL_TEST") == "1",
                     "CI-only synthetic database rehearsal")
class ExpandReleaseRehearsalMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("CI") != "true" or os.environ.get("MYSQL_PWD") != "ci-app-password":
            raise RuntimeError("Synthetic CI credentials and explicit opt-in required")
        if DB_SOURCE == DB_RESTORE or "matrix_prp_expand_" not in DB_RESTORE:
            raise RuntimeError("Incorrect fixed CI-only rehearsal schema")

    @staticmethod
    def command(database, *, dump=False):
        if database not in (DB_SOURCE, DB_RESTORE):
            raise ValueError("Non-CI schema denied")
        executable = (shutil.which("mysqldump") or shutil.which("mariadb-dump")) if dump else "mysql"
        if not executable:
            raise RuntimeError("No CLI database dump tool available")
        args = [executable, "--protocol=TCP", "-h", "127.0.0.1", "-u", "matrix_prp",
                "--default-character-set=utf8mb4"]
        if dump:
            return args + ["--single-transaction", "--no-tablespaces", "--skip-comments",
                           database, TABLE]
        return args + ["-N", "-B", database]

    @classmethod
    def query(cls, db, statement, *, check=True):
        return subprocess.run(cls.command(db), input=statement, text=True, capture_output=True,
                              check=check, timeout=20)

    @classmethod
    def old_rows(cls, db):
        return cls.query(db, f"SELECT {OLD_COLUMNS} FROM {TABLE} ORDER BY id;").stdout.strip()

    @classmethod
    def before_snapshot(cls, db):
        rows = cls.old_rows(db)
        ddl = cls.query(db, f"SHOW CREATE TABLE {TABLE};").stdout.strip()
        return (hashlib.sha256(rows.encode()).hexdigest(),
                hashlib.sha256(ddl.encode()).hexdigest())

    def setUp(self):
        self.query(DB_SOURCE, f"DROP TABLE IF EXISTS {TABLE};")
        self.query(DB_RESTORE, f"DROP TABLE IF EXISTS {TABLE};")
        self.query(DB_SOURCE, f"CREATE TABLE {TABLE} ("
                   "id BIGINT PRIMARY KEY, owner_user_id BIGINT NOT NULL, "
                   "note VARCHAR(32) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        self.query(DB_SOURCE, f"INSERT INTO {TABLE} VALUES "
                   "(1,101,'alpha'),(2,102,'beta');")

    def tearDown(self):
        for db in (DB_RESTORE, DB_SOURCE):
            self.query(db, f"DROP TABLE IF EXISTS {TABLE};")

    def restored_copy(self):
        # This is the same logical dump/import pattern as rehearsal of a real
        # backup, but it intentionally contains only synthetic CI test records.
        dumped = subprocess.run(self.command(DB_SOURCE, dump=True),
                                text=True, capture_output=True, check=True, timeout=20).stdout
        self.assertIn("CREATE TABLE", dumped)
        self.assertIn("INSERT INTO", dumped)
        self.query(DB_RESTORE, dumped)
        self.assertEqual(self.old_rows(DB_RESTORE), self.old_rows(DB_SOURCE))
        return dumped

    def test_backup_restore_then_expand_preserves_original_and_old_client_projection(self):
        source_fingerprints = self.before_snapshot(DB_SOURCE)
        self.restored_copy()
        restored_fingerprints = self.before_snapshot(DB_RESTORE)
        self.assertEqual(restored_fingerprints, source_fingerprints)
        self.query(DB_RESTORE, ADD)
        self.assertEqual(self.old_rows(DB_RESTORE), self.old_rows(DB_SOURCE))
        self.assertEqual(self.before_snapshot(DB_SOURCE), source_fingerprints)
        self.assertEqual(self.query(DB_SOURCE, f"SELECT COUNT(*) FROM "
                         f"information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                         f"AND TABLE_NAME='{TABLE}' AND COLUMN_NAME='source_platform';").stdout.strip(), "0")

        # These old/new SQL projections are compatibility probes, not a test
        # of actual historical JAR binaries or API behavior.
        self.query(DB_RESTORE, f"INSERT INTO {TABLE} (id,owner_user_id,note) "
                   "VALUES (3,103,'old-client');")
        self.query(DB_RESTORE, f"INSERT INTO {TABLE} "
                   "(id,owner_user_id,note,source_platform) "
                   "VALUES (4,104,'new-client','wechat');")
        projected = self.old_rows(DB_RESTORE).splitlines()
        self.assertEqual(len(projected), 4)
        self.assertEqual(self.query(DB_RESTORE, f"SELECT owner_user_id,source_platform "
                         f"FROM {TABLE} WHERE id=3;").stdout.strip(), "103\tNULL")
        self.assertEqual(self.query(DB_RESTORE, f"SELECT owner_user_id,source_platform "
                         f"FROM {TABLE} WHERE id=4;").stdout.strip(), "104\twechat")
        self.assertEqual(self.old_rows(DB_SOURCE), "1\t101\t616C706861\n2\t102\t62657461")

    def test_metadata_lock_wait_fails_without_ddl_fallback_or_mutation(self):
        # Acquire a real metadata lock in a live transaction. MySQL's DDL
        # waiting time is bounded by per-session lock_wait_timeout.
        self.restored_copy()
        original = self.before_snapshot(DB_RESTORE)
        process = subprocess.Popen(
            self.command(DB_RESTORE)[:-1] + ["--unbuffered", DB_RESTORE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(f"START TRANSACTION;\nSELECT COUNT(*) FROM {TABLE};\n")
            process.stdin.flush()
            readable, _, _ = select.select([process.stdout], [], [], 10)
            if not readable or process.stdout.readline().strip() != "2":
                raise AssertionError("Did not establish concurrent reader metadata lock")
            start = time.monotonic()
            blocked = self.query(DB_RESTORE, "SET SESSION lock_wait_timeout=1; " + ADD,
                                 check=False)
            elapsed = time.monotonic() - start
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("Lock wait timeout exceeded", blocked.stderr)
            self.assertLess(elapsed, 12)
        finally:
            if process.poll() is None:
                try:
                    assert process.stdin is not None
                    process.stdin.write("ROLLBACK;\nquit\n")
                    process.stdin.flush()
                    process.wait(timeout=8)
                except (BrokenPipeError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        self.assertEqual(self.before_snapshot(DB_RESTORE), original)
        self.query(DB_RESTORE, ADD)  # No fallback; same INSTANT statement after lock released.
        self.assertEqual(self.old_rows(DB_RESTORE), self.old_rows(DB_SOURCE))
        self.assertEqual(self.query(DB_RESTORE, f"SELECT COUNT(*) FROM "
                         f"information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                         f"AND TABLE_NAME='{TABLE}' AND COLUMN_NAME='source_platform';").stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
