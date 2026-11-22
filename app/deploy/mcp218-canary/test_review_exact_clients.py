"""#218 synthetic validation for review-only exact-client proposals. No installs."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from review_exact_clients import (
    CHATGPT_ID, CHATGPT_REDIRECT, CHATGPT_JWKS, FIRST_PARTY_ID,
    client_proposals, review_package, validate_proposals,
)

RESOURCE = "https://mcp218-ci-contract.micor.top/api/mcp"
ISSUER = "https://auth-mcp218-ci-contract.micor.top/realms/prp-mcp218"


class ReviewOnlyExactClientTests(unittest.TestCase):
    def setUp(self):
        self.candidates = client_proposals(RESOURCE, ISSUER)
        self.first, self.chatgpt = self.candidates

    def test_two_exact_clients_separate_from_single_resource_client(self):
        self.assertTrue(validate_proposals(self.candidates, RESOURCE, ISSUER))
        self.assertEqual([c["clientId"] for c in self.candidates],
                         [FIRST_PARTY_ID, CHATGPT_ID])
        self.assertNotIn("matrix-prp-mcp218-resource",
                         [c["clientId"] for c in self.candidates])

    def test_chatgpt_exact_public_metadata_key_and_audience(self):
        c = self.chatgpt
        self.assertEqual(c["clientId"], CHATGPT_ID)
        self.assertEqual(c["redirectUris"], [CHATGPT_REDIRECT])
        self.assertEqual(c["clientAuthenticatorType"], "client-jwt")
        self.assertFalse(c["publicClient"])
        self.assertEqual(c["attributes"], {
            "pkce.code.challenge.method": "S256",
            "use.jwks.url": "true",
            "jwks.url": CHATGPT_JWKS,
        })
        self.assertEqual(c["protocolMappers"][0]["config"]
                         ["included.custom.audience"], RESOURCE)
        self.assertEqual(c["optionalClientScopes"],
                         ["prp.reviews.read", "prp.video.read"])

    def test_first_party_client_id_matches_pinned_prp_frontend(self):
        # Independent Realm, same approved identifier: never alter the
        # frontend's fail-closed client-id check to accommodate a proposal.
        from pathlib import Path
        frontend = (Path(__file__).resolve().parents[2] / "web" / "src"
                    / "utils" / "mcpOidcAuthorizeUrl.ts").read_text(encoding="utf-8")
        self.assertEqual(FIRST_PARTY_ID, "prp-first-party-link")
        self.assertIn("params.get('client_id') !== 'prp-first-party-link'", frontend)
        self.assertEqual(self.first["clientId"], FIRST_PARTY_ID)
        self.assertNotEqual(self.first["clientId"], CHATGPT_ID)
        self.assertEqual(self.first["redirectUris"], [
            "https://mcp218-ci-contract.micor.top/prp/me/mcp-link/callback"
        ])
        self.assertTrue(self.first["publicClient"])

    def test_first_party_exact_isolated_callback_no_data_scopes(self):
        self.assertTrue(self.first["publicClient"])
        self.assertEqual(self.first["redirectUris"],
            ["https://mcp218-ci-contract.micor.top/prp/me/mcp-link/callback"])
        self.assertEqual(self.first["clientId"], FIRST_PARTY_ID)
        self.assertEqual(self.first["optionalClientScopes"], [])
        self.assertEqual(self.first["attributes"]["pkce.code.challenge.method"], "S256")

    def test_clients_cannot_use_implicit_password_service_or_broad_scopes(self):
        for client in self.candidates:
            self.assertEqual(client["defaultClientScopes"], ["basic"])
            self.assertTrue(client["consentRequired"])
            self.assertEqual(client["webOrigins"], [])
            for flag in ("implicitFlowEnabled", "directAccessGrantsEnabled",
                         "serviceAccountsEnabled", "fullScopeAllowed"):
                self.assertIs(client[flag], False)

    def test_no_users_secrets_tokens_credentials_or_release_authority(self):
        report = review_package(RESOURCE, ISSUER)
        self.assertFalse(report["deployable"])
        self.assertTrue(report["not_a_keycloak_import"])
        self.assertTrue(report["not_a_release_receipt"])
        self.assertNotIn("clients", report)
        self.assertNotIn("users", report)
        self.assertNotIn("credentials", report)
        self.assertEqual(report["realm"], "prp-mcp218")
        self.assertEqual(report["issuer"], ISSUER)
        self.assertEqual(report["synthetic_owner_plan"]["actual_user_ids"],
                         "NOT_ALLOCATED")
        self.assertEqual(report["synthetic_owner_plan"]["expanded_user_ids_setting"],
                         "NOT_CONFIGURED")
        self.assertEqual(report["synthetic_owner_plan"]["owner_client_grants"],
                         "NOT_GRANTED")

    def test_broadening_or_replacing_client_is_rejected(self):
        mutations = [
            (0, "redirectUris", ["https://prp-test.micor.top/callback"]),
            (0, "publicClient", False),
            (0, "optionalClientScopes", ["prp.tasks.read"]),
            (1, "redirectUris", ["https://evil.invalid/callback"]),
            (1, "publicClient", True),
            (1, "optionalClientScopes", ["prp.write.create"]),
            (1, "clientAuthenticatorType", "client-secret"),
            (1, "fullScopeAllowed", True),
        ]
        for index, field, new_value in mutations:
            with self.subTest(index=index, field=field):
                bad = deepcopy(self.candidates)
                bad[index][field] = new_value
                with self.assertRaises(ValueError):
                    validate_proposals(bad, RESOURCE, ISSUER)

    def test_no_extra_duplicate_or_removed_clients(self):
        invalid_sets = [
            self.candidates[:1],
            self.candidates + [deepcopy(self.candidates[0])],
            [self.candidates[0], deepcopy(self.candidates[0])],
            ["not a client", self.candidates[1]],
        ]
        for bad in invalid_sets:
            with self.subTest(bad=str(type(bad[0]))), self.assertRaises(ValueError):
                validate_proposals(bad, RESOURCE, ISSUER)

    def test_reject_legacy_shared_resource_or_issuer_and_unsafe_domains(self):
        bad_resource = [
            "https://prp-test.micor.top/api/mcp",
            "http://mcp218-ci-contract.micor.top/api/mcp",
            "https://mcp218-ci-contract.micor.top:18443/api/mcp",
            "https://mcp218-ci-contract.micor.top/api/mcp?scope=prp.write.create",
        ]
        for value in bad_resource:
            with self.subTest(resource=value), self.assertRaises(ValueError):
                client_proposals(value, ISSUER)
        bad_issuer = [
            "https://auth-test.micor.top/realms/prp-mcp218",
            "https://auth.micor.top/realms/prp-mcp218",
            "http://auth-mcp218-ci-contract.micor.top/realms/prp-mcp218",
            "https://auth-mcp218-ci-contract.micor.top/realms/prp-mcp",
            "https://auth-mcp218-ci-contract.micor.top:18443/realms/prp-mcp218",
            "https://auth-mcp218-ci-contract.micor.top.evil.invalid/realms/prp-mcp218",
            "https://auth-mcp218-.micor.top/realms/prp-mcp218",
        ]
        for value in bad_issuer:
            with self.subTest(issuer=value), self.assertRaises(ValueError):
                client_proposals(RESOURCE, value)

    def test_offline_pure_deterministic_and_never_connects(self):
        with patch("socket.create_connection", side_effect=AssertionError("NETWORK_FORBIDDEN")):
            first = review_package(RESOURCE, ISSUER)
            second = review_package(RESOURCE, ISSUER)
        self.assertEqual(first, second)
        self.assertEqual(first["proposed_clients"], self.candidates)


if __name__ == "__main__":
    unittest.main()
