#!/usr/bin/env python3
"""Synthetic-only checks. No local Nginx, external network or live host."""
import importlib.util
from pathlib import Path
import unittest

module_path = Path(__file__).with_name("classify_test_vhost_upstream_readonly.py")
spec = importlib.util.spec_from_file_location("test_vhost_audit", module_path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

HEADER = "# configuration file /etc/nginx/nginx.conf:\nevents {}\n"
VHOST = "# configuration file /etc/nginx/conf.d/prp-mcp-test.conf:\n"


def dump(proxies, *, host=True):
    name = "server_name prp-test.micor.top;" if host else "server_name other.invalid;"
    blocks = "\n".join("location = /probe%d { proxy_pass %s; }" % (i, url)
                       for i, url in enumerate(proxies))
    # Use normal multi-line directives so the parser cannot match comments.
    blocks = "\n".join("location = /probe%d {\n proxy_pass %s;\n}" % (i, url)
                       for i, url in enumerate(proxies))
    return (HEADER + VHOST + "server {\n" + name + "\n" + blocks
            + "\n}\n# configuration file /etc/nginx/extra.conf:\n"
            + "server { proxy_pass http://127.0.0.1:18081; }\n").encode()


class TestStagingReadOnlyClassifier(unittest.TestCase):
    def assert_safe(self, data):
        self.assertTrue(data["diagnostic_only"])
        self.assertFalse(data["host_mutated"])
        self.assertFalse(data["release_approved"])
        self.assertEqual(data["live_upstream"], "NOT_PROVEN")
        self.assertEqual(data["effective_oauth_scopes"], "NOT_CHECKED")

    def test_v2_literal_candidate_is_not_a_live_acceptance(self):
        data = audit.classify(dump([audit.EXPECTED_V2, audit.EXPECTED_V2]))
        self.assertEqual(data["candidate_upstream"], "V2_18082_ONLY_IN_ON_DISK_VHOST")
        self.assertEqual(data["direct_proxy_pass_count"], 2)
        self.assertFalse(data["route_precedence_checked"])
        self.assertFalse(data["included_proxy_chain_checked"])
        self.assert_safe(data)

    def test_legacy_vhost_is_classified(self):
        data = audit.classify(dump([audit.LEGACY]))
        self.assertEqual(data["candidate_upstream"], "LEGACY_18081_ONLY_IN_ON_DISK_VHOST")
        self.assert_safe(data)

    def test_mixed_port_is_not_allowed_to_look_like_v2(self):
        data = audit.classify(dump([audit.EXPECTED_V2, audit.LEGACY]))
        self.assertEqual(data["candidate_upstream"], "MIXED_18081_18082_IN_ON_DISK_VHOST")
        self.assert_safe(data)

    def test_other_and_variable_proxy_are_unverified(self):
        for proxy in ("http://127.0.0.1:18443", "http://$upstream", "https://127.0.0.1:18082"):
            with self.subTest(proxy=proxy):
                data = audit.classify(dump([proxy]))
                self.assertEqual(data["candidate_upstream"], "UNVERIFIED")
                self.assertEqual(data["on_disk_vhost"], "COMPLEX_OR_NONSTANDARD_PROXY_PRESENT")
                self.assert_safe(data)

    def test_wrong_hostname_does_not_pass(self):
        data = audit.classify(dump([audit.EXPECTED_V2], host=False))
        self.assertEqual(data["on_disk_vhost"], "EXPECTED_TEST_HOST_NOT_FOUND")
        self.assert_safe(data)

    def test_missing_or_repeated_file_fails_closed(self):
        body = dump([audit.EXPECTED_V2])
        for candidate in (b"", HEADER.encode(), body + body):
            data = audit.classify(candidate)
            self.assertEqual(data["candidate_upstream"], "UNVERIFIED")
            self.assert_safe(data)

    def test_comments_and_other_file_cannot_supply_proxy(self):
        candidate = (HEADER + VHOST + "server_name prp-test.micor.top;\n"
                     + "# proxy_pass http://127.0.0.1:18082;\n"
                     + "# configuration file /etc/nginx/else.conf:\n"
                     + "proxy_pass http://127.0.0.1:18082;\n").encode()
        data = audit.classify(candidate)
        self.assertEqual(data["on_disk_vhost"], "NO_LITERAL_PROXY_PASS_IN_TEST_VHOST")
        self.assert_safe(data)

    def test_oversized_and_invalid_utf8_fail_closed(self):
        for candidate in (b"x" * (audit.MAX_DUMP_BYTES + 1), b"\xff"):
            self.assertEqual(audit.classify(candidate)["candidate_upstream"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
