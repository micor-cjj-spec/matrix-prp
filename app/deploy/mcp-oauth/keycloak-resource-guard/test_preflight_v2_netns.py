#!/usr/bin/env python3
"""No host namespace changes: fake subprocesses for V2 netns preflight."""
import types
import unittest
from unittest.mock import patch

import preflight_v2_netns as mod

SAFE = {"status": "V2_ROUTE_SEMANTICS_INVENTORIED",
        "test": {"v2_behind_non_exact_locations": 0,
                 "v2_proxy_directives": 2,
                 "broad_prefix_with_proxy": 0,
                 "nonloopback_or_variable_upstream_directives": 0}}

class NetNamespacePreflightTests(unittest.TestCase):
    def call(self, inventory=SAFE, missing=None, exit_code=0, runner=None):
        def binaries(name):
            return None if name == missing else "/mock/" + name
        def fake_runner(args, **kwargs):
            self.assertEqual(args, ["/mock/unshare", "--net", "--fork", "/bin/true"])
            self.assertLessEqual(kwargs["timeout"], 6)
            return types.SimpleNamespace(returncode=exit_code)
        with patch.object(mod.semantic, "inspect", return_value=inventory):
            return mod.check_host(binaries=binaries,
                                  runner=runner or fake_runner)

    def test_all_preflights_pass_only_in_ephemeral_namespace(self):
        report = self.call()
        self.assertEqual(report["status"], "ISOLATED_NETNS_PREFLIGHT_READY")
        self.assertTrue(report["unshare_netns_available"])
        self.assertFalse(report["host_nginx_started_or_reloaded"])
        self.assertFalse(report["public_or_api_requests_executed"])

    def test_broad_upstream_refuses_namespace_check(self):
        unsafe = {"status": "V2_ROUTE_SEMANTICS_INVENTORIED",
                  "test": dict(SAFE["test"], broad_prefix_with_proxy=1)}
        with self.assertRaisesRegex(ValueError, "ROUTE_ENVELOPE_CHANGED"):
            self.call(unsafe)

    def test_implicit_external_upstream_fails_closed(self):
        unsafe = {"test": dict(SAFE["test"], nonloopback_or_variable_upstreams=0,
                               nonloopback_or_variable_upstream_directives=1)}
        with self.assertRaisesRegex(ValueError, "ROUTE_ENVELOPE_CHANGED"):
            self.call(unsafe)

    def test_unshare_denied_does_not_claim_runtime_acceptance(self):
        report = self.call(exit_code=1)
        self.assertEqual(report["status"], "ISOLATED_NETNS_PREFLIGHT_BLOCKED")
        self.assertEqual(report["blocker"], "NEW_NETWORK_NAMESPACE_NOT_PERMITTED")
        self.assertFalse(report["release_approved"])

    def test_missing_ip_or_nginx_never_runs_unshare(self):
        def forbidden_runner(*args, **kwargs):
            raise AssertionError("must not run subprocess")
        for missing in ("ip", "nginx", "python3"):
            with self.subTest(missing=missing):
                report = self.call(missing=missing, runner=forbidden_runner)
                self.assertEqual(report["blocker"], "REQUIRED_LOCAL_BINARY_MISSING")
                self.assertEqual(report["missing_binary_count"], 1)

    def test_probe_timeout_stays_closed(self):
        import subprocess
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("unshare", 6)
        report = self.call(runner=timeout)
        self.assertEqual(report["blocker"], "NEW_NETWORK_NAMESPACE_PROBE_TIMEOUT")

if __name__ == "__main__":
    unittest.main()
