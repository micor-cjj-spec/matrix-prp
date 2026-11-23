"""Pure synthetic tests for an uninstalled, isolated full-app stage proposal."""
from pathlib import Path
import unittest
from unittest.mock import patch
import check_env as v

ROOT = Path(__file__).resolve().parent


def sample():
    return {
        "PRP_UNIFIED_PUBLIC_HOST": "prp-unified.example.org",
        "PRP_UNIFIED_PUBLIC_URL": "https://prp-unified.example.org",
        "PRP_UNIFIED_AUTH_ISSUER": "https://auth-unified.example.org/realms/prp-unified",
        "PRP_UNIFIED_LOOPBACK_PORT": "23080",
        "PRP_UNIFIED_DB_ROOT_PASSWORD": "0123456789abcdef" * 4,
        "PRP_UNIFIED_DB_PASSWORD": "fedcba9876543210" * 4,
        "PRP_UNIFIED_JWT_SECRET": "00112233445566778899aabbccddeeff" * 2,
        "PRP_UNIFIED_BOOTSTRAP_USERNAME": "synthetic_stage_owner",
        "PRP_UNIFIED_BOOTSTRAP_PASSWORD": "ffeeddccbbaa99887766554433221100" * 2,
    }


class UnifiedStageReviewTests(unittest.TestCase):
    def test_valid_static_fixture_is_never_deployment_approval(self):
        result = v.check(sample())
        self.assertEqual(result["config_shape"], "VALID_FOR_STATIC_REVIEW_ONLY")
        self.assertFalse(result["deployment_permitted"])
        self.assertFalse(result["dns_tls_validated"])
        self.assertFalse(result["runtime_resource_collision_checked"])

    def test_env_parser_does_not_allow_extra_unknown_or_duplicate_keys(self):
        text = "\n".join(f"{k}={val}" for k, val in sample().items()) + "\n"
        self.assertEqual(v.parse_env(text), sample())
        with self.assertRaises(ValueError):
            v.parse_env(text + "PRP_UNIFIED_DB_PASSWORD=foo\n")
        with self.assertRaises(ValueError):
            v.check(dict(sample(), PRODUCTION_MYSQL_PASSWORD="wrong"))
        with self.assertRaises(ValueError):
            v.parse_env(text + "BAD_KEY=word with spaces\n")

    def test_production_and_existing_stage_hostnames_rejected(self):
        for host in ("micor.top", "www.micor.top", "auth.micor.top",
                     "prp-test.micor.top", "auth-test.micor.top",
                     "prp.micor.top", "127.0.0.1", "www.localhost",
                     "host;bad.example.org"):
            with self.subTest(host=host):
                changed = sample()
                changed["PRP_UNIFIED_PUBLIC_HOST"] = host
                changed["PRP_UNIFIED_PUBLIC_URL"] = "https://" + host
                with self.assertRaises(ValueError):
                    v.check(changed)

    def test_protected_ports_and_invalid_ranges_rejected(self):
        for port in ("11000", "18081", "18082", "18083", "65535", "80",
                     "-1", "bad", "01000"):
            with self.subTest(port=port):
                changed = sample()
                changed["PRP_UNIFIED_LOOPBACK_PORT"] = port
                with self.assertRaises(ValueError):
                    v.check(changed)

    def test_issuer_must_be_exact_distinct_stage_only_url(self):
        for issuer in (
            "https://prp-unified.example.org/realms/prp-unified",
            "https://auth-test.micor.top/realms/prp-unified",
            "https://auth.micor.top/realms/prp-unified",
            "http://auth-unified.example.org/realms/prp-unified",
            "https://auth-unified.example.org/realms/master",
            "https://auth-unified.example.org:443/realms/prp-unified",
            "https://auth-unified.example.org/realms/prp-unified?x=1",
        ):
            with self.subTest(issuer=issuer):
                changed = sample()
                changed["PRP_UNIFIED_AUTH_ISSUER"] = issuer
                with self.assertRaises(ValueError):
                    v.check(changed)

    def test_secrets_are_distinct_and_not_placeholders(self):
        for value in ("REPLACE_ME", "a" * 64, "00" * 32, "A" * 64):
            with self.subTest(value=value[:6]):
                changed = sample()
                changed["PRP_UNIFIED_JWT_SECRET"] = value
                with self.assertRaises(ValueError):
                    v.check(changed)
        changed = sample()
        changed["PRP_UNIFIED_JWT_SECRET"] = changed["PRP_UNIFIED_DB_PASSWORD"]
        with self.assertRaises(ValueError):
            v.check(changed)

    def test_no_generic_or_privileged_bootstrap_identity(self):
        for name in ("root", "admin", "matrix_prp", "cosmic", "a",
                     "owner;cmd", "OWNER"):
            with self.subTest(name=name):
                changed = sample()
                changed["PRP_UNIFIED_BOOTSTRAP_USERNAME"] = name
                with self.assertRaises(ValueError):
                    v.check(changed)

    def test_review_compose_keeps_three_services_profile_gated(self):
        src = (ROOT / "compose.review.yaml").read_text()
        self.assertEqual(src.count('profiles: ["unified-review"]'), 3)
        self.assertIn("name: prp-unified-stage-review", src)
        self.assertIn("matrix_prp_unified_stage", src)
        self.assertIn('internal: true', src)
        self.assertEqual(src.count('networks: [unified_private]'), 2)
        self.assertEqual(src.count('networks: [unified_private, unified_ingress]'), 1)
        self.assertIn("127.0.0.1:${PRP_UNIFIED_LOOPBACK_PORT", src)
        self.assertIn('MATRIX_PRP_MCP_ENABLED: "false"', src)
        self.assertIn('MATRIX_PRP_MCP_OAUTH_ENABLED: "false"', src)
        self.assertIn('MATRIX_PRP_MCP_WRITE_ENABLED: "false"', src)
        self.assertIn('MATRIX_PRP_AI_SPRING_AI_ENABLED: "false"', src)
        self.assertIn('MATRIX_PRP_FLYWAY_ENABLED: "true"', src)
        for forbidden in ("127.0.0.1:18081:", "127.0.0.1:18082:",
                          "127.0.0.1:18083:", "127.0.0.1:11000:",
                          "/var/lib/matrix-prp", "matrix-mysql", "prp-mcp-v2-gateway"):
            self.assertNotIn(forbidden, src)
        self.assertIn("nginx.conf.template:/etc/nginx/templates/default.conf.template:ro", src)

    def test_gateway_mcp_is_deny_by_default(self):
        src = (ROOT / "nginx.conf.template").read_text()
        self.assertIn("location ^~ /api/mcp { return 404; }", src)
        self.assertIn("location ^~ /.well-known/ { return 404; }", src)
        self.assertIn("location ^~ /api/ {", src)
        self.assertIn("location ^~ /prp/ {", src)
        self.assertIn("if ($host != ${PRP_STAGE_HOST}) { return 421; }", src)

    def test_example_cannot_validate_without_operator_decisions(self):
        source = (ROOT / ".env.example").read_text()
        self.assertIn("REPLACE_WITH", source)
        with self.assertRaises(ValueError):
            v.check(v.parse_env(source))

    def test_no_live_production_mutation_in_validator(self):
        src = (ROOT / "check_env.py").read_text()
        for forbidden in ("subprocess", "paramiko", "requests.", "urllib.request",
                          "docker compose up", "shell=True", "os.system("):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
