import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml
import verify_ssh_boundary as gate

ROOT = Path(__file__).resolve().parent
SHA = "7d23ea686b7eca6e66619979357953a0a18fc366d4896f900ea6cae743b396d1"
MANIFEST = {"schema_version": 1, "approved_controller": {
    "path": "/usr/local/sbin/prp-release", "sha256": SHA}}
STALE = {"schema_version": 1, "state": "stale", "code": "STALE_DIAGNOSTIC",
         "stage": "unknown", "table": None, "exception": None, "timestamp_utc": None}


def response(code=0, out=b"", err=b""):
    return subprocess.CompletedProcess([], code, out, err)


class SSHBoundaryTests(unittest.TestCase):
    def runner(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[-1] == "controller-sha256":
            return response(out=(SHA + "  /usr/local/sbin/prp-release\n").encode())
        if args[-1] == "diagnose":
            return response(out=json.dumps(STALE).encode())
        if "-W" in args:
            return response(255, err=b"channel 0: open failed: administratively prohibited: open failed\nstdio forwarding failed\n")
        if "-R" in args:
            return response(255, err=b"Error: remote port forwarding failed for listen port 0\n")
        return response(2, err=gate.GATEWAY_DENIAL + b"\n")

    def setUp(self):
        self.calls = []

    def verifier(self, runner=None):
        return gate.Verifier("example.invalid", Path("/tmp/test-identity"), MANIFEST, runner or self.runner)

    def test_complete_gate_and_timeouts_without_shell_execution(self):
        self.verifier().verify()
        self.assertEqual(len(self.calls), 11)
        self.assertEqual(self.calls[0][0][-1], "controller-sha256")
        for args, kwargs in self.calls:
            self.assertEqual(kwargs["timeout"], 20)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertNotIn("shell", kwargs)
            self.assertIn("StrictHostKeyChecking=yes", args)
            self.assertIn("BatchMode=yes", args)
        self.assertIn("127.0.0.1:1", next(args for args, _ in self.calls if "-W" in args))

    def test_network_auth_and_hostkey_errors_are_not_permission_denials(self):
        cases = [(b"ssh: connect: Connection timed out", "CONNECTION_FAILED"),
                 (b"ssh: connect: Connection refused", "CONNECTION_FAILED"),
                 (b"ssh: Could not resolve hostname", "CONNECTION_FAILED"),
                 (b"Permission denied (publickey).", "AUTHENTICATION_FAILED"),
                 (b"Host key verification failed.", "HOST_KEY_FAILED")]
        for stderr, expected in cases:
            with self.subTest(expected=expected):
                def run(args, **kwargs):
                    if args[-1] == "sh":
                        return response(255, err=stderr)
                    return self.runner(args, **kwargs)
                with self.assertRaises(gate.BoundaryError) as raised:
                    self.verifier(run).verify()
                self.assertEqual(raised.exception.code, expected)

    def test_transport_text_cannot_be_hidden_in_a_denial_marker(self):
        def run(args, **kwargs):
            if args[-1] == "sh":
                return response(2, err=gate.GATEWAY_DENIAL + b"\nPermission denied (publickey).")
            return self.runner(args, **kwargs)
        with self.assertRaises(gate.BoundaryError) as raised:
            self.verifier(run).verify()
        self.assertEqual(raised.exception.code, "AUTHENTICATION_FAILED")

    def test_arbitrary_nonzero_without_gateway_marker_fails(self):
        def run(args, **kwargs):
            if args[-1] == "sh":
                return response(2, err=b"unknown failure")
            return self.runner(args, **kwargs)
        with self.assertRaises(gate.BoundaryError):
            self.verifier(run).verify()

    def test_accepted_shell_and_sftp_fail_closed(self):
        for index in ["sh", "-s"]:
            def run(args, **kwargs):
                if args[-1] == index or index in args:
                    return response()
                return self.runner(args, **kwargs)
            with self.subTest(index=index), self.assertRaises(gate.BoundaryError):
                self.verifier(run).verify()

    def test_connection_refusal_is_not_a_forwarding_permission_denial(self):
        for flag in ["-W", "-R"]:
            def run(args, **kwargs):
                if flag in args:
                    return response(255, err=b"channel 0: open failed: connect failed: Connection refused")
                return self.runner(args, **kwargs)
            with self.subTest(flag=flag), self.assertRaises(gate.BoundaryError) as raised:
                self.verifier(run).verify()
            self.assertEqual(raised.exception.code, "CONNECTION_FAILED")

    def test_forwarding_allowed_or_arbitrary_failure_is_rejected(self):
        for flag in ["-W", "-R"]:
            for result in [response(), response(255, err=b"unexpected failure")]:
                def run(args, **kwargs):
                    if flag in args:
                        return result
                    return self.runner(args, **kwargs)
                with self.subTest(flag=flag), self.assertRaises(gate.BoundaryError):
                    self.verifier(run).verify()

    def test_timeout_is_not_a_denial(self):
        for flag in ["sh", "-W", "-R"]:
            def run(args, **kwargs):
                if args[-1] == flag or flag in args:
                    raise subprocess.TimeoutExpired("ssh", 20)
                return self.runner(args, **kwargs)
            with self.subTest(flag=flag), self.assertRaises(gate.BoundaryError) as raised:
                self.verifier(run).verify()
            self.assertEqual(raised.exception.code, "TIMEOUT")

    def test_malformed_or_unavailable_diagnostic_fails(self):
        for data in [b"banner", b"[]", json.dumps({**STALE, "secret": "never-publish"}).encode(),
                     json.dumps({**STALE, "state": "unavailable"}).encode(),
                     json.dumps({**STALE, "table": "prp_arbitrary_secret"}).encode(),
                     json.dumps({**STALE, "schema_version": True}).encode()]:
            def run(args, **kwargs):
                if args[-1] == "diagnose":
                    return response(out=data)
                return self.runner(args, **kwargs)
            with self.subTest(data=data), self.assertRaises(gate.BoundaryError):
                self.verifier(run).verify()

    def test_manifest_mismatch_stops_before_other_commands(self):
        def run(args, **kwargs):
            self.calls.append((args, kwargs))
            return response(out=("0"*64+"  /usr/local/sbin/prp-release\n").encode())
        with self.assertRaises(gate.BoundaryError):
            self.verifier(run).verify()
        self.assertEqual(len(self.calls), 1)

    def test_ssh_stderr_never_reaches_console(self):
        def run(args, **kwargs):
            return response(255, err=b"Permission denied (publickey). PRIVATE_TOKEN_MUST_NOT_APPEAR")
        verifier = self.verifier(run)
        output = io.StringIO()
        with patch.object(gate, "Verifier", return_value=verifier), \
             patch.object(sys, "argv", ["verify", "--host", "example.invalid", "--identity", "test", "--manifest", str(ROOT/'controller-manifest.json')]), \
             contextlib.redirect_stdout(output):
            self.assertEqual(gate.main(), 1)
        self.assertNotIn("PRIVATE_TOKEN", output.getvalue())
        self.assertIn("AUTHENTICATION_FAILED", output.getvalue())

    def test_workflow_gate_is_blocking_and_after_checkout_before_production(self):
        path = ROOT.parents[1]/'.github/workflows/deploy-prp.yml'
        workflow = yaml.safe_load(path.read_text())
        steps = workflow['jobs']['publish']['steps']
        names = [s.get('name') for s in steps]
        gate_step = next(s for s in steps if 'verify_ssh_boundary.py' in s.get('run',''))
        i = steps.index(gate_step)
        self.assertLess(names.index('Checkout controller manifest for the exact release commit'), i)
        self.assertLess(names.index('Configure restricted deployment identity'), i)
        self.assertLess(i, names.index('Deploy or operate production'))
        self.assertFalse(gate_step.get('continue-on-error',False))
        self.assertNotIn('always()',gate_step.get('if',''))
        self.assertNotIn('|| true',gate_step['run'])
        self.assertIn('set -euo pipefail',gate_step['run'])
        self.assertNotIn("inputs.action == 'check'",gate_step['if'])
        operation = next(s for s in steps if s.get('id')=='production_operation')
        self.assertNotIn('always()',operation.get('if',''))
        self.assertFalse(operation.get('continue-on-error',False))


if __name__ == '__main__':
    unittest.main()
