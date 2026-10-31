"""Negative review tests on resolved Compose, without starting Docker services."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_newdb_review import validate, NAME, PROFILE
from prepare_env import make_config, write_secrets_file


class NewDatabaseComposeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent
        cls.env = make_config("prp-test.micor.top", "auth-test.micor.top", "stage_admin")
        with tempfile.TemporaryDirectory(prefix="prp-newdb-test-") as tmp:
            file = Path(tmp) / ".env"
            write_secrets_file(file, cls.env)
            command = ["docker", "compose", "--profile", PROFILE,
                       "--env-file", str(file),
                       "-f", str(cls.root / "compose.newdb.review.yaml"),
                       "config", "--format", "json"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=35)
            if result.returncode:
                raise AssertionError("REVIEW_COMPOSE_CONFIG_RENDER_FAILED")
            cls.rendered = json.loads(result.stdout)

    def test_real_resolved_review_candidate_isolated_and_disabled(self):
        self.assertTrue(validate(self.rendered, self.env))
        self.assertEqual(self.rendered["name"], NAME)

    def test_no_automatic_services_without_the_named_review_profile(self):
        with tempfile.TemporaryDirectory(prefix="prp-newdb-no-profile-") as tmp:
            private_env = Path(tmp) / ".env"
            write_secrets_file(private_env, self.env)
            result = subprocess.run(
                ["docker", "compose", "--env-file", str(private_env),
                 "-f", str(self.root / "compose.newdb.review.yaml"),
                 "config", "--services"],
                capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, "NO_PROFILE_CONFIG_FAILED")
            self.assertEqual(result.stdout.strip(), "", "PROFILE_NOT_OPT_IN")

    def test_reject_old_port_volume_schema_and_unreviewed_service(self):
        cases = {
            "legacy_port": lambda d: d["services"]["gateway"]["ports"][0].update(
                {"published": "18081"}),
            "v2_port": lambda d: d["services"]["gateway"]["ports"][0].update(
                {"published": "18082"}),
            "public_bind": lambda d: d["services"]["gateway"]["ports"][0].update(
                {"host_ip": "0.0.0.0"}),
            "old_volume": lambda d: d["services"]["mysql"]["volumes"][0].update(
                {"source": "stage_mysql"}),
            "production_schema": lambda d: d["services"]["mysql"]["environment"].update(
                {"MYSQL_DATABASE": "matrix_prp"}),
            "old_schema": lambda d: d["services"]["backend"]["environment"].update(
                {"MATRIX_PRP_DB_URL": "jdbc:mysql://mysql:3306/matrix_prp_mcp_stage"}),
            "unreviewed_service": lambda d: d["services"].update(
                {"production_service": {}}),
            "removed_profile": lambda d: d["services"]["backend"].pop("profiles"),
            "write_enabled": lambda d: d["services"]["backend"]["environment"].update(
                {"MATRIX_PRP_MCP_WRITE_ENABLED": "true"}),
            "first_party_enabled": lambda d: d["services"]["backend"]["environment"].update(
                {"MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED": "true"}),
            "oauth_enabled": lambda d: d["services"]["backend"]["environment"].update(
                {"MATRIX_PRP_MCP_OAUTH_ENABLED": "true"}),
            "host_network": lambda d: d["services"]["backend"].update(
                {"network_mode": "host"}),
            "db_published": lambda d: d["services"]["mysql"].update(
                {"ports": [{"published": "3306", "target": 3306}]}),
            "external_net": lambda d: d["networks"]["newdb_private"].update(
                {"external": True}),
            "foreign_project": lambda d: d.update({"name": "prp-mcp-stage"}),
            "foreign_db_image": lambda d: d["services"]["mysql"].update(
                {"image": "mysql:latest"}),
        }
        for label, modify in cases.items():
            with self.subTest(label=label):
                altered = deepcopy(self.rendered)
                modify(altered)
                with self.assertRaises(AssertionError):
                    validate(altered, self.env)

    def test_public_hostname_cannot_be_production(self):
        invalid = self.env.copy()
        invalid["PRP_STAGE_PUBLIC_HOST"] = "micor.top"
        with self.assertRaises(ValueError):
            validate(self.rendered, invalid)


if __name__ == "__main__":
    unittest.main()
