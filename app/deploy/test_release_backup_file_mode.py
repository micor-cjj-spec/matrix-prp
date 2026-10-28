"""No server, Docker, credentials, MySQL or production backups are accessed.

Executes only the parsed dump() function with a synthetic writer and
temporary files. The rest of the release program is NEVER executed.
"""
import ast
import os
from pathlib import Path
import stat
import tempfile
import unittest


FILES = (
    Path(__file__).parent / "approved" / "prp-release.py",
    Path(__file__).parent / "server-release.py",
)


def isolated_dump(source, called):
    text = source.read_text(encoding="utf-8")
    module = ast.parse(text, filename=str(source))
    fns = [node for node in module.body
           if isinstance(node, ast.FunctionDef) and node.name == "dump"]
    if len(fns) != 1:
        raise AssertionError("Release script dump() function missing/duplicated")
    node = fns[0]
    # Only the selected dump() AST gets executed; no top-level commands,
    # backup, import, deploy, Docker, shell, or any network function.
    isolated = compile(ast.Module(body=[node], type_ignores=[]), "<only-dump-ast>", "exec")

    def fake_run(args, *, stdout):
        called.append(1)
        stdout.write(b"-- SYNTHETIC TEST BACKUP - NO REAL DB ROWS --\n")

    namespace = {"os": os, "run": fake_run}
    exec(isolated, namespace)
    return namespace["dump"]


class BackupFilePermissionsTests(unittest.TestCase):
    def test_every_release_dump_is_owner_only_even_with_permissive_umask(self):
        for source in FILES:
            with self.subTest(source=source.name):
                called = []
                dump = isolated_dump(source, called)
                with tempfile.TemporaryDirectory() as td:
                    target = Path(td) / "preflight.sql"
                    previous_umask = os.umask(0o000)
                    try:
                        dump(target)
                    finally:
                        os.umask(previous_umask)
                    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                    self.assertEqual(target.read_bytes(),
                                     b"-- SYNTHETIC TEST BACKUP - NO REAL DB ROWS --\n")
                    self.assertEqual(called, [1])

    def test_existing_historical_backup_cannot_be_overwritten(self):
        for source in FILES:
            with self.subTest(source=source.name):
                called = []
                dump = isolated_dump(source, called)
                with tempfile.TemporaryDirectory() as td:
                    target = Path(td) / "database.sql"
                    target.write_bytes(b"OLD_BACKUP_PRESERVE")
                    with self.assertRaises(FileExistsError):
                        dump(target)
                    self.assertEqual(target.read_bytes(), b"OLD_BACKUP_PRESERVE")
                    self.assertEqual(called, [])

    def test_symlink_backup_path_is_rejected_without_following_it(self):
        for source in FILES:
            with self.subTest(source=source.name):
                called = []
                dump = isolated_dump(source, called)
                with tempfile.TemporaryDirectory() as td:
                    data = Path(td) / "sensitive.sql"
                    data.write_bytes(b"SECRET_NEVER_TOUCH")
                    link = Path(td) / "database.sql"
                    link.symlink_to(data)
                    with self.assertRaises(OSError):
                        dump(link)
                    self.assertEqual(data.read_bytes(), b"SECRET_NEVER_TOUCH")
                    self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
