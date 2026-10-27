import os
from pathlib import Path
import tempfile
import unittest
from check_env import check, parse_env
from prepare_env import make_config, write_secrets_file


class StagingIsolationTests(unittest.TestCase):
    def test_build_context_excludes_nested_credentials(self):
        repo = Path(__file__).resolve().parents[3]
        patterns = set((repo / ".dockerignore").read_text().splitlines())
        for required in (".git", "**/.env", "**/.env.*", "**/.generated", "**/*.pem", "**/*.key"):
            self.assertIn(required, patterns)
        dockerfile = (Path(__file__).parent / "Dockerfile.web").read_text()
        self.assertIn("RUN test ! -e /repo/app/deploy/mcp-staging/.env", dockerfile)

    def test_staging_web_api_base_matches_gateway_routes(self):
        root = Path(__file__).parent
        dockerfile = (root / "Dockerfile.web").read_text()
        nginx = (root / "nginx.conf.template").read_text()
        self.assertIn("ENV VITE_API_BASE=/api", dockerfile)
        self.assertIn("location ^~ /api/ {", nginx)
        self.assertIn("location ^~ /prp/api/ { return 404; }", nginx)

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

    def test_first_party_pkce_remains_disabled_and_pinned_to_stage_host(self):
        self.assertEqual(self.values["PRP_STAGE_FIRST_PARTY_LINK_ENABLED"], "false")
        self.assertEqual(self.values["PRP_STAGE_FIRST_PARTY_CLIENT_ID"], "prp-first-party-link")
        self.assertEqual(self.values["PRP_STAGE_FIRST_PARTY_REDIRECT_URI"],
                         "https://prp-test.micor.top/prp/me/mcp-link/callback")
        self.assertFalse(check(self.values)["first_party_enabled"])
        from pathlib import Path
        root = Path(__file__).parent
        compose = (root / "compose.yaml").read_text()
        dockerfile = (root / "Dockerfile.web").read_text()
        self.assertIn("MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED:", compose)
        self.assertIn("MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_CLIENT_ID:", compose)
        self.assertIn("MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_REDIRECT_URI:", compose)
        self.assertIn("VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT:", compose)
        self.assertIn("${PRP_STAGE_AUTH_ISSUER:?}/protocol/openid-connect/auth", compose)
        self.assertIn("ARG VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT", dockerfile)

    def test_first_party_fails_closed_without_mcp_and_independent_client_review(self):
        self.values["PRP_STAGE_FIRST_PARTY_LINK_ENABLED"] = "true"
        with self.assertRaisesRegex(ValueError, "requires MCP and OAuth"):
            check(self.values)
        self.values["PRP_STAGE_MCP_ENABLED"] = "true"
        self.values["PRP_STAGE_OAUTH_ENABLED"] = "true"
        self.assertTrue(check(self.values)["first_party_enabled"])
        for key, bad in (
            ("PRP_STAGE_FIRST_PARTY_LINK_ENABLED", "yes"),
            ("PRP_STAGE_FIRST_PARTY_CLIENT_ID", "https://chatgpt.com/oauth/client.json"),
            ("PRP_STAGE_FIRST_PARTY_REDIRECT_URI",
             "https://micor.top/prp/me/mcp-link/callback"),
            ("PRP_STAGE_FIRST_PARTY_REDIRECT_URI",
             "https://prp-test.micor.top/prp/me/mcp-link/callback?code=bad"),
            ("PRP_STAGE_FIRST_PARTY_REDIRECT_URI",
             "https://auth-test.micor.top/prp/me/mcp-link/callback"),
        ):
            with self.subTest(setting=key, rejected=bad):
                candidate = self.values.copy()
                candidate[key] = bad
                with self.assertRaises(ValueError):
                    check(candidate)
        for missing in ("PRP_STAGE_FIRST_PARTY_CLIENT_ID",
                        "PRP_STAGE_FIRST_PARTY_REDIRECT_URI"):
            with self.subTest(missing=missing):
                candidate = self.values.copy()
                candidate.pop(missing)
                with self.assertRaisesRegex(ValueError, "required"):
                    check(candidate)

    def test_legacy_staging_config_can_stay_off_without_new_settings(self):
        for key in ("PRP_STAGE_FIRST_PARTY_LINK_ENABLED",
                    "PRP_STAGE_FIRST_PARTY_CLIENT_ID",
                    "PRP_STAGE_FIRST_PARTY_REDIRECT_URI"):
            self.values.pop(key, None)
        self.assertFalse(check(self.values)["first_party_enabled"])

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

    def test_rendered_compose_rejects_second_public_port_and_internal_exposure(self):
        # Pure in-memory regression: never start Docker or open staging secrets.
        from copy import deepcopy
        from check_rendered_compose import validate

        settings = self.values
        compose = {
            "services": {
                "mysql": {},
                "backend": {"environment": {
                    "MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED": "false",
                    "MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_CLIENT_ID":
                        settings["PRP_STAGE_FIRST_PARTY_CLIENT_ID"],
                    "MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_REDIRECT_URI":
                        settings["PRP_STAGE_FIRST_PARTY_REDIRECT_URI"],
                    "MATRIX_PRP_MCP_WRITE_ENABLED": "false",
                }},
                "gateway": {
                    "build": {"args": {
                        "VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT":
                            settings["PRP_STAGE_AUTH_ISSUER"] +
                            "/protocol/openid-connect/auth",
                    }},
                    "ports": [{
                        "published": "18081", "target": 8080,
                        "host_ip": "127.0.0.1",
                    }],
                },
            },
        }
        validate(compose, settings)

        mutations = {
            "second_public_gateway_port": lambda d: d["services"]["gateway"]["ports"].append(
                {"published": "18083", "target": 8080, "host_ip": "0.0.0.0"}),
            "second_loopback_gateway_port": lambda d: d["services"]["gateway"]["ports"].append(
                {"published": "18083", "target": 8080, "host_ip": "127.0.0.1"}),
            "backend_public_port": lambda d: d["services"]["backend"].update(
                {"ports": [{"published": "18084", "target": 8080, "host_ip": "0.0.0.0"}]}),
            "mysql_public_port": lambda d: d["services"]["mysql"].update(
                {"ports": [{"published": "3306", "target": 3306, "host_ip": "0.0.0.0"}]}),
            "host_network": lambda d: d["services"]["backend"].update(
                {"network_mode": "host"}),
            "unreviewed_service": lambda d: d["services"].update(
                {"additional": {"ports": [{"published": "80", "host_ip": "0.0.0.0"}]}}),
            "wrong_gateway_target": lambda d: d["services"]["gateway"]["ports"][0].update(
                {"target": 8081}),
        }
        for name, mutate in mutations.items():
            with self.subTest(case=name):
                altered = deepcopy(compose)
                mutate(altered)
                with self.assertRaises(AssertionError):
                    validate(altered, settings)

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
