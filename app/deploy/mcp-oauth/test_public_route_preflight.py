import json
import unittest
from email.message import Message
from unittest.mock import patch
import public_route_preflight as live
from public_route_preflight import canonical_resource, metadata_uri, inspect


RESOURCE = "https://mcp.staging.example.org/api/mcp"
ISSUER = "https://auth.staging.example.org/realms/prp-mcp"
WELL_KNOWN = "https://mcp.staging.example.org/.well-known/oauth-protected-resource/api/mcp"


def fake_fetch(uri, method, body):
    if uri == WELL_KNOWN:
        return 200, {"content-type": "application/json"}, {
            "resource": RESOURCE,
            "authorization_servers": [ISSUER],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["prp.tasks.read"],
        }
    if uri == RESOURCE:
        return 401, {
            "www-authenticate": 'Bearer resource_metadata="' + WELL_KNOWN + '"'
        }, {}
    raise AssertionError("Unrecognized preflight URI")


class PublicRouteContractTests(unittest.TestCase):
    def test_actual_backend_api_url_and_protected_resource_metadata(self):
        self.assertEqual(metadata_uri(RESOURCE), WELL_KNOWN)
        self.assertTrue(inspect(RESOURCE, ISSUER, fake_fetch)["unauthenticated_mcp_denied"])

    def test_wrong_resource_prefix_not_accepted(self):
        for value in (
            "https://mcp.staging.example.org/prp/api/mcp",
            "http://mcp.staging.example.org/api/mcp",
            "https://micor.top/api/mcp",
            "https://mcp.staging.example.org/api/mcp?debug=1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_resource(value)

    def test_missing_unauth_challenge_fails(self):
        def wrong_challenge(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "POST":
                headers = {"www-authenticate": "Bearer"}
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "challenge"):
            inspect(RESOURCE, ISSUER, wrong_challenge)

    def test_anonymous_mcp_must_fail_closed(self):
        def accidentally_open(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "POST":
                return 200, headers, {"result": {"tools": []}}
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "401"):
            inspect(RESOURCE, ISSUER, accidentally_open)

    def test_public_discovery_rejects_extra_or_malformed_scopes(self):
        cases = (
            ["prp.tasks.read", "prp.finance.read"],
            ["prp.tasks.read", "prp.wellness.read"],
            ["prp.tasks.read", "prp.write.create"],
            ["prp.tasks.read", "prp.write.update", "prp.write.delete"],
            ["prp.tasks.read", "unknown.scope"],
            ["prp.tasks.read", "prp.tasks.read"],
            ["prp.finance.read", "prp.tasks.read"],
            [],
            None,
            "prp.tasks.read",
        )
        for scopes in cases:
            with self.subTest(scopes=scopes):
                def extra_discovery(uri, method, body):
                    status, headers, data = fake_fetch(uri, method, body)
                    if method == "GET":
                        data["scopes_supported"] = scopes
                    return status, headers, data
                with self.assertRaisesRegex(ValueError, "task-read-only"):
                    inspect(RESOURCE, ISSUER, extra_discovery)

    def test_public_discovery_requires_scopes_field(self):
        def missing_scopes(uri, method, body):
            status, headers, data = fake_fetch(uri, method, body)
            if method == "GET":
                del data["scopes_supported"]
            return status, headers, data
        with self.assertRaisesRegex(ValueError, "task-read-only"):
            inspect(RESOURCE, ISSUER, missing_scopes)

    def test_metadata_different_target_rejected(self):
        def tampered(uri, method, body):
            status, headers, json_value = fake_fetch(uri, method, body)
            if method == "GET":
                json_value["resource"] = "https://elsewhere.staging.example.org/api/mcp"
            return status, headers, json_value
        with self.assertRaisesRegex(ValueError, "Advertised resource"):
            inspect(RESOURCE, ISSUER, tampered)

    def test_network_fetch_requires_exact_staging_method_and_url(self):
        with patch.object(live, "build_opener", side_effect=AssertionError("network attempted")):
            for args in (
                    ("https://micor.top/api/mcp", "POST", {"method": "initialize"}),
                    (live.STAGING_RESOURCE, "GET", None),
                    (live.STAGING_RESOURCE, "POST", {"method": "tools/list"}),
                    (live.STAGING_METADATA + "?unexpected=true", "GET", None),
                    (live.STAGING_METADATA, "POST", {"method": "initialize"}),
                    ("http://prp-test.micor.top/api/mcp", "POST", {"method": "initialize"}),
            ):
                with self.subTest(args=args), self.assertRaisesRegex(
                        ValueError, "Fixed staging URL"):
                    live.https_fetch(*args)

    def test_transport_never_sends_credentials_or_follows_redirects(self):
        class FakeResponse:
            def __init__(self, url, status, payload, response_headers):
                self._url, self.status, self._payload = url, status, payload
                self.headers = Message()
                for k, v in response_headers.items():
                    self.headers.add_header(k, v)
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return self._url
            def read(self, n): return self._payload[:n]
        observed = []
        class FakeOpener:
            def open(self, req, timeout):
                observed.append((req.full_url, req.get_method(), req.header_items(),
                                 req.data, timeout))
                if req.full_url == live.STAGING_METADATA:
                    return FakeResponse(req.full_url, 200,
                                        json.dumps({"resource": live.STAGING_RESOURCE}).encode(),
                                        {"Content-Type": "application/json"})
                return FakeResponse(req.full_url, 401, b"credentials never parsed",
                                    {"WWW-Authenticate": 'Bearer resource_metadata="' +
                                     live.STAGING_METADATA + '"'})
        with patch.object(live, "build_opener", return_value=FakeOpener()) as make:
            metadata = live.https_fetch(live.STAGING_METADATA, "GET", None)
            response = live.https_fetch(live.STAGING_RESOURCE, "POST",
                                        {"jsonrpc": "2.0", "method": "initialize"})
        self.assertEqual(metadata[0], 200)
        self.assertEqual(metadata[2]["resource"], live.STAGING_RESOURCE)
        self.assertEqual(response[0], 401)
        self.assertEqual(response[2], {})
        self.assertEqual([x[1] for x in observed], ["GET", "POST"])
        self.assertTrue(all(x[4] == 9 for x in observed))
        self.assertTrue(all("authorization" not in dict((k.lower(), v) for k, v in x[2])
                            for x in observed))
        self.assertTrue(all("cookie" not in dict((k.lower(), v) for k, v in x[2])
                            for x in observed))
        self.assertIsNone(observed[0][3])
        self.assertEqual(json.loads(observed[1][3])["method"], "initialize")
        for call in make.call_args_list:
            self.assertTrue(any(isinstance(x, live.ProxyHandler) for x in call.args))
            self.assertTrue(any(isinstance(x, live.NoRedirect) for x in call.args))

    def test_redirect_is_refused_before_downstream_fetch(self):
        with self.assertRaisesRegex(live.RedirectForbidden, "redirect"):
            live.NoRedirect().redirect_request(None, None, None, 302, None,
                                               "https://unknown.example/")

    def test_unexpected_advertised_finance_or_write_scopes_fail_closed(self):
        def excess_scope(uri, method, body):
            status, headers, metadata = fake_fetch(uri, method, body)
            if method == "GET":
                metadata["scopes_supported"] = [
                    "prp.tasks.read", "prp.finance.read", "prp.write.create"]
            return status, headers, metadata
        with self.assertRaisesRegex(ValueError, "Task-only"):
            inspect(RESOURCE, ISSUER, excess_scope)


if __name__ == "__main__":
    unittest.main()
