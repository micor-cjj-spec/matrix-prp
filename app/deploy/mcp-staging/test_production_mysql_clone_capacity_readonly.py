"""Synthetic, no-Docker/no-DB tests for PRP MySQL clone capacity inventory."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import production_mysql_clone_capacity_readonly as p


def opts(**overrides):
    val = {
        "active": True,
        "container_status": "running",
        "image": "mysql:8.4",
        "mounts": True,
        "backup_parent": True,
        "free_backup_bytes": 30 * p.GIB,
        "free_source_bytes": 30 * p.GIB,
        "same_device": True,
        "mem_bytes": 3 * p.GIB,
        "db_size_mib": 2048,
    }
    val.update(overrides)
    return p.analyze(**val)


class FakeRunner:
    def __init__(self, *, status=b"running\n", image=b"mysql:8.4\n",
                 mounts=b'[]\n'):
        self.commands = []
        self.status = status
        self.image = image
        self.mounts = mounts

    def __call__(self, argv, *, stdout, stderr, check, timeout):
        self.commands.append(argv)
        if argv == ["systemctl", "is-active", p.SERVICE]:
            out = b"active\n"
        elif argv == ["docker", "inspect", "--format",
                      "{{.State.Status}}", p.CONTAINER]:
            out = self.status
        elif argv == ["docker", "inspect", "--format",
                      "{{.Config.Image}}", p.CONTAINER]:
            out = self.image
        elif argv == ["docker", "inspect", "--format",
                      "{{json .Mounts}}", p.CONTAINER]:
            out = self.mounts
        elif argv[:9] == ["nice", "-n", "15", "ionice", "-c3",
                         "du", "-sk", "-x", "--"]:
            out = b"1000000\t" + str(argv[-1]).encode() + b"\n"
        else:
            raise AssertionError("Unexpected command " + str(argv))
        return SimpleNamespace(returncode=0, stdout=out)


class CapacityReadOnlyTest(unittest.TestCase):
    def test_conservative_estimate_not_deployment_permission(self):
        val = opts()
        self.assertEqual(val["capacity_envelope"], "CAPACITY_ESTIMATE_REVIEW_ONLY")
        self.assertEqual(val["conservative_same_fs_review_requirement_mib"],
                         3 * 2048 + 4096)
        for field in ("real_backup_performed", "restore_executed",
                      "database_modified", "services_restarted",
                      "g0_b2_approval_issued", "deployment_permitted"):
            self.assertIs(val[field], False)
        self.assertNotIn("password", json.dumps(val).lower())
        self.assertNotIn("/var/lib", json.dumps(val))

    def test_fail_closed_on_resource_and_container(self):
        cases = (
            {"active": False},
            {"container_status": "exited"},
            {"image": "unknown:latest"},
            {"mounts": False},
            {"backup_parent": False},
            {"mem_bytes": p.GIB},
        )
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(opts(**case)["capacity_envelope"],
                                 "BLOCKED_OR_UNVERIFIED")
        self.assertEqual(
            opts(free_backup_bytes=7 * p.GIB)["capacity_envelope"],
            "INSUFFICIENT_FOR_CONSERVATIVE_SAME_FS_REVIEW")
        self.assertEqual(
            opts(same_device=False)["capacity_envelope"],
            "SEPARATE_FILESYSTEM_REVIEW_REQUIRED")

    def test_fixed_source_mount_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "mysql-data"
            good.mkdir()
            mounts = [{"Destination": p.MYSQL_DEST,
                       "Source": str(good), "Type": "volume"}]
            self.assertEqual(p.validate_mysql_mount(mounts), good)
            with self.assertRaisesRegex(p.PreflightError, "NOT_UNIQUE"):
                p.validate_mysql_mount(mounts + mounts)
            with self.assertRaisesRegex(p.PreflightError, "TYPE_UNREVIEWED"):
                p.validate_mysql_mount([{**mounts[0], "Type": "tmpfs"}])
            wrong = [{"Destination": "/var/lib/secret", "Source": str(good),
                      "Type": "volume"}]
            with self.assertRaisesRegex(p.PreflightError, "NOT_UNIQUE"):
                p.validate_mysql_mount(wrong)
            symlink = Path(tmp) / "linked"
            symlink.symlink_to(good, target_is_directory=True)
            with self.assertRaisesRegex(p.PreflightError, "UNSAFE"):
                p.validate_mysql_mount([{**mounts[0], "Source": str(symlink)}])
            with self.assertRaisesRegex(p.PreflightError, "TOO_BROAD"):
                p.validate_mysql_mount([{**mounts[0], "Source": "/"}])

    def test_du_only_fixed_bounded_metadata_command(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            value = p.measure_size_mib(Path(tmp), runner=runner)
        self.assertGreater(value, 900)
        self.assertEqual(runner.commands[0][:9],
                         ["nice", "-n", "15", "ionice", "-c3",
                          "du", "-sk", "-x", "--"])
        self.assertEqual(p.DU_TIMEOUT, 30)

    def test_full_check_uses_only_fixed_read_only_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "mysql"
            data.mkdir()
            fake = FakeRunner(mounts=json.dumps([{
                "Destination": p.MYSQL_DEST, "Source": str(data),
                "Type": "volume"
            }]).encode())
            from os import stat as real_stat
            # pathlib.Path.is_dir also calls os.stat. Keep real metadata
            # for the fake source, and emulate only the absent host backup root.
            def fake_stat(path, *args, **kwargs):
                if str(path) == str(p.BACKUP_ROOT):
                    return SimpleNamespace(st_dev=real_stat(data).st_dev)
                return real_stat(path, *args, **kwargs)
            with patch.object(p, "backup_parent_ok", return_value=True), \
                    patch.object(p, "memory_available", return_value=4*p.GIB), \
                    patch.object(p.shutil, "disk_usage",
                                 return_value=SimpleNamespace(free=20*p.GIB)), \
                    patch.object(p.os, "stat", side_effect=fake_stat):
                outcome = p.check(runner=fake)
            self.assertEqual(outcome["capacity_envelope"],
                             "CAPACITY_ESTIMATE_REVIEW_ONLY")
            self.assertEqual(len(fake.commands), 5)
            self.assertTrue(all(x[0] in ("docker", "systemctl", "nice")
                                for x in fake.commands))
            self.assertNotIn(str(data), json.dumps(outcome))
            self.assertNotIn("password", json.dumps(outcome).lower())
            self.assertFalse(outcome["database_modified"])

    def test_broken_mount_fails_closed_with_redacted_diagnostic(self):
        fake = FakeRunner(mounts=b'[{"Destination":"/var/lib/mysql", "Source":'
                                 b'"/etc/secret", "Type":"tmpfs"}]')
        response = p.check(runner=fake)
        self.assertEqual(response["capacity_envelope"],
                         "BLOCKED_OR_UNVERIFIED")
        self.assertEqual(response["diagnostic"], "MYSQL_DATA_MOUNT_TYPE_UNREVIEWED")
        self.assertNotIn("secret", json.dumps(response))
        self.assertFalse(response["deployment_permitted"])

    def test_no_write_or_database_exec_in_review_script(self):
        script = Path(p.__file__).read_text(encoding="utf-8")
        for prohibited in (
            '["docker", "exec"', '["docker", "run"', '["docker", "stop"',
            '["docker", "cp"', '["docker", "compose"',
            '["mysql"', '["mysqldump"', '["pg_dump"',
            "subprocess.Popen(", "shell=True",
            ".Config.Env", ".env", "rmtree(", "mkdir(",
            "write_text(", "chmod(", "chown(", "unlink(",
        ):
            # Comments are not executable; guard core source contracts.
            self.assertNotIn(prohibited, script)


if __name__ == "__main__":
    unittest.main()
