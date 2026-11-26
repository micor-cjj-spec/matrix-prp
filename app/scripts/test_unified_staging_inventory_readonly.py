"""Offline synthetic tests: never contact Docker, SSH, a server or a database."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import unified_staging_inventory_readonly as h

HEADER = " sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode"
EMPTY = HEADER + "\n"


def tcp(port, state="0A"):
    return HEADER + f"\n0: 0100007F:{port:04X} 00000000:0000 {state} 0 0 0 0 0 0\n"


def snapshot(**overrides):
    args = dict(
        proc4=EMPTY, proc6=EMPTY,
        containers=set(), published=set(), volumes=set(), networks=set(),
        free_memory=4 * 1024**3, free_disk=30 * 1024**3,
        observed_utc="2026-11-23T00:00:00Z",
    )
    args.update(overrides)
    return h.analyze(**args)


class UnifiedStagingInventoryTests(unittest.TestCase):
    def test_baseline_never_authorizes_deploy_even_if_no_listener(self):
        result = snapshot()
        for port in h.PORTS:
            with self.subTest(port=port):
                self.assertEqual(result["ports"][str(port)]["host_tcp"],
                                 "NO_LISTENER_OBSERVED")
                self.assertEqual(result["ports"][str(port)]["docker_tcp_publish"],
                                 "NO_PUBLISH_OBSERVED")
        self.assertIs(result["staging_deployment_authorized"], False)
        self.assertIs(result["production_deployment_authorized"], False)
        self.assertIs(result["host_identity_verified"], False)
        self.assertIs(result["dns_tls_keycloak_database_flyway_verified"], False)
        self.assertEqual(result["new_stage_ready"], "NOT_ESTABLISHED")

    def test_real_ipv4_or_ipv6_listener_detected_for_all_known_ports(self):
        for port in h.PORTS:
            for family in ("proc4", "proc6"):
                with self.subTest(port=port, family=family):
                    result = snapshot(**{family: tcp(port)})
                    self.assertEqual(result["ports"][str(port)]["host_tcp"],
                                     "LISTENER_OBSERVED")

    def test_docker_publish_detects_nat_without_host_proxy(self):
        for port in h.PORTS:
            for published in (
                f"127.0.0.1:{port}->8080/tcp",
                f"0.0.0.0:{port}->8080/tcp, :::{port}->8080/tcp",
                f"[::]:{port}->8080/tcp",
            ):
                with self.subTest(port=port, published=published):
                    result = snapshot(published={published})
                    self.assertEqual(result["ports"][str(port)]["docker_tcp_publish"],
                                     "PUBLISHED_TCP_OBSERVED")
                    self.assertEqual(result["ports"][str(port)]["host_tcp"],
                                     "NO_LISTENER_OBSERVED")

    def test_non_listener_and_unpublished_ports_are_not_claimed_used(self):
        result = snapshot(proc4=tcp(18082, "01"),
                          published={"8080/tcp", "127.0.0.1:18088->8080/tcp"})
        self.assertEqual(result["ports"]["18082"]["host_tcp"], "NO_LISTENER_OBSERVED")
        self.assertEqual(result["ports"]["18083"]["docker_tcp_publish"],
                         "NO_PUBLISH_OBSERVED")

    def test_missing_or_bad_proc_is_unknown_not_free(self):
        for value in (None, "", "broken header", HEADER + "\ninvalid"):
            with self.subTest(value=value):
                result = snapshot(proc4=value)
                self.assertTrue(all(
                    x["host_tcp"] == "UNKNOWN" for x in result["ports"].values()
                ))

    def test_failed_docker_permissions_are_unknown_not_free(self):
        result = snapshot(containers=None, published=None, volumes=None, networks=None)
        self.assertTrue(all(
            value == "UNKNOWN_QUERY" for group in result["project_name_hints"].values()
            for value in group.values()
        ))
        self.assertEqual(result["ports"]["18082"]["docker_tcp_publish"],
                         "UNKNOWN_QUERY")
        self.assertIs(result["staging_deployment_authorized"], False)

    def test_detect_project_hints_and_never_output_unrelated_names_or_secrets(self):
        result = snapshot(
            containers={"prp-mcp-v2-gateway-1", "unrelated_SECRET_KEY=abc123"},
            volumes={"prp-mcp-newdb-review_data", "SECRET_DB_PASSWORD=foo"},
            networks={"prp-mcp-stage_default", "PRIVATE_NW"},
            published={"DOCKER_SECRET_X=yyy"},
        )
        p = result["project_name_hints"]
        self.assertEqual(p["v2_18082_name_hint"]["containers"], "NAME_MATCH_OBSERVED")
        self.assertEqual(p["newdb_18083_name_hint"]["volumes"], "NAME_MATCH_OBSERVED")
        self.assertEqual(p["legacy_18081_name_hint"]["networks"], "NAME_MATCH_OBSERVED")
        payload = json.dumps(result)
        for forbidden in ("abc123", "SECRET_KEY", "SECRET_DB", "PRIVATE_NW", "DOCKER_SECRET"):
            self.assertNotIn(forbidden, payload)

    def test_capacity_thresholds_are_not_approval(self):
        self.assertEqual(snapshot(free_memory=1)["capacity"]["available_memory_2gib"],
                         "BELOW_REVIEW_THRESHOLD")
        self.assertEqual(snapshot(free_disk=None)["capacity"]["root_free_disk_25gib"],
                         "UNKNOWN")
        self.assertFalse(snapshot()["staging_deployment_authorized"])

    @patch.object(h.subprocess, "run")
    def test_only_fixed_docker_list_queries(self, call):
        call.return_value.returncode = 0
        call.return_value.stdout = b"prp-mcp-v2-gateway-1\n"
        self.assertEqual(h.docker_lines("containers"), {"prp-mcp-v2-gateway-1"})
        self.assertEqual(call.call_args.args[0], h.DOCKER_COMMANDS["containers"])
        self.assertNotIn("shell", call.call_args.kwargs)
        self.assertEqual(call.call_args.kwargs["timeout"], 12)
        self.assertEqual(call.call_args.kwargs["env"], h.SAFE_ENV)
        for command in h.DOCKER_COMMANDS.values():
            for forbidden in ("inspect", "exec", "run", "up", "down", "start",
                              "stop", "rm", "prune", "cp"):
                self.assertNotIn(forbidden, command)

    @patch.object(h.subprocess, "run")
    def test_oversize_or_failed_docker_is_unknown(self, call):
        call.return_value.returncode = 0
        call.return_value.stdout = b"x" * (h.MAX_DOCKER_STDOUT + 1)
        self.assertIsNone(h.docker_lines("containers"))
        call.return_value.returncode = 1
        self.assertIsNone(h.docker_lines("containers"))

    def test_meminfo_parser_is_bounded_and_uses_available_not_total(self):
        with patch.object(h, "read_proc", return_value="MemTotal: 99999999 kB\nMemAvailable: 1024 kB\n"):
            self.assertEqual(h.available_memory(), 1024 * 1024)
        with patch.object(h, "read_proc", return_value="MemTotal: 999 kB"):
            self.assertIsNone(h.available_memory())

    def test_source_has_no_install_or_secret_reading_interface(self):
        src = (Path(__file__).parent / "unified_staging_inventory_readonly.py").read_text()
        self.assertNotIn("shell=True", src)
        self.assertNotIn("docker inspect", src)
        self.assertNotIn("os.system(", src)
        self.assertNotIn("Popen(", src)
        self.assertNotIn("write_text(", src)
        self.assertNotIn("requests.", src)


if __name__ == "__main__":
    unittest.main()
