"""Pure synthetic negative tests. Never access a real host Docker daemon."""
from pathlib import Path
import unittest
from unittest.mock import patch
import host_newdb_readonly_inventory as h

HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode"
EMPTY = HEADER + "\n"
PORT_18083_LISTENER = HEADER + (
    "\n   0: 0100007F:46A3 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 0"
)
OTHER_PORT_LISTENER = HEADER + (
    "\n   0: 00000000:46A2 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 0"
)
ORIGINAL = set(h.EXPECTED_EXISTING)
ABOVE_MEMORY = 3 * 1024**3
ABOVE_DISK = 27 * 1024**3


def report(**kwargs):
    data = {
        "proc4": EMPTY,
        "proc6": EMPTY,
        "containers": ORIGINAL,
        "volumes": set(),
        "networks": set(),
        "published_ports": set(),
        "mem_bytes": ABOVE_MEMORY,
        "disk_bytes": ABOVE_DISK,
    }
    data.update(kwargs)
    return h.analyze(**data)


class HostNewdbInventoryTests(unittest.TestCase):
    def test_expected_is_not_a_deployment_approval(self):
        result = report()
        self.assertEqual(result["newdb_host_preflight"],
                         "NO_COLLISION_OBSERVED_REVIEW_ONLY")
        self.assertIs(result["deployment_permitted"], False)
        self.assertEqual(result["b2_authorization"],
                         "NOT_ESTABLISHED_BY_THIS_SCRIPT")
        self.assertEqual(result["independent_g0_approval"],
                         "NOT_ESTABLISHED_BY_THIS_SCRIPT")
        self.assertNotIn("docker_environment", result)

    def test_listening_ipv4_and_ipv6_both_block(self):
        for key in ("proc4", "proc6"):
            with self.subTest(key=key):
                got = report(**{key: PORT_18083_LISTENER})
                self.assertEqual(got["host_observations"]["tcp_port_18083"],
                                 "LISTENER_PRESENT")
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")

    def test_other_listening_port_does_not_block_18083(self):
        got = report(proc4=OTHER_PORT_LISTENER)
        self.assertEqual(got["newdb_host_preflight"],
                         "NO_COLLISION_OBSERVED_REVIEW_ONLY")

    def test_docker_published_port_blocks_without_host_listener(self):
        for ports in (
            {"127.0.0.1:18083->8080/tcp"},
            {"0.0.0.0:18083->8080/tcp, :::18083->8080/tcp"},
            {"[::]:18083->8080/tcp"},
        ):
            with self.subTest(ports=ports):
                got = report(published_ports=ports)
                self.assertEqual(got["host_observations"]["docker_published_tcp_18083"],
                                 "PUBLISHED_PORT_PRESENT")
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")

    def test_unpublished_or_other_docker_port_does_not_block(self):
        got = report(published_ports={"8080/tcp", "0.0.0.0:18082->8080/tcp"})
        self.assertEqual(got["newdb_host_preflight"],
                         "NO_COLLISION_OBSERVED_REVIEW_ONLY")

    def test_unknown_proc_and_unparseable_states_are_blocked(self):
        for value in (None, "bad", HEADER + "\n 0: invalid_line"):
            with self.subTest(proc=value):
                got = report(proc4=value)
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")

    def test_existing_project_containers_volumes_networks_block(self):
        cases = (
            ("containers", ORIGINAL | {"prp-mcp-newdb-review-mysql-1"}),
            ("volumes", {"prp-mcp-newdb-review_newdb_mysql"}),
            ("volumes", {"prp-mcp-newdb-review_newdb_vocal"}),
            ("networks", {"prp-mcp-newdb-review_newdb_private"}),
        )
        for key, items in cases:
            with self.subTest(key=key, items=str(items)):
                got = report(**{key: items})
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")

    def test_docker_permission_failure_is_unknown_not_free(self):
        for key in ("containers", "volumes", "networks", "published_ports"):
            with self.subTest(key=key):
                got = report(**{key: None})
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")
                self.assertIn("UNKNOWN", str(got["host_observations"]))

    def test_known_gateway_absence_and_insufficient_resources_block(self):
        for mutation in (
            {"containers": {"prp-mcp-v2-gateway-1"}},
            {"containers": {"prp-mcp-stage-gateway-1"}},
            {"mem_bytes": 1 * 1024**3},
            {"disk_bytes": 8 * 1024**3},
            {"mem_bytes": None},
            {"disk_bytes": None},
        ):
            with self.subTest(mutation=str(mutation)):
                got = report(**mutation)
                self.assertEqual(got["newdb_host_preflight"],
                                 "BLOCKED_OR_UNVERIFIED")

    def test_only_allowlisted_read_only_docker_commands(self):
        self.assertEqual(
            h.READ_ONLY_DOCKER_COMMANDS,
            {
                "containers": ("docker", "ps", "-a", "--format", "{{.Names}}"),
                "published_ports": ("docker", "ps", "--format", "{{.Ports}}"),
                "volumes": ("docker", "volume", "ls", "--format", "{{.Name}}"),
                "networks": ("docker", "network", "ls", "--format", "{{.Name}}"),
            },
        )
        for cmd in h.READ_ONLY_DOCKER_COMMANDS.values():
            self.assertNotIn("inspect", cmd)
            for forbidden in ("run", "create", "rm", "start", "stop", "up",
                              "down", "prune", "exec", "cp"):
                self.assertNotIn(forbidden, cmd)

    @patch.object(h.subprocess, "run")
    def test_stdout_only_name_listing_and_no_secret_output(self, mocked):
        mocked.return_value.returncode = 0
        mocked.return_value.stdout = "prp-mcp-v2-gateway-1\nprp-mcp-stage-gateway-1\n"
        names = h.docker_names("containers")
        self.assertEqual(names, ORIGINAL)
        self.assertEqual(mocked.call_args.args[0],
                         h.READ_ONLY_DOCKER_COMMANDS["containers"])
        self.assertEqual(mocked.call_args.kwargs["capture_output"], True)

    def test_source_has_no_mutation_interfaces(self):
        code = (Path(__file__).parent / "host_newdb_readonly_inventory.py").read_text()
        self.assertNotIn("os.system(", code)
        self.assertNotIn("shell=True", code)
        self.assertNotIn("open(\"w\"", code)
        self.assertNotIn("docker inspect", code.replace("# No Docker inspect Config.Env", ""))


if __name__ == "__main__":
    unittest.main()
