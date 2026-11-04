"""Fail-closed tests for the non-installable client registration review pack."""
from copy import deepcopy
from io import StringIO
import contextlib
import json
import unittest

from review_exact_client_registrations import (
    CHATGPT, CHATGPT_CALLBACK, CHATGPT_JWKS, FIRST_PARTY, PRP_CALLBACK,
    RESOURCE, client_proposals, main, review_package, validate_proposals,
)


class RegistrationReviewOnlyTests(unittest.TestCase):
    def setUp(self):
        self.original = client_proposals()
        self.by_id = {x["clientId"]: x for x in self.original}

    def test_two_exact_clients_and_no_realm_import_or_release_authority(self):
        report = review_package()
        self.assertTrue(validate_proposals(report["proposed_clients"]))
        self.assertEqual(report["realm"], "prp-mcp")
        self.assertEqual(report["resource"], RESOURCE)
        self.assertEqual(set(self.by_id), {CHATGPT, FIRST_PARTY})
        self.assertFalse(report["deployable"])
        self.assertTrue(report["not_a_keycloak_import"])
        self.assertTrue(report["not_a_release_receipt"])
        self.assertNotIn("clients", report)
        self.assertNotIn("clientPolicies", report)
        self.assertEqual(report["status"], "PENDING_INDEPENDENT_G0_AND_B2_APPROVAL")

    def test_first_party_is_own_public_pkce_client_without_scope_expansion(self):
        c = self.by_id[FIRST_PARTY]
        self.assertTrue(c["publicClient"])
        self.assertTrue(c["standardFlowEnabled"])
        self.assertEqual(c["redirectUris"], [PRP_CALLBACK])
        self.assertEqual(c["attributes"], {"pkce.code.challenge.method": "S256"})
        self.assertEqual(c["optionalClientScopes"], [])
        self.assertEqual(c["defaultClientScopes"], ["basic"])
        self.assertEqual(c["protocolMappers"], [])

    def test_chatgpt_has_exact_jwks_redirect_privatejwt_task_only_audience(self):
        c = self.by_id[CHATGPT]
        self.assertFalse(c["publicClient"])
        self.assertEqual(c["clientAuthenticatorType"], "client-jwt")
        self.assertEqual(c["redirectUris"], [CHATGPT_CALLBACK])
        self.assertEqual(c["optionalClientScopes"], ["prp.tasks.read", "offline_access"])
        self.assertEqual(c["attributes"], {
            "pkce.code.challenge.method": "S256",
            "use.jwks.url": "true",
            "jwks.url": CHATGPT_JWKS,
        })
        self.assertEqual(c["protocolMappers"][0]["config"], {
            "included.custom.audience": RESOURCE,
            "id.token.claim": "false",
            "access.token.claim": "true",
        })

    def test_all_unsafe_grants_remain_disabled_for_both_clients(self):
        for c in self.original:
            for prop in ("implicitFlowEnabled", "directAccessGrantsEnabled",
                         "serviceAccountsEnabled", "fullScopeAllowed"):
                self.assertIs(c[prop], False, prop)
            self.assertEqual(c["webOrigins"], [])
            self.assertEqual(c["defaultClientScopes"], ["basic"])
            self.assertIs(c["consentRequired"], True)

    def test_reject_broadened_scope_redirect_pkce_jwks_or_client_id(self):
        cases = (
            (0, ("redirectUris",), ["https://example.invalid/callback"]),
            (0, ("optionalClientScopes",), ["prp.tasks.read"]),
            (0, ("attributes", "pkce.code.challenge.method"), "plain"),
            (0, ("fullScopeAllowed",), True),
            (0, ("publicClient",), False),
            (1, ("clientId",), "https://attacker.invalid/oauth/client.json"),
            (1, ("redirectUris",), ["https://example.invalid/callback"]),
            (1, ("attributes", "jwks.url"), "https://example.invalid/jwks"),
            (1, ("attributes", "use.jwks.url"), "false"),
            (1, ("attributes", "pkce.code.challenge.method"), "plain"),
            (1, ("optionalClientScopes",), ["prp.tasks.read", "prp.finance.read"]),
            (1, ("serviceAccountsEnabled",), True),
        )
        for i, keys, value in cases:
            with self.subTest(index=i, field=".".join(keys)):
                modified = deepcopy(self.original)
                target = modified[i]
                for k in keys[:-1]:
                    target = target[k]
                target[keys[-1]] = value
                with self.assertRaises(ValueError):
                    validate_proposals(modified)

    def test_reject_duplicate_extra_removed_and_nonobject_proposals(self):
        for modified in (
            [self.original[0]],
            self.original + [deepcopy(self.original[0])],
            [self.original[0], deepcopy(self.original[0])],
            ["not a client", self.original[1]],
        ):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                validate_proposals(modified)

    def test_cli_prints_only_non_deployable_fixed_review_json(self):
        capture = StringIO()
        with contextlib.redirect_stdout(capture):
            main()
        report = json.loads(capture.getvalue())
        self.assertFalse(report["deployable"])
        self.assertTrue(report["not_a_release_receipt"])
        self.assertEqual(report["proposed_clients"], self.original)
        self.assertNotIn("access_token", capture.getvalue())
        self.assertNotIn("client_secret", capture.getvalue())


if __name__ == "__main__":
    unittest.main()
