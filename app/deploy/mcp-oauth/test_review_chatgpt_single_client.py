"""Offline owner-scope contract for single-client review. No network or writes."""
import copy
import unittest
from review_chatgpt_single_client import EXPECTED, review_single_client

class SingleClientScopeTests(unittest.TestCase):
    def test_exact_one_and_no_go(self):
        p = review_single_client()
        self.assertEqual(p["proposed_client_count"], 1)
        self.assertEqual(p["proposed_client"]["clientId"],
                         "https://chatgpt.com/oauth/client.json")
        self.assertFalse(p["deployable"])
        self.assertTrue(p["not_an_admin_api_request"])
        self.assertIn("prp-first-party-link", p["explicitly_excluded"])

    def test_reject_unauthorized_changes(self):
        cases = [
            ("clientId", "prp-first-party-link"),
            ("redirectUris", ["https://evil.invalid/cb"]),
            ("optionalClientScopes", ["prp.finance.read"]),
            ("fullScopeAllowed", True),
            ("publicClient", True),
            ("attributes", {"pkce.code.challenge.method": "plain"}),
            ("protocolMappers", []),
        ]
        for key, value in cases:
            with self.subTest(key=key):
                candidate = copy.deepcopy(EXPECTED)
                candidate[key] = value
                with self.assertRaises(ValueError):
                    review_single_client(candidate)

    def test_default_none_is_fixed_safe_candidate(self):
        self.assertEqual(review_single_client(None)["proposed_client"], EXPECTED)

    def test_reject_non_client_and_extra_fields(self):
        for candidate in ([], {"clientId": EXPECTED["clientId"]}):
            with self.assertRaises(ValueError):
                review_single_client(candidate)
        candidate = copy.deepcopy(EXPECTED)
        candidate["unexpected"] = True
        with self.assertRaises(ValueError):
            review_single_client(candidate)

if __name__ == "__main__":
    unittest.main()
