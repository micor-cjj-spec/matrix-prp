"""Offline S0 report validator regression tests; no Docker or real host."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import unified_staging_inventory_readonly as inventory
import unified_staging_s0_report_review as review

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)


def sample():
    empty = " sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
    return inventory.analyze(
        proc4=empty, proc6=empty, containers=set(), published=set(),
        volumes=set(), networks=set(), free_memory=4 * 1024 ** 3,
        free_disk=30 * 1024 ** 3,
        observed_utc=(NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
    )


class OfflineS0ReviewTests(unittest.TestCase):
    def check(self, doc):
        return review.assess(doc, now=NOW)

    def test_nominal_report_is_format_valid_but_always_non_authorizing(self):
        result = self.check(sample())
        self.assertEqual(result["s0_report_format"], "VALID")
        self.assertFalse(result["stage_deployment_authorized"])
        self.assertFalse(result["production_deployment_authorized"])
        self.assertEqual(result["stage_readiness"], "NOT_ESTABLISHED")
        self.assertEqual(result["operator_host_identity_confirmation"], "REQUIRED")

    def test_unknown_docker_and_memory_are_valid_observations_not_free_ports(self):
        doc = sample()
        doc["project_name_hints"]["production_name_hint"]["containers"] = "UNKNOWN_QUERY"
        doc["capacity"]["available_memory_2gib"] = "UNKNOWN"
        self.assertEqual(self.check(doc)["s0_report_format"], "VALID")
        self.assertFalse(self.check(doc)["stage_deployment_authorized"])

    def test_extra_raw_metadata_or_secrets_never_echoed(self):
        doc = sample()
        doc["PRIVATE_PASSWORD"] = "abc123"
        result = self.check(doc)
        self.assertEqual(result["s0_report_format"], "REJECTED")
        self.assertIn("TOP_LEVEL_SCHEMA_MISMATCH", result["reason_codes"])
        self.assertNotIn("abc123", json.dumps(result))

    def test_forged_readiness_and_approvals_rejected(self):
        for key, value in (
            ("host_identity_verified", True),
            ("staging_deployment_authorized", True),
            ("production_deployment_authorized", True),
            ("new_stage_ready", "VERIFIED"),
            ("absence_is_not_availability_proof", False),
        ):
            with self.subTest(key=key):
                doc = sample()
                doc[key] = value
                self.assertEqual(self.check(doc)["s0_report_format"], "REJECTED")

    def test_fake_free_port_claim_and_wrong_nested_type_rejected(self):
        for state in ("FREE", 42, ["NO_LISTENER_OBSERVED"]):
            with self.subTest(state=state):
                doc = sample()
                doc["ports"]["18083"]["host_tcp"] = state
                self.assertIn("PORT_STATE_INVALID", self.check(doc)["reason_codes"])

    def test_bad_project_and_resource_states_rejected(self):
        doc = sample()
        doc["project_name_hints"]["newdb_18083_name_hint"]["containers"] = {"secrets": 1}
        doc["capacity"]["root_free_disk_25gib"] = 2000
        problems = self.check(doc)["reason_codes"]
        self.assertIn("PROJECT_HINT_STATE_INVALID", problems)
        self.assertIn("CAPACITY_STATE_INVALID", problems)

    def test_invalid_timestamp_future_and_stale_rejected(self):
        for date, reason in (
            ("bad-date", "TIMESTAMP_INVALID"),
            ((NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z"), "TIMESTAMP_FUTURE"),
            ((NOW - timedelta(days=3)).isoformat().replace("+00:00", "Z"), "REPORT_OLDER_THAN_24H"),
        ):
            with self.subTest(date=date):
                doc = sample()
                doc["observed_utc"] = date
                self.assertIn(reason, self.check(doc)["reason_codes"])

    def test_duplicate_keys_fail_closed(self):
        with self.assertRaises(ValueError):
            json.loads('{"same": 1, "same": 2}', object_pairs_hook=review.unique_pairs)

    def test_symlink_report_rejected_without_raw_output(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            report.write_text(json.dumps(sample()), encoding="utf-8")
            link = Path(folder) / "symlink.json"
            link.symlink_to(report)
            with patch("sys.argv", ["review", str(link)]), patch("builtins.print") as out:
                self.assertEqual(review.main(), 2)
                self.assertNotIn("observed_utc", out.call_args.args[0])

    def test_no_network_or_host_execution_in_review_source(self):
        text = (Path(__file__).parent / "unified_staging_s0_report_review.py").read_text()
        for forbidden in ("subprocess", "os.system", "socket.", "urlopen(", "write_text(", "write_bytes("):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
