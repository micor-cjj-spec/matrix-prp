import copy
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import probe_sftp_init
import test_ssh_boundary as fixtures
import verify_ssh_boundary as gate


class CorrelatedProductionGateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SSHBoundaryTests()
        self.fixture.setUp()
        self.v = self.fixture.verifier()
        self.v.manifest = copy.deepcopy(fixtures.MANIFEST)

    def change_proof(self, change):
        original = self.v.runner
        def run(args, **kwargs):
            if args[-1] == "diagnose" and len(kwargs.get("input", b"")) == 32:
                d = fixtures.policy_response(kwargs["input"])
                change(d)
                return fixtures.response(out=json.dumps(d).encode())
            return original(args, **kwargs)
        self.v.runner = run

    def assert_blocked(self, code=None):
        with self.assertRaises(gate.BoundaryError) as raised:
            self.v.verify()
        if code:
            self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_confirmed_openssh_suppressed_stderr_requires_complete_live_correlation(self):
        original = self.v.runner
        def run(args, **kwargs):
            if "-s" in args:
                return fixtures.response(2)  # Real observed subsystem result; no marker.
            return original(args, **kwargs)
        self.v.runner = run
        self.v.verify()
        self.assertEqual(self.v.sftp_verdict, "SFTP_DENIED_BY_FORCED_GATEWAY")
        probes = [(a, kw) for a, kw in self.fixture.calls if kw.get("input") == probe_sftp_init.INIT]
        # The subsystem runner above is separate; the exact exec is definitely exercised.
        self.assertEqual(probes[0][0][-1], "/usr/lib/openssh/sftp-server")

    def test_explicit_gateway_refusal_also_passes_complete_correlation(self):
        self.v.verify()
        self.assertEqual(self.v.sftp_verdict, "SFTP_DENIED_BY_FORCED_GATEWAY")

    def test_actual_production_manifest_is_intentionally_not_a_live_proof(self):
        manifest = Path(__file__).with_name("controller-manifest.json")
        self.v.manifest = json.loads(manifest.read_text(encoding="utf-8"))
        self.assert_blocked("SSH_POLICY_BASELINE_MISSING")
        self.assertFalse(any("-s" in args for args, _ in self.fixture.calls))

    def test_existing_server_diagnostic_without_policy_is_rejected(self):
        original = self.v.runner
        def run(args, **kwargs):
            if args[-1] == "diagnose":
                return fixtures.response(out=json.dumps(fixtures.STALE).encode())
            return original(args, **kwargs)
        self.v.runner = run
        self.assert_blocked("SSH_POLICY_PROOF_UNAVAILABLE")

    def test_each_gateway_key_configuration_binary_or_mapping_drift_blocks(self):
        for field in fixtures.POLICY:
            with self.subTest(field=field):
                self.setUp()
                self.change_proof(lambda d: d["ssh_policy"]["baseline"].__setitem__(field, "drift"))
                self.assert_blocked("SSH_POLICY_DRIFT")

    def test_nonce_replay_stale_clock_and_unverified_loaded_policy_block(self):
        changes = [
            (lambda p: p.__setitem__("challenge", "0"*64), "SSH_POLICY_CHALLENGE_MISMATCH"),
            (lambda p: p.__setitem__("observed_utc", "2000-01-01T00:00:00Z"), "SSH_POLICY_PROOF_STALE"),
        ]
        for field in ["connection_bound", "loaded_policy_verified", "trusted_paths"]:
            changes.extend([(lambda p, f=field: p.__setitem__(f, False), "SSH_POLICY_RUNTIME_UNVERIFIED"),
                            (lambda p, f=field: p.__setitem__(f, 1), "SSH_POLICY_RUNTIME_UNVERIFIED")])
        for change, code in changes:
            with self.subTest(code=code):
                self.setUp()
                self.change_proof(lambda d: change(d["ssh_policy"]))
                self.assert_blocked(code)

    def mutate_exchange(self, mutate, command_only=False):
        original = self.v.sftp_exchange
        def exchange(command=None):
            result = original(command)
            if (command is not None) == command_only:
                mutate(result)
            return result
        self.v.sftp_exchange = exchange

    def test_real_version_or_any_other_protocol_output_always_blocks(self):
        for out in [struct.pack(">IBI", 5, 2, 3), struct.pack(">IBI", 5, 101, 0), b"unrecognized bytes"]:
            with self.subTest(out_size=len(out)):
                self.setUp()
                original = self.v.runner
                def run(args, **kwargs):
                    if "-s" in args:
                        return fixtures.response(2, out=out)
                    return original(args, **kwargs)
                self.v.runner = run
                self.assert_blocked("SFTP_ACCESSIBLE" if out[4:5] == b"\x02" else "SFTP_UNEXPECTED_OUTPUT")

    def test_exec_rejection_alone_wrong_exit_or_forged_marker_is_insufficient(self):
        for mutate in [lambda r: r.__setitem__("exit_code", 0),
                       lambda r: r.__setitem__("exit_code", 255),
                       lambda r: r.__setitem__("subsystem_request_accepted", False),
                       lambda r: r.__setitem__("category", "UNKNOWN_ERROR"),
                       lambda r: r.__setitem__("authenticated_publickey", False)]:
            with self.subTest(mutate=mutate.__name__):
                self.setUp()
                self.mutate_exchange(mutate)
                self.assert_blocked()
        self.setUp()
        self.mutate_exchange(lambda r: r.__setitem__("gateway_denial", False), command_only=True)
        self.assert_blocked("SFTP_EXACT_COMMAND_NOT_DENIED")

    def test_auth_hostkey_network_timeout_limit_and_missing_fields_block_both_exchanges(self):
        for field in ["authentication_error", "host_key_error", "network_error", "timed_out", "output_limited"]:
            for exact in [True, False]:
                with self.subTest(field=field, exact=exact):
                    self.setUp()
                    self.mutate_exchange(lambda r: r.__setitem__(field, True), command_only=exact)
                    self.assert_blocked()
        self.setUp()
        self.mutate_exchange(lambda r: r.pop("version_response"))
        self.assert_blocked("SFTP_EVIDENCE_INCOMPLETE")

    def test_error_output_never_contains_proof_remote_rows_or_tokens(self):
        self.change_proof(lambda d: d["ssh_policy"]["baseline"].__setitem__("gateway_sha256", "PRIVATE_TOKEN_PERSONAL_ROW"))
        output = io.StringIO()
        with patch.object(gate, "Verifier", return_value=self.v), patch.object(sys, "argv", [
            "verify", "--host", "example.invalid", "--identity", "test", "--manifest",
            str(Path(__file__).with_name("controller-manifest.json"))]), contextlib.redirect_stdout(output):
            self.assertEqual(gate.main(), 1)
        self.assertNotIn("PRIVATE_TOKEN", output.getvalue())
        self.assertIn("SSH_POLICY_DRIFT", output.getvalue())

    def test_forwarding_refusals_still_use_production_path_and_fail_closed(self):
        for flag in ["-W", "-R"]:
            self.setUp()
            original = self.v.runner
            def run(args, **kwargs):
                if flag in args:
                    return fixtures.response(255, err=b"Connection refused")
                return original(args, **kwargs)
            self.v.runner = run
            self.assert_blocked("CONNECTION_FAILED")


if __name__ == "__main__":
    unittest.main()
