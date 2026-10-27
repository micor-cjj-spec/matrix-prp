"""Offline contract tests for the strictly GET-only public staging probe."""
import json
import unittest
from email.message import Message
from unittest.mock import patch
import public_get_only_diagnostic as d


class FakeResponse:
    def __init__(self, url, status, document, content_type="application/json"):
        self.url = url
        self.status = status
        self.payload = json.dumps(document).encode() if not isinstance(document, bytes) else document
        self.headers = Message()
        self.headers.add_header("Content-Type", content_type)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, length): return self.payload[:length]


RESOURCE = {"resource": d.RESOURCE, "authorization_servers": [d.ISSUER],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["prp.tasks.read"]}
DISCOVERY = {"issuer": d.ISSUER, "client_id_metadata_document_supported": True,
             "code_challenge_methods_supported": ["S256"],
             "grant_types_supported": ["authorization_code", "refresh_token"],
             "jwks_uri": d.JWKS}
JWKS = {"keys": [{"kty": "RSA", "n": "public-modulus", "e": "AQAB",
                  "use": "sig", "alg": "RS256"}]}


class PublicGetOnlyDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.docs = {d.RESOURCE_METADATA: RESOURCE.copy(),
                     d.DISCOVERY: DISCOVERY.copy(), d.JWKS: JWKS.copy()}

    def test_metadata_only_complete_with_exact_resource_and_issuer(self):
        seen = []
        def fetch(url):
            seen.append(url)
            return self.docs[url]
        report = d.assess(fetch)
        self.assertEqual(report["status"], "PUBLIC_GET_ONLY_METADATA_PASSED")
        self.assertEqual(seen, [d.RESOURCE_METADATA, d.DISCOVERY, d.JWKS])
        self.assertEqual(report["request_method"], "GET_ONLY")
        self.assertFalse(report["b2_release_approved"])
        self.assertFalse(report["mcp_post_or_tools_called"])
        self.assertFalse(report["chatgpt_oauth_verified"])
        self.assertFalse(report["public_ipv6_independently_proven"])

    def test_excess_scope_is_observation_blocker_not_approval(self):
        self.docs[d.RESOURCE_METADATA]["scopes_supported"] = [
            "prp.tasks.read", "prp.finance.read", "prp.write.create"]
        report = d.assess(lambda url: self.docs[url])
        self.assertEqual(report["checks"]["resource_metadata"],
                         {"state": "UNVERIFIED", "reason": "TASK_ONLY_SCOPE_NOT_DEPLOYED"})
        self.assertEqual(report["status"], "PUBLIC_GET_ONLY_METADATA_REVIEW_REQUIRED")
        self.assertFalse(report["b2_release_approved"])

    def test_unreachable_is_unknown_not_secure_denial(self):
        def fetch(url):
            if url == d.RESOURCE_METADATA:
                raise d.ProbeError("TRANSPORT_UNVERIFIED")
            return self.docs[url]
        report = d.assess(fetch)
        self.assertEqual(report["checks"]["resource_metadata"]["state"], "UNVERIFIED")
        self.assertEqual(report["checks"]["issuer_public_jwks"]["state"], "PASS")
        self.assertFalse(report["b2_release_approved"])

    def test_wrong_resource_or_changed_jwks_is_rejected(self):
        self.docs[d.RESOURCE_METADATA]["resource"] = "https://micor.top/api/mcp"
        self.docs[d.DISCOVERY]["jwks_uri"] = "https://untrusted.example/key"
        report = d.assess(lambda url: self.docs[url])
        self.assertEqual(report["checks"]["resource_metadata"]["reason"], "RESOURCE_MISMATCH")
        self.assertEqual(report["checks"]["issuer_discovery"]["reason"], "JWKS_ENDPOINT_DRIFT")

    def test_fetch_sends_only_get_to_exact_allowlisted_staging_url(self):
        calls = []
        class Opener:
            def open(self, request, timeout):
                calls.append((request.full_url, request.get_method(), timeout))
                return FakeResponse(request.full_url, 200, RESOURCE)
        with patch.object(d, "build_opener", return_value=Opener()) as build:
            body = d.public_get(d.RESOURCE_METADATA)
        self.assertEqual(body["resource"], d.RESOURCE)
        self.assertEqual(calls, [(d.RESOURCE_METADATA, "GET", 9)])
        args = build.call_args.args
        self.assertTrue(any(type(a) is d.NoRedirect for a in args))
        self.assertTrue(any(type(a) is d.ProxyHandler for a in args))

    def test_fetch_refuses_any_nontarget_url_without_network(self):
        with patch.object(d, "build_opener", side_effect=AssertionError("network attempted")):
            for url in ("https://micor.top/api/mcp",
                        "https://prp-test.micor.top/api/mcp",
                        d.RESOURCE_METADATA + "?x=1",
                        "http://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp"):
                with self.assertRaisesRegex(d.ProbeError, "URL_NOT_ALLOWLISTED"):
                    d.public_get(url)

    def test_redirect_duplicate_keys_and_unbounded_body_fail_closed(self):
        cases = [
            (d.RESOURCE_METADATA + "/redirect", RESOURCE, "REDIRECT_FORBIDDEN"),
            (d.RESOURCE_METADATA, b'{"a":1,"a":2}', "DUPLICATE_JSON_KEY"),
            (d.RESOURCE_METADATA, b"0" * (d.MAX_BODY + 1), "JSON_TOO_LARGE"),
        ]
        for returned_url, value, reason in cases:
            with self.subTest(reason=reason):
                class Opener:
                    def open(self, req, timeout):
                        return FakeResponse(returned_url, 200, value)
                with patch.object(d, "build_opener", return_value=Opener()):
                    with self.assertRaisesRegex(d.ProbeError, reason):
                        d.public_get(d.RESOURCE_METADATA)

    def test_bad_mime_or_status_is_not_considered_a_valid_metadata_response(self):
        for code, mime, expected in ((404, "application/json", "NON_200_RESPONSE"),
                                     (200, "text/html", "CONTENT_TYPE_INVALID")):
            with self.subTest(code=code):
                class Opener:
                    def open(self, req, timeout):
                        return FakeResponse(req.full_url, code, RESOURCE, mime)
                with patch.object(d, "build_opener", return_value=Opener()):
                    with self.assertRaisesRegex(d.ProbeError, expected):
                        d.public_get(d.RESOURCE_METADATA)


if __name__ == "__main__":
    unittest.main()
