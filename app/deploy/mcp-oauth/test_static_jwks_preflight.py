#!/usr/bin/env python3
"""Pure-stdlib, no-network contract checks for the static-JWKS probe.

Run: python3 -m unittest app/deploy/mcp-oauth/test_static_jwks_preflight.py
This does not execute Keycloak, authenticate clients, or approve deployment.
"""
import ast
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).with_name("ci_static_jwks_client_jwt.py")


class StaticJwksPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(SCRIPT))

    def test_syntax(self):
        self.assertIsInstance(self.tree, ast.Module)

    def test_ci_only_guard_present(self):
        self.assertIn('GITHUB_ACTIONS', self.source)

    def test_loopback_guard_present(self):
        self.assertIn('127.0.0.1', self.source)
        self.assertIn('localhost', self.source)

    def test_no_official_chatgpt_client_identity(self):
        self.assertNotIn('https://chatgpt.com/oauth/client.json', self.source)

    def test_no_live_prp_endpoint(self):
        self.assertNotIn('prp-test.micor.top', self.source)
        self.assertNotIn('auth-test.micor.top', self.source)

    def test_static_jwks_attributes_present(self):
        for attr in ('use.jwks.string', 'jwks.string', 'use.jwks.url'):
            self.assertIn(attr, self.source)

    def test_positive_and_negative_probes_present(self):
        for label in ('VALID_STATIC_JWKS', 'WRONG_SIGNATURE', 'WRONG_KID',
                      'WRONG_AUDIENCE', 'EXPIRED_ASSERTION'):
            self.assertIn(label, self.source)

    def test_disposable_identity_guard_required(self):
        self.assertIn('TEST_KEYCLOAK_CONTAINER', self.source)


if __name__ == "__main__":
    unittest.main()
