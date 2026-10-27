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

    def test_edge_mode_uses_only_new_namespace(self):
        calls = []
        report = {"status": mod.STATUS_EDGE,
                  "host_nginx_installed_or_reloaded": False,
                  "real_mcp_or_prp_backend_accessed": False}
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps(report), stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", side_effect=lambda name: "/mock/" + name), \
             patch.object(mod.os, "readlink", return_value="net:[112]"), \
             patch.object(mod.subprocess, "run", side_effect=runner):
            result = mod.parent_run(edge_matrix=True)
        self.assertEqual(result["status"], mod.STATUS_EDGE)
        self.assertEqual(calls[0][0][:4],
                         ["/mock/unshare", "--net", "--fork", "--kill-child"])
        self.assertEqual(calls[0][0][-3:], ["--isolated-child", "net:[112]", "edge"])

    def test_edge_matrix_only_fixed_literal_paths(self):
        for group in (mod.EDGE_WRONG_HOST, mod.EDGE_CANONICAL_ALIASES):
            labels = [k for k, _ in group]
            self.assertEqual(len(set(labels)), len(labels))
            for label, path in group:
                self.assertTrue(label.startswith("edge_"))
                self.assertTrue(path.startswith("/"))
                self.assertTrue(path.isascii())
                self.assertNotIn("?", path)
                self.assertNotIn("#", path)
                self.assertNotIn("\r", path)
                self.assertNotIn("\n", path)
        self.assertIn(("edge_wrong_host_mcp", "/api/mcp"), mod.EDGE_WRONG_HOST)
        self.assertIn(("edge_alias_pct_letter", "/api/%6dcp"), mod.EDGE_CANONICAL_ALIASES)

    def test_raw_uri_protocol_matrix_requires_canonical_metadata_and_query_denial(self):
        requests = {}
        def spy(label, **kwargs):
            requests[label] = kwargs
        mod.run_raw_uri_protocol_compat_checks(spy)
        self.assertEqual(len(requests), 4)
        metadata = requests["compat_metadata_discovery_get"]
        self.assertEqual(metadata["method"], "GET")
        self.assertEqual(metadata["path"],
                         "/.well-known/oauth-protected-resource/api/mcp")
        self.assertEqual(metadata["expected"], (200,))
        self.assertEqual(metadata["hits"], 1)
        for label in ("compat_metadata_discovery_query_rejected",
                      "compat_mcp_post_query_rejected",
                      "compat_mcp_get_query_rejected"):
            with self.subTest(label=label):
                request = requests[label]
                self.assertIn("?", request["path"])
                self.assertEqual(request["expected"], (404,))
                self.assertEqual(request["hits"], 0)
        self.assertEqual(
            requests["compat_mcp_post_query_rejected"]["method"], "POST")

    def test_raw_uri_protocol_matrix_never_tests_real_auth(self):
        self.assertFalse("TOKEN" in mod.STATUS_RAW)
        self.assertFalse("AUTH" in mod.STATUS_RAW)
        self.assertFalse("PUBLIC" in mod.STATUS_RAW)
        self.assertFalse("DEPLOY" in mod.STATUS_RAW)

    def test_edge_get_and_post_aliases_are_both_probed(self):
        calls = []
        def spy(label, **kwargs):
            calls.append((label, kwargs))
        mod.run_edge_checks(spy)
        self.assertEqual(len(calls), len(mod.EDGE_WRONG_HOST)
                         + 1 + len(mod.EDGE_CANONICAL_ALIASES) * 2)
        control = [k for k, _ in calls if k == "edge_canonical_get_control"]
        self.assertEqual(control, ["edge_canonical_get_control"])
        for label, path in mod.EDGE_CANONICAL_ALIASES:
            get = [kw for key, kw in calls if key == label]
            post = [kw for key, kw in calls
                    if key == label.replace("edge_alias_", "edge_post_alias_")]
            self.assertEqual(len(get), 1)
            self.assertEqual(len(post), 1)
            self.assertEqual(get[0]["path"], path)
            self.assertEqual(post[0]["path"], path)
            self.assertEqual(get[0]["method"], "GET")
            self.assertEqual(post[0]["method"], "POST")
            self.assertEqual(get[0]["hits"], 0)
            self.assertEqual(post[0]["hits"], 0)
            self.assertNotIn(200, post[0]["expected"])
            self.assertNotIn(405, get[0]["expected"])

    def test_wrong_host_matrix_never_uses_trusted_host(self):
        calls = []
        mod.run_edge_checks(lambda label, **kw: calls.append((label, kw)))
        for label, _ in mod.EDGE_WRONG_HOST:
            entry = [kw for key, kw in calls if key == label]
            self.assertEqual(len(entry), 1)
            self.assertEqual(entry[0]["host"], "untrusted.invalid")
            self.assertEqual(entry[0]["expected"], (421,))
            self.assertEqual(entry[0]["hits"], 0)

    def test_nonzero_edge_result_does_not_claim_success(self):
        fake = types.SimpleNamespace(
            returncode=2, stdout=json.dumps({"status": mod.STATUS_EDGE}), stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", return_value="/mock/unshare"), \
             patch.object(mod.os, "readlink", return_value="net:[111]"), \
             patch.object(mod.subprocess, "run", return_value=fake):
            report = mod.parent_run(edge_matrix=True)
        self.assertEqual(report["blocker"], "ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH")
        self.assertFalse(report["release_approved"])

    def test_disposable_raw_uri_mode_must_launch_in_new_netns(self):
        calls = []
        report = {
            "status": mod.STATUS_RAW,
            "sandbox_raw_uri_review_overlay":
                {"original_candidate_modified": False},
            "host_nginx_installed_or_reloaded": False,
        }
        def fake_runner(argv, **kwargs):
            calls.append(argv)
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps(report), stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", side_effect=lambda name: "/mock/" + name), \
             patch.object(mod.os, "readlink", return_value="net:[333]"), \
             patch.object(mod.subprocess, "run", side_effect=fake_runner):
            result = mod.parent_run(raw_guard=True)
        self.assertEqual(result["status"], mod.STATUS_RAW)
        self.assertEqual(calls[0][:4],
                         ["/mock/unshare", "--net", "--fork", "--kill-child"])
        self.assertEqual(calls[0][-3:], ["--isolated-child", "net:[333]", "raw-uri"])

    def test_disposable_raw_uri_mode_cannot_reuse_edge_success(self):
        fake = types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"status": mod.STATUS_EDGE}),
            stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", return_value="/mock/unshare"), \
             patch.object(mod.os, "readlink", return_value="net:[333]"), \
             patch.object(mod.subprocess, "run", return_value=fake):
            report = mod.parent_run(raw_guard=True)
        self.assertEqual(report["blocker"], "ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH")

    def test_pinned_review_mode_rechecks_persisted_bytes_before_unshare(self):
        calls = []
        expected_receipt = {"status": mod.STATUS_PINNED, "release_approved": False}
        actual = (b"trusted main", b"trusted test", {"review_test_candidate_sha256": "fixed"})
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps(expected_receipt), stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.sandbox, "inspect_sources",
                          return_value={"review_main": b"main"}) as sources, \
             patch.object(mod.verified_review, "checked_files",
                          return_value={"from": "actual on disk"}) as files, \
             patch.object(mod.verified_review, "verify_artifact",
                          return_value=actual) as verify, \
             patch.object(mod.shutil, "which", return_value="/mock/unshare"), \
             patch.object(mod.os, "readlink", return_value="net:[111]"), \
             patch.object(mod.subprocess, "run", side_effect=runner):
            result = mod.parent_run(pinned_review=True)
        self.assertEqual(result["status"], mod.STATUS_PINNED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][-3:],
                         ["--isolated-child", "net:[111]", "pinned-review"])
        self.assertEqual(calls[0][0][:4],
                         ["/mock/unshare", "--net", "--fork", "--kill-child"])
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(files.call_count, 1)
        self.assertEqual(sources.call_count, 1)
        self.assertLessEqual(calls[0][1]["timeout"], 55)

    def test_pinned_review_tampered_file_prevents_unshare(self):
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.verified_review, "checked_files",
                          side_effect=ValueError("REVIEW_DIRECTORY_CONTENTS_DRIFT")), \
             patch.object(mod.subprocess, "run",
                          side_effect=AssertionError("must not run unshare")):
            with self.assertRaisesRegex(ValueError, "REVIEW_DIRECTORY_CONTENTS_DRIFT"):
                mod.parent_run(pinned_review=True)

    def test_pinned_review_wrong_exit_or_mode_is_blocked(self):
        fake = types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"status": mod.STATUS_RAW}),
            stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.verified_review, "checked_files",
                          return_value={"from": "disk"}), \
             patch.object(mod.sandbox, "inspect_sources",
                          return_value={"review_main": b"old"}), \
             patch.object(mod.verified_review, "verify_artifact",
                          return_value=(b"main", b"test", {})), \
             patch.object(mod.os, "readlink", return_value="net:[111]"), \
             patch.object(mod.shutil, "which", return_value="/mock/unshare"), \
             patch.object(mod.subprocess, "run", return_value=fake):
            result = mod.parent_run(pinned_review=True)
        self.assertEqual(result["status"], "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED")
        self.assertEqual(result["blocker"], "ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH")
        self.assertFalse(result["release_approved"])

    def test_pinned_review_cannot_claim_oauth_or_public_acceptance(self):
        self.assertIn("PINNED_REVIEW_HTTP", mod.STATUS_PINNED)
        self.assertNotIn("OAUTH", mod.STATUS_PINNED)
        self.assertNotIn("PUBLIC", mod.STATUS_PINNED)
        self.assertNotIn("DEPLOY", mod.STATUS_PINNED)

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
        self.assertEqual(report["blocker"],"ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH")

    def test_child_refuses_equal_parent_namespace(self):
        with patch.object(mod.os,"readlink",return_value="net:[111]"), \
             patch.object(mod.subprocess,"run",side_effect=AssertionError("ran")):
            with self.assertRaisesRegex(ValueError,"NETWORK_NAMESPACE_NOT_ISOLATED"):
                mod.require_own_namespace("net:[111]")

    def test_child_refuses_any_non_loopback_interface_before_ip_changes(self):
        with patch.object(mod.os,"readlink",side_effect=lambda path: "net:[222]" if path == "/proc/self/ns/net" else "net:[111]"), \
             patch.object(mod.socket,"if_nameindex",return_value=[(1,"lo"),(2,"eth0")]), \
             patch.object(mod.subprocess,"run",side_effect=AssertionError("ran")):
            with self.assertRaisesRegex(ValueError,"NON_LOOPBACK_INTERFACE"):
                mod.require_own_namespace("net:[111]")

    def test_init_namespace_matches_child_is_blocked_before_socket_access(self):
        with patch.object(mod.os, "readlink",
                          side_effect=lambda path: "net:[222]"), \
             patch.object(mod.socket, "if_nameindex",
                          side_effect=AssertionError("interfaces read")):
            with self.assertRaisesRegex(
                    ValueError, "PID1_NETWORK_NAMESPACE_NOT_ISOLATED"):
                mod.require_own_namespace("net:[111]")

    def test_parent_denies_wrong_mode_even_when_exit_zero(self):
        fake = types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"status": mod.STATUS_READY}),
            stderr="")
        with patch.object(mod.netns, "check_host",
                          return_value={"status": "ISOLATED_NETNS_PREFLIGHT_READY"}), \
             patch.object(mod.shutil, "which", return_value="/mock/unshare"), \
             patch.object(mod.os, "readlink", return_value="net:[111]"), \
             patch.object(mod.subprocess, "run", return_value=fake):
            report = mod.parent_run(edge_matrix=True)
        self.assertEqual(report["blocker"], "ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH")
        self.assertFalse(report["release_approved"])

    def test_report_status_is_not_production_approval(self):
        self.assertNotIn("PUBLIC", mod.STATUS_READY)
        self.assertNotIn("OAUTH", mod.STATUS_READY)
        self.assertNotIn("INSTALL", mod.STATUS_READY)

if __name__ == "__main__":
    unittest.main()
