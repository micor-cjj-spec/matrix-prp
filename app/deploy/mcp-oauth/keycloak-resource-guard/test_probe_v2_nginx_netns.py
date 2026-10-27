#!/usr/bin/env python3
"""Pure unit tests: no real namespaces, network sockets or Nginx process."""
import json
import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import probe_v2_nginx_netns as mod

class V2NetnsRuntimeTests(unittest.TestCase):
    def test_parent_only_launches_unshare_with_new_net_namespace(self):
        captured = []
        fake_report = {
            "status": mod.STATUS_READY,
            "host_nginx_installed_or_reloaded": False,
            "real_mcp_or_prp_backend_accessed": False,
        }
        def run(argv, **kwargs):
            captured.append((argv, kwargs))
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps(fake_report), stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status":"ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", side_effect=lambda name:"/mock/"+name), \
             patch.object(mod.os, "readlink", return_value="net:[111]"), \
             patch.object(mod.subprocess, "run", side_effect=run):
            result = mod.parent_run()
        self.assertEqual(result["status"], mod.STATUS_READY)
        argv, kwargs = captured[0]
        self.assertEqual(argv[:4], ["/mock/unshare", "--net", "--fork", "--kill-child"])
        self.assertEqual(argv[-2:], ["--isolated-child", "net:[111]"])
        self.assertTrue(kwargs.get("capture_output"))
        self.assertLessEqual(kwargs.get("timeout"), 55)

    def test_preflight_failure_never_executes_unshare(self):
        with patch.object(mod.netns,"check_host",
                          return_value={"status":"ISOLATED_NETNS_PREFLIGHT_BLOCKED",
                                        "blocker":"NEW_NETWORK_NAMESPACE_NOT_PERMITTED"}), \
             patch.object(mod.subprocess,"run",side_effect=AssertionError("called")):
            report = mod.parent_run()
        self.assertEqual(report["status"],"ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED")
        self.assertEqual(report["blocker"],"NEW_NETWORK_NAMESPACE_NOT_PERMITTED")

    def test_parent_does_not_accept_nonzero_exit_for_claimed_success(self):
        fake = types.SimpleNamespace(
            returncode=2, stdout=json.dumps({"status":mod.STATUS_READY}),
            stderr="")
        with patch.object(mod.netns,"check_host",
                          return_value={"status":"ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil,"which",return_value="/mock/unshare"), \
             patch.object(mod.os,"readlink",return_value="net:[111]"), \
             patch.object(mod.subprocess,"run",return_value=fake):
            report = mod.parent_run()
        self.assertEqual(report["blocker"],"ISOLATED_CHILD_EXIT_MISMATCH")

    def test_child_refuses_equal_parent_namespace(self):
        with patch.object(mod.os,"readlink",return_value="net:[111]"), \
             patch.object(mod.subprocess,"run",side_effect=AssertionError("ran")):
            with self.assertRaisesRegex(ValueError,"NETWORK_NAMESPACE_NOT_ISOLATED"):
                mod.require_own_namespace("net:[111]")

    def test_child_refuses_any_non_loopback_interface_before_ip_changes(self):
        with patch.object(mod.os,"readlink",return_value="net:[222]"), \
             patch.object(mod.socket,"if_nameindex",return_value=[(1,"lo"),(2,"eth0")]), \
             patch.object(mod.subprocess,"run",side_effect=AssertionError("ran")):
            with self.assertRaisesRegex(ValueError,"NON_LOOPBACK_INTERFACE"):
                mod.require_own_namespace("net:[111]")

    def test_report_status_is_not_production_approval(self):
        self.assertNotIn("PUBLIC", mod.STATUS_READY)
        self.assertNotIn("OAUTH", mod.STATUS_READY)
        self.assertNotIn("INSTALL", mod.STATUS_READY)

if __name__ == "__main__":
    unittest.main()
