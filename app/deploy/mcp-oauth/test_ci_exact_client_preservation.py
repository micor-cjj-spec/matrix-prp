"""Offline contract for disposable 13-legacy-client preserve/add/rollback CI."""
from unittest import TestCase, mock
import os
from pathlib import Path
import subprocess

import ci_exact_client_preservation as stage
from review_exact_client_registrations import CHATGPT, FIRST_PARTY


class CIExactClientPreservationContract(TestCase):
    def test_requires_disposable_runner_and_explicit_opt_in(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "REFUSED_NON_DISPOSABLE"):
                stage.require_disposable()
        for missing in ("GITHUB_ACTIONS", "CI_EXACT_CLIENT_PRESERVE",
                        "RUNNER_TEMP", "MCP_TEST_ADMIN_PASSWORD"):
            valid = {
                "GITHUB_ACTIONS": "true",
                "CI_EXACT_CLIENT_PRESERVE": "1",
                "RUNNER_TEMP": "/tmp/throwaway-test-only",
                "MCP_TEST_ADMIN_PASSWORD": "c" * 32,
            }
            valid.pop(missing)
            with self.subTest(missing=missing), mock.patch.dict(os.environ, valid, clear=True):
                with self.assertRaisesRegex(RuntimeError, "REFUSED_NON_DISPOSABLE"):
                    stage.require_disposable()

    def test_source_never_allows_active_keycloak_url_or_admin_secret_output(self):
        source = Path(stage.__file__).read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:18080", source)
        self.assertIn("CI_EXACT_CLIENT_PRESERVE", source)
        self.assertIn("NOT A BACKUP RESTORE", source)
        self.assertIn("original clients and policies unchanged", source)
        self.assertNotIn("https://auth-test.micor.top", source)
        self.assertNotIn("prp-mcp-oauth-stage-keycloak-1", source)
        self.assertNotIn("docker exec", source)
        self.assertNotIn("kcadm", source)
        self.assertNotIn("print(token", source)
        self.assertNotIn("print(client", source)
        self.assertEqual(stage.LEGACY_COUNT, 13)

    def test_disabled_legacy_fixture_and_validated_exact_clients(self):
        f = stage.fixture("ci-synthetic-only")
        for prop in ("enabled", "standardFlowEnabled", "implicitFlowEnabled",
                     "directAccessGrantsEnabled", "serviceAccountsEnabled",
                     "fullScopeAllowed"):
            self.assertIs(f[prop], False)
        self.assertEqual(f["optionalClientScopes"], [])
        self.assertEqual(f["redirectUris"], [])
        proposal = stage.client_proposals()
        self.assertTrue(stage.validate_proposals(proposal))
        self.assertEqual({x["clientId"] for x in proposal}, {CHATGPT, FIRST_PARTY})

    def test_cannot_read_arbitrary_admin_urls(self):
        for bad in ("https://external.example", "clients", "//clients",
                    "/clients//other"):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                stage.endpoint(bad)

    def test_module_is_syntax_valid(self):
        subprocess.run(["python3", "-c",
                        "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())",
                        str(Path(stage.__file__))], check=True)


if __name__ == "__main__":
    import unittest
    unittest.main()
