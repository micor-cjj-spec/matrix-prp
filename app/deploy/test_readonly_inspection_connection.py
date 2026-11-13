"""Synthetic, offline regression for PRP's production-inspect SSH input gate.

Never attempts SSH/network, accesses GitHub secrets or modifies a host.
"""
import contextlib
from io import StringIO
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import preflight_readonly_inspection_env as guard


class InspectionConnectionGuardTests(unittest.TestCase):
    def test_unset_and_newline_only_secrets_cannot_be_valid(self):
        for values in ({}, {
            "INSPECT_KEY": "",
            "INSPECT_KNOWN_HOSTS": "",
            "INSPECT_HOST": "",
        }, {
            "INSPECT_KEY": "\n",
            "INSPECT_KNOWN_HOSTS": "\n",
            "INSPECT_HOST": "\n",
        }):
            self.assertFalse(guard.check(values))
        with patch.dict(os.environ, {
            "INSPECT_KEY": "",
            "INSPECT_KNOWN_HOSTS": "",
            "INSPECT_HOST": "",
        }, clear=True), contextlib.redirect_stderr(StringIO()) as err:
            self.assertEqual(guard.main(), 2)
            self.assertNotIn("PRIVATE", err.getvalue())
            self.assertEqual(err.getvalue().strip(),
                             "INSPECTION_CONNECTION_CONFIG_MISSING_OR_INVALID")

    def test_host_does_not_accept_shell_metacharacters_or_unsafe_whitespace(self):
        for bad in ("", " ", "\n", "-oProxyCommand=evil",
                    "example.test;id", "host/../other", "host:22",
                    "foo..bar", "host @ other", "0.0.0.0", "[::1]"):
            self.assertFalse(guard.valid_host(bad), bad)
        for good in ("prp-inspect.example.test", "192.0.2.18", "::1"):
            self.assertTrue(guard.valid_host(good), good)

    def test_malformed_or_mismatched_private_key_markers_rejected(self):
        for bad in ("", "\n", "ssh-ed25519 AAAA fake", "PRIVATE",
                    "-----BEGIN OPENSSH PRIVATE KEY-----" + "A" * 200
                    + "-----END PRIVATE KEY-----"):
            self.assertFalse(guard.valid_private_key(bad))
        fake_key = ("-----BEGIN OPENSSH PRIVATE KEY-----\n"
                    + "A" * 180
                    + "\n-----END OPENSSH PRIVATE KEY-----")
        # Format-only preflight is deliberately not sufficient;
        # ssh-keygen -y -P '' verifies the actual private key afterward.
        self.assertTrue(guard.valid_private_key(fake_key))
        self.assertFalse(guard.check({
            "INSPECT_KEY": fake_key,
            "INSPECT_KNOWN_HOSTS": "",
            "INSPECT_HOST": "prp-inspect.example.test",
        }))

    def test_ephemeral_ssh_key_and_host_pin_can_be_validated_offline(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            key = folder / "synthetic_ed25519"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519",
                            "-N", "", "-f", str(key)],
                           check=True, capture_output=True, timeout=15)
            private = key.read_text()
            public = key.with_suffix(".pub").read_text().split()
            self.assertTrue(guard.check({
                "INSPECT_KEY": private,
                "INSPECT_KNOWN_HOSTS": "prp-inspect.example.test "
                                       + public[0] + " " + public[1],
                "INSPECT_HOST": "prp-inspect.example.test",
            }))
            pin = folder / "known_hosts"
            pin.write_text("prp-inspect.example.test " + public[0]
                           + " " + public[1] + "\n")
            key_check = subprocess.run(
                ["ssh-keygen", "-y", "-P", "", "-f", str(key)],
                capture_output=True, timeout=10, check=False)
            self.assertEqual(key_check.returncode, 0)
            host_check = subprocess.run(
                ["ssh-keygen", "-F", "prp-inspect.example.test", "-f", str(pin)],
                capture_output=True, timeout=10, check=False)
            self.assertEqual(host_check.returncode, 0)
            wrong = subprocess.run(
                ["ssh-keygen", "-F", "wrong-host.example.test", "-f", str(pin)],
                capture_output=True, timeout=10, check=False)
            self.assertNotEqual(wrong.returncode, 0)

    def test_github_workflow_must_guard_before_files_or_ssh_and_remain_manual_main_only(self):
        source = (Path(__file__).resolve().parents[2]
                  / ".github/workflows/prp-readonly-inspect.yml").read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("github.ref == 'refs/heads/main'", source)
        self.assertIn("environment: production-inspect", source)
        gate = "python3 app/deploy/preflight_readonly_inspection_env.py"
        create = 'mkdir -p "$HOME/.ssh"'
        request = "timeout 30s ssh -i"
        self.assertIn(gate, source)
        self.assertLess(source.index(gate), source.index(create))
        self.assertLess(source.index(gate), source.index(request))
        self.assertIn("ssh-keygen -y -P ''", source)
        self.assertIn('ssh-keygen -F "$INSPECT_HOST"', source)
        self.assertIn("StrictHostKeyChecking=yes", source)
        self.assertIn("PRP_INSPECT_HOST", source)
        self.assertNotIn("printf '%s\\n' \"$INSPECT_KEY\"", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("python3 app/deploy/validate_inspection.py", source)


if __name__ == "__main__":
    unittest.main()
