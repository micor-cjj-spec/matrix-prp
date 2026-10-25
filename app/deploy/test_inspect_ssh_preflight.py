"""No-network regression tests for manual production inspection prerequisites."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from inspect_ssh_preflight import prepare, valid_host


class InspectionSSHPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.identity = self.root / "config" / "prp_inspect"
        self.known_hosts = self.root / "config" / "known_hosts"

    def check(self, values):
        return prepare(values, self.identity, self.known_hosts)

    def test_missing_secrets_fail_before_creating_files(self):
        self.assertEqual(self.check({}), "INSPECT_KEY_MISSING")
        self.assertEqual(self.check({"PRP_INSPECT_SSH_KEY": "  \n"}),
                         "INSPECT_KEY_MISSING")
        self.assertEqual(self.check({"PRP_INSPECT_SSH_KEY": "dummy"}),
                         "INSPECT_KNOWN_HOSTS_MISSING")
        self.assertEqual(self.check({"PRP_INSPECT_SSH_KEY": "dummy",
                                     "PRP_INSPECT_KNOWN_HOSTS": "dummy"}),
                         "INSPECT_HOST_MISSING")
        self.assertFalse(self.identity.exists())

    def test_host_value_must_be_a_bare_hostname_or_address(self):
        for value in ("", " ", "-evil", "host/path", "user@host",
                      "host:22", "host\nINJECT", "host;exit", "host..bad"):
            self.assertFalse(valid_host(value), value)
        self.assertTrue(valid_host("example.test"))
        self.assertTrue(valid_host("192.0.2.10"))
        self.assertEqual(self.check({
            "PRP_INSPECT_SSH_KEY": "dummy",
            "PRP_INSPECT_KNOWN_HOSTS": "dummy",
            "PRP_INSPECT_HOST": "user@badhost",
        }), "INSPECT_HOST_INVALID")
        self.assertFalse(self.identity.exists())

    def make_key(self):
        base = self.root / "ephemeral_ed25519"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                        "-f", str(base)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return base.read_text(), (base.parent / (base.name + ".pub")).read_text().strip()

    def test_valid_disposable_key_and_matching_host_pin(self):
        key, pub = self.make_key()
        outcome = self.check({
            "PRP_INSPECT_SSH_KEY": key,
            "PRP_INSPECT_KNOWN_HOSTS": "example.test " + pub + "\n",
            "PRP_INSPECT_HOST": "example.test",
        })
        self.assertEqual(outcome, "INSPECT_PREFLIGHT_VALID")
        self.assertEqual(self.identity.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.known_hosts.stat().st_mode & 0o777, 0o600)

    def test_unparseable_private_key_is_rejected(self):
        key, pub = self.make_key()
        self.assertEqual(self.check({
            "PRP_INSPECT_SSH_KEY": "not a private key",
            "PRP_INSPECT_KNOWN_HOSTS": "example.test " + pub,
            "PRP_INSPECT_HOST": "example.test",
        }), "INSPECT_KEY_INVALID")

    def test_known_hosts_must_pin_the_exact_inspection_host(self):
        key, pub = self.make_key()
        self.assertEqual(self.check({
            "PRP_INSPECT_SSH_KEY": key,
            "PRP_INSPECT_KNOWN_HOSTS": "different.example " + pub,
            "PRP_INSPECT_HOST": "example.test",
        }), "INSPECT_HOST_KEY_NOT_PINNED")

    def test_secret_files_are_never_overwritten(self):
        key, pub = self.make_key()
        self.identity.parent.mkdir()
        self.identity.write_text("preserve existing file")
        result = self.check({
            "PRP_INSPECT_SSH_KEY": key,
            "PRP_INSPECT_KNOWN_HOSTS": "example.test " + pub,
            "PRP_INSPECT_HOST": "example.test",
        })
        self.assertEqual(result, "INSPECT_FILESYSTEM_UNAVAILABLE")
        self.assertEqual(self.identity.read_text(), "preserve existing file")


if __name__ == "__main__":
    unittest.main()
