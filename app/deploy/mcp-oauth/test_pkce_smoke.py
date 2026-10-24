import base64
import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from pkce_smoke import (
    pkce_pair, authorization_url, validate_callback, exchange, smoke,
)


ISSUER = "https://auth.example.org/realms/prp-mcp"
RESOURCE = "https://prp.staging.test/api/mcp"
CALLBACK = "http://127.0.0.1:8765/callback"


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()
        self.headers = {"Content-Type": "application/json"}
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self, limit):
        return self.data


class PKCESmokeOfflineTests(unittest.TestCase):
    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = pkce_pair()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)
        self.assertTrue(len(verifier) >= 43)

    def test_authorization_has_resource_scope_and_exact_callback(self):
        url = authorization_url(
            ISSUER + "/protocol/openid-connect/auth", "test-client",
            CALLBACK, RESOURCE, "challenge123", "state123", "nonce123")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["resource"], [RESOURCE])
        self.assertEqual(query["scope"], ["openid prp.tasks.read"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["redirect_uri"], [CALLBACK])

    def test_callback_requires_original_state(self):
        valid = "code=example-code&state=randomstate&iss=https%3A%2F%2Fauth.example.org%2Frealms%2Fprp-mcp"
        self.assertEqual(validate_callback(valid, "randomstate", ISSUER), "example-code")
        with self.assertRaisesRegex(ValueError, "state"):
            validate_callback(valid, "replayedstate", ISSUER)
        with self.assertRaisesRegex(ValueError, "issuer"):
            validate_callback("code=example-code&state=randomstate&iss=https%3A%2F%2Fevil.test",
                              "randomstate", ISSUER)

    def test_code_exchange_sends_resource_and_verifier_but_never_logs_token(self):
        recorded = []
        def fake_open(request, timeout):
            recorded.append(request)
            return FakeResponse({"access_token": "private-token-do-not-print"})
        with patch("pkce_smoke.urlopen", side_effect=fake_open):
            token = exchange(ISSUER + "/protocol/openid-connect/token",
                             "pkce-test-client", CALLBACK, "one-time-code",
                             "secret-verifier", RESOURCE)
        self.assertEqual(token, "private-token-do-not-print")
        self.assertEqual(len(recorded), 1)
        body = parse_qs(recorded[0].data.decode())
        self.assertEqual(body["resource"], [RESOURCE])
        self.assertEqual(body["code_verifier"], ["secret-verifier"])
        self.assertEqual(body["redirect_uri"], [CALLBACK])
        self.assertEqual(body["grant_type"], ["authorization_code"])

    def test_read_only_mcp_flow_does_not_print_personal_task_data(self):
        replies = iter([
            {"data": {"subject": "linked-subject"}},
            {"jsonrpc": "2.0", "id": 1,
             "result": {"serverInfo": {"name": "matrix-prp", "version": "1.0"}}},
            {"jsonrpc": "2.0", "id": 2,
             "result": {"tools": [{"name": "prp_tasks_list"}]}},
            {"jsonrpc": "2.0", "id": 3, "result": {
                "content": [{"type": "text", "text": "private tasks must not print"}],
                "isError": False}},
        ])
        seen = []
        def fake_post(url, token, body, accept="application/json"):
            seen.append((url, token, body))
            return next(replies)
        with patch("pkce_smoke.post_json", side_effect=fake_post), patch(
                "builtins.print") as mock_print:
            self.assertTrue(smoke(RESOURCE, "secret-access-token", "one-time-link-code"))
        self.assertEqual(seen[0][0], RESOURCE + "/link")
        self.assertEqual(seen[0][2], {"ticket": "one-time-link-code"})
        self.assertEqual(seen[-1][2]["params"]["name"], "prp_tasks_list")
        public_output = " ".join(str(arg) for call in mock_print.call_args_list
                                 for arg in call.args)
        self.assertNotIn("private tasks", public_output)
        self.assertNotIn("secret-access-token", public_output)
        self.assertNotIn("one-time-link-code", public_output)


if __name__ == "__main__":
    unittest.main()
