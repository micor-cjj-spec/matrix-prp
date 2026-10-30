#!/usr/bin/env python3
"""Offline tests: no DNS, TLS, HTTP, credentials or live server access."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("review_public_oauth_readonly.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class FakeHeaders:
    def get_content_type(self):
        return "application/json"

class FakeResponse:
    status = 200
    headers = FakeHeaders()
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count):
        return self.payload

class ProbeTests(unittest.TestCase):
    def test_issuer_match(self):
        self.assertEqual(probe.classify_json("issuer_discovery", {
            "issuer": probe.EXPECTED_ISSUER,
            "authorization_endpoint": probe.EXPECTED_ISSUER + "/protocol/openid-connect/auth",
            "token_endpoint": probe.EXPECTED_ISSUER + "/protocol/openid-connect/token",
            "jwks_uri": probe.EXPECTED_ISSUER + "/protocol/openid-connect/certs"
        }), "METADATA_MATCH")
    def test_issuer_mismatch(self):
        self.assertEqual(probe.classify_json("issuer_discovery", {"issuer": "https://other.invalid"}), "ISSUER_MISMATCH")
    def test_resource_mismatch(self):
        self.assertEqual(probe.classify_json("protected_resource", {"resource": "https://other.invalid"}), "RESOURCE_MISMATCH")
    def test_server_mismatch(self):
        self.assertEqual(probe.classify_json("protected_resource", {"resource": probe.EXPECTED_RESOURCE, "authorization_servers": []}), "AUTHORIZATION_SERVER_MISMATCH")
    def test_resource_match(self):
        self.assertEqual(probe.classify_json("protected_resource", {"resource": probe.EXPECTED_RESOURCE, "authorization_servers": [probe.EXPECTED_ISSUER]}), "METADATA_MATCH")
    def test_reject_unlisted_url_before_network(self):
        with patch.object(probe, "build_opener", side_effect=AssertionError("NETWORK_USED")):
            self.assertEqual(probe.probe_metadata("issuer_discovery", "https://evil.invalid/"), "REFUSED_NON_ALLOWLIST_URL")
    def test_no_redirects(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid/"))
    def test_bad_json(self):
        with patch.object(probe, "build_opener") as mock:
            mock.return_value.open.return_value = FakeResponse(b"not json")
            self.assertEqual(probe.probe_metadata("issuer_discovery", probe.URLS["issuer_discovery"]), "HTTP_OR_JSON_UNAVAILABLE")
    def test_oversize(self):
        with patch.object(probe, "build_opener") as mock:
            mock.return_value.open.return_value = FakeResponse(b"x" * 65537)
            self.assertEqual(probe.probe_metadata("issuer_discovery", probe.URLS["issuer_discovery"]), "OVERSIZE_RESPONSE")
    def test_main_only_reports_categories(self):
        with patch.object(probe, "probe_dns", return_value="DNS_UNAVAILABLE"), patch.object(probe, "probe_tls", return_value="TLS_UNAVAILABLE_OR_UNTRUSTED"), patch.object(probe, "probe_metadata", return_value="HTTP_OR_JSON_UNAVAILABLE"), patch("builtins.print") as out:
            self.assertEqual(probe.main(), 0)
            report = json.loads(out.call_args.args[0])
            self.assertFalse(report["production_change_authorized"])
            self.assertFalse(report["real_chatgpt_signature_verified"])

if __name__ == "__main__":
    unittest.main()
