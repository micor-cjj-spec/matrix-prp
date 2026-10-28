"""No Docker or network: negative tests for candidate JAR/source lineage."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import verify_oci_migration_jar as m


class ReviewOnlyJarSqlTests(unittest.TestCase):
    def setup_fixture(self, root):
        directory = root / "source"
        directory.mkdir()
        sql = {}
        for i in range(1, 29):
            name = f"V{i}__synthetic_ci_{i}.sql"
            value = f"-- CI only\\nCREATE TABLE ci_dummy_{i} (id INT);\\n".encode()
            (directory / name).write_bytes(value)
            sql[name] = value
        return directory, sql

    def create_jar(self, path, sql, *, extra=None, duplicates=False):
        with ZipFile(path, "w") as jar:
            for name, value in sql.items():
                key = m.PREFIX + name
                jar.writestr(key, value)
                if duplicates and name.startswith("V1__"):
                    jar.writestr(key, value)
            for key, value in (extra or {}).items():
                jar.writestr(key, value)

    def test_exact_source_byte_match_is_review_only(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            self.create_jar(jar, sql)
            result = m.validate(jar, source)
            self.assertEqual(result["source_migrations"], 28)
            self.assertEqual(result["jar_migrations"], 28)
            self.assertTrue(result["identical_raw_bytes"])
            self.assertFalse(result["deployment_permitted"])
            self.assertEqual(len(result["candidate_jar_sha256"]), 64)
            with redirect_stdout(StringIO()) as sink:
                exit_code = m.main(["--jar", str(jar), "--source", str(source)])
            self.assertEqual(exit_code, 4)
            self.assertNotIn(str(root), sink.getvalue())

    def test_one_byte_change_is_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            sql["V9__synthetic_ci_9.sql"] += b"-- tampered"
            self.create_jar(jar, sql)
            self.assertEqual(m.validate(jar, source)["reason"], "JAR_MIGRATION_BYTES_DRIFT")

    def test_missing_and_extra_jar_migrations_are_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            self.create_jar(jar, {k: v for k, v in sql.items() if not k.startswith("V3__")})
            self.assertEqual(m.validate(jar, source)["reason"], "JAR_MIGRATION_FILE_SET_DRIFT")
            self.create_jar(jar, sql, extra={m.PREFIX + "V29__unexpected.sql": b"SELECT 1;"})
            self.assertEqual(m.validate(jar, source)["reason"], "JAR_MIGRATION_FILE_SET_DRIFT")

    def test_unknown_file_under_migration_directory_is_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            self.create_jar(jar, sql, extra={m.PREFIX + "sneaky/override.sql": b"DROP TABLE owners;"})
            self.assertEqual(m.validate(jar, source)["reason"], "UNRECOGNIZED_PACKAGED_MIGRATION_FILE")

    def test_duplicate_zip_names_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                self.create_jar(jar, sql, duplicates=True)
            self.assertEqual(m.validate(jar, source)["reason"], "DUPLICATED_ZIP_ENTRY_NAMES")

    def test_invalid_source_migration_set_is_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            self.create_jar(jar, sql)
            (source / "V22__synthetic_ci_22.sql").unlink()
            self.assertEqual(m.validate(jar, source)["reason"], "SOURCE_EXPECTED_V1_V28_INCOMPLETE")

    def test_symlinked_jar_is_blocked(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, sql = self.setup_fixture(root)
            jar = root / "synthetic.jar"
            self.create_jar(jar, sql)
            link = root / "linked.jar"
            link.symlink_to(jar)
            self.assertEqual(m.validate(link, source)["reason"], "INPUT_NOT_TRUSTED_REGULAR_CI_ARTIFACT")

    def test_unreadable_jar_fails_closed_without_echo(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source, _ = self.setup_fixture(root)
            jar = root / "bad.jar"
            jar.write_bytes(b"not a jar")
            with redirect_stdout(StringIO()) as sink:
                status = m.main(["--jar", str(jar), "--source", str(source)])
            self.assertEqual(status, 2)
            result = json.loads(sink.getvalue())
            self.assertEqual(result["decision"], "BLOCKED")
            self.assertIs(result["deployment_permitted"], False)
            self.assertNotIn(str(root), sink.getvalue())


if __name__ == "__main__":
    unittest.main()
