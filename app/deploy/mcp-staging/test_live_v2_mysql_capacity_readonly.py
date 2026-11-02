"""Offline, deterministic safety tests for fixed V2 volume capacity metadata."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import live_v2_mysql_capacity_readonly as p


class Fake:
    def __init__(self, source, *, state="running", image="mysql:8.4",
                 project="prp-mcp-v2", extra_mounts=(), fail_on=None):
        self.calls = []
        self.state = state
        self.image = image
        self.project = project
        self.source = source
        self.extra_mounts = extra_mounts
        self.fail_on = fail_on

    def __call__(self, argv, *, stdout, stderr, check, timeout):
        assert check is False and stdout == subprocess.PIPE
        assert stderr == subprocess.DEVNULL
        self.calls.append(tuple(argv))
        if self.fail_on and self.fail_on in argv:
            raise subprocess.TimeoutExpired(argv, timeout)
        if argv[:3] == ["docker", "inspect", "--format"]:
            assert argv[-1] == p.CONTAINER
            mapping = {
                "{{.State.Status}}": self.state,
                "{{.Config.Image}}": self.image,
                '{{index .Config.Labels "com.docker.compose.project"}}': self.project,
                "{{json .Mounts}}": json.dumps([
                    {"Type": "volume", "Destination": p.MYSQL_DEST,
                     "Name": "prp-mcp-v2_mysql", "Source": str(self.source)},
                    *self.extra_mounts,
                ]),
            }
            payload = mapping[argv[3]].encode() + b"\n"
        elif argv[:9] == ["nice", "-n", "15", "ionice", "-c3",
                         "du", "-sk", "-x", "--"]:
            assert argv[-1] == str(self.source)
            payload = b"1500000\t" + str(self.source).encode() + b"\n"
        else:
            raise AssertionError("FORBIDDEN_HOST_COMMAND:" + str(argv))
        return SimpleNamespace(returncode=0, stdout=payload)


def setup_volume(folder):
    path = Path(folder) / "docker" / "volumes" / "prp-mcp-v2_mysql" / "_data"
    path.mkdir(parents=True)
    return path


class V2CapacityReadOnly(unittest.TestCase):
    def test_positive_heuristic_is_never_backup_or_release_authorization(self):
        x = p.verdict(image=p.IMAGE, state="running", project=p.PROJECT,
                      mem_bytes=4 * p.GIB, free_bytes=20 * p.GIB,
                      footprint_mib=1500, same_root_device=True)
        self.assertEqual(x["capacity_decision"], "RESOURCE_ENVELOPE_REVIEW_ONLY")
        self.assertEqual(x["initial_heuristic_requirement_mib"], 8596)
        for name in ("real_backup_performed", "restore_executed", "database_modified",
                     "container_modified", "g0_b2_approval_issued",
                     "deployment_permitted"):
            self.assertIs(x[name], False)

    def test_low_memory_low_disk_and_wrong_container_fail_closed(self):
        b = dict(image=p.IMAGE, state="running", project=p.PROJECT,
                 mem_bytes=4*p.GIB, free_bytes=20*p.GIB,
                 footprint_mib=2000, same_root_device=True)
        for values in ({"mem_bytes": p.GIB}, {"project": "prp-mcp-stage"},
                       {"image": "mysql:9"}, {"state": "exited"}):
            with self.subTest(values=values):
                self.assertEqual(p.verdict(**{**b, **values})["capacity_decision"],
                                 "BLOCKED_OR_UNVERIFIED")
        self.assertEqual(p.verdict(**{**b, "free_bytes": 7*p.GIB})["capacity_decision"],
                         "CAPACITY_HEURISTIC_INSUFFICIENT")

    def test_exact_named_volume_only_and_never_follow_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = setup_volume(tmp)
            m = {"Destination": p.MYSQL_DEST, "Type": "volume",
                 "Name": "prp-mcp-v2_mysql", "Source": str(good)}
            self.assertEqual(p.checked_v2_mount([m]), good)
            for bad, message in (
                ([m, m], "NOT_UNIQUE"),
                ([{**m, "Type": "bind"}], "NAMED_VOLUME_REQUIRED"),
                ([{**m, "Name": "matrix-mysql"}], "IDENTITY_UNVERIFIED"),
                ([{**m, "Source": str(Path(tmp))}], "SOURCE_UNSAFE"),
                ([{**m, "Destination": "/var/lib/other"}], "NOT_UNIQUE"),
            ):
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(p.InventoryError, message):
                        p.checked_v2_mount(bad)
            alias = good.parent / "_linked"
            alias.symlink_to(good, target_is_directory=True)
            with self.assertRaises(p.InventoryError):
                p.checked_v2_mount([{**m, "Source": str(alias)}])

    def test_full_inventory_has_only_four_docker_inspects_and_low_priority_du(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = setup_volume(tmp)
            fake = Fake(source)
            with patch.object(p, "mem_available", return_value=4*p.GIB), \
                    patch.object(p.shutil, "disk_usage",
                                 return_value=SimpleNamespace(free=20*p.GIB)):
                result = p.inspect(runner=fake)
            self.assertEqual(result["capacity_decision"], "RESOURCE_ENVELOPE_REVIEW_ONLY")
            self.assertEqual(len(fake.calls), 5)
            self.assertEqual([x[0] for x in fake.calls],
                             ["docker", "docker", "docker", "docker", "nice"])
            self.assertEqual(fake.calls[-1][:9],
                             ("nice", "-n", "15", "ionice", "-c3",
                              "du", "-sk", "-x", "--"))
            self.assertNotIn(str(source), json.dumps(result))
            self.assertNotIn("MYSQL_PASSWORD", json.dumps(result))
            self.assertFalse(result["database_modified"])

    def test_wrong_compose_label_stops_before_volume_or_du(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(setup_volume(tmp), project="prp-mcp-stage")
            result = p.inspect(runner=fake)
            self.assertEqual(result["safe_diagnostic"],
                             "V2_CONTAINER_IDENTITY_OR_STATE_INVALID")
            self.assertEqual(len(fake.calls), 3)
            self.assertFalse(result["deployment_permitted"])

    def test_timeout_is_bounded_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = setup_volume(tmp)
            fake = Fake(source, fail_on="du")
            result = p.inspect(runner=fake)
            self.assertEqual(result["capacity_decision"], "BLOCKED_OR_UNVERIFIED")
            self.assertEqual(result["safe_diagnostic"],
                             "READ_ONLY_HOST_COMMAND_UNAVAILABLE")
            self.assertNotIn(str(source), json.dumps(result))

    def test_unexpected_mount_and_unsafe_path_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = setup_volume(tmp)
            second = {"Destination": p.MYSQL_DEST, "Type": "volume",
                      "Name": "prp-mcp-v2_other", "Source": str(source)}
            r = p.inspect(Fake(source, extra_mounts=(second,)))
            self.assertEqual(r["safe_diagnostic"], "V2_MYSQL_MOUNT_NOT_UNIQUE")
            self.assertFalse(r["database_modified"])

    def test_no_arguments_or_unsafe_host_operations_in_script(self):
        path = Path(p.__file__)
        result = subprocess.run(["python3", str(path), "--any"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("NO_OPERATOR_PARAMETERS_ACCEPTED", result.stderr)
        source = path.read_text(encoding="utf-8")
        for token in ('["docker", "exec"', '["docker", "cp"', '["docker", "run"',
                      '["mysql"', '["mysqldump"', "shell=True", ".Config.Env",
                      "subprocess.Popen(", "write_text(", "mkdir(", "chmod(",
                      "rmtree(", "flyway migrate"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
