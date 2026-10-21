import os
from pathlib import Path
import tempfile
import unittest
from check_env import check, parse_env
from prepare_env import make_config, write_secrets_file


class StagingIsolationTests(unittest.TestCase):
    def setUp(self):
        self.values = make_config("prp-test.micor.top", "auth-test.micor.top", "stage_admin")

    def test_generated_env_has_unique_secrets_and_all_flags_disabled(self):
        result = check(self.values)
        self.assertEqual(result["stage_host"], "prp-test.micor.top")
        self.assertFalse(result["mcp_enabled"])
        self.assertFalse(result["oauth_enabled"])
        self.assertNotEqual(self.values["PRP_STAGE_DB_ROOT_PASSWORD"],
                            self.values["PRP_STAGE_DB_PASSWORD"])
        self.assertNotEqual(self.values["PRP_STAGE_DB_PASSWORD"],
                            self.values["PRP_STAGE_ADMIN_PASSWORD"])

    def test_fails_closed_on_real_production_host(self):
        self.values["PRP_STAGE_PUBLIC_HOST"] = "micor.top"
        self.values["PRP_STAGE_PUBLIC_URL"] = "https://micor.top"
        self.values["PRP_STAGE_MCP_RESOURCE"] = "https://micor.top/api/mcp"
        with self.assertRaisesRegex(ValueError, "non-production"):
            check(self.values)

    def test_fails_when_mcp_enabled_without_oauth(self):
        self.values["PRP_STAGE_MCP_ENABLED"] = "true"
        with self.assertRaisesRegex(ValueError, "without OAuth"):
            check(self.values)

    def test_fails_if_stage_reuses_public_host_for_issuer(self):
        self.values["PRP_STAGE_AUTH_PUBLIC_URL"] = self.values["PRP_STAGE_PUBLIC_URL"]
        self.values["PRP_STAGE_AUTH_ISSUER"] = self.values["PRP_STAGE_PUBLIC_URL"] + "/realms/prp-mcp"
        self.values["PRP_STAGE_AUTH_JWKS_URI"] = (
            self.values["PRP_STAGE_PUBLIC_URL"] + "/realms/prp-mcp/protocol/openid-connect/certs")
        with self.assertRaisesRegex(ValueError, "separate"):
            check(self.values)

    def test_secrets_are_exclusive_mode_600_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / ".env"
            write_secrets_file(output, self.values)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(check(parse_env(output.read_text()))["stage_host"], "prp-test.micor.top")
            with self.assertRaises(FileExistsError):
                write_secrets_file(output, make_config(
                    "prp-test.micor.top", "auth-test.micor.top", "stage_admin"))

    def test_template_and_compose_do_not_reference_production_database(self):
        root = Path(__file__).resolve().parent
        compose = (root / "compose.yaml").read_text()
        self.assertIn("matrix_prp_mcp_stage", compose)
        self.assertIn("127.0.0.1:18081:8080", compose)
        self.assertIn("stage_mysql:/var/lib/mysql", compose)
        self.assertIn("MATRIX_PRP_MCP_WRITE_ENABLED: \"false\"", compose)
        self.assertNotIn("container_name: matrix-mysql", compose)
        self.assertNotIn("127.0.0.1:11000", compose)
        self.assertNotIn("/var/lib/mysql:/var/lib/mysql", compose)
        self.assertNotIn("network_mode: host", compose)


if __name__ == "__main__":
    unittest.main()
