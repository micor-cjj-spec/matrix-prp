"""Offline regression for pinned Keycloak backup/readiness preflight.

No Docker access, live Realm, backup, credentials, network or DB touched.
"""
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(__file__).with_name("preflight_restored_realm_host.sh")
BEGIN = "# Keycloak may print JAVA_OPTS information before the version line."
END = "echo '=== READ ONLY: BACKUP INTEGRITY ==='"


class PinnedRestoredRealmPreflightTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(self.source.count(BEGIN), 1)
        self.assertEqual(self.source.count(END), 1)
        self.version_snippet = self.source.split(BEGIN, 1)[1].split(END, 1)[0]

    def test_full_script_syntax_and_preserves_all_checks(self):
        subprocess.run(["bash", "-n", str(SOURCE)], check=True)
        for required in ("PINNED_POSTGRES_DUMP=PASS",
                         "PINNED_POSTGRES_DUMP=FAIL",
                         "READ_ONLY_PREFLIGHT_COMPLETE=YES",
                         "=== READ ONLY: HOST BUILD AND ARTIFACT OPTIONS ===",
                         "=== READ ONLY: RESOURCES / RESIDUES ==="):
            self.assertIn(required, self.source)
        self.assertEqual(self.source.count("/opt/keycloak/bin/kc.sh --version"), 1)
        self.assertNotIn("| head -n 2", self.version_snippet)
        self.assertNotIn("docker run", self.version_snippet)
        self.assertNotIn("docker restart", self.version_snippet)
        self.assertNotIn("kcadm", self.version_snippet)

    def run_version_fixture(self, simulated_stdout, rc=0):
        # A fake *shell function*, not a real Docker process. Prints test
        # fixture to stdout, not credentials from a host.
        quoted = "'"+simulated_stdout.replace("'", "'\\''")+"'"
        setup = (
            "set -Eeuo pipefail\n"
            'LIVE_KC=synthetic-only\n'
            "docker() { printf '%s' "+quoted+"; return "+str(rc)+"; }\n"
        )
        cmd = setup + BEGIN + self.version_snippet + "\necho AFTER_PREFLIGHT_VERSION=YES\n"
        return subprocess.run(["bash", "-c", cmd], capture_output=True,
                              text=True, check=False, timeout=5)

    def test_multiline_keycloak_output_does_not_stop_pipefail(self):
        res = self.run_version_fixture(
            "JAVA_OPTS_KC_HEAP already set in environment; overriding default settings\n"
            "Keycloak 26.8.0\n"
            "SYNTHETIC_UNTRUSTED_EXTRA_LINE\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("KEYCLOAK_VERSION=26.8.0", res.stdout)
        self.assertIn("AFTER_PREFLIGHT_VERSION=YES", res.stdout)
        self.assertNotIn("JAVA_OPTS", res.stdout)
        self.assertNotIn("SYNTHETIC_UNTRUSTED_EXTRA_LINE", res.stdout)

    def test_missing_and_failed_version_does_not_prevent_backup_review(self):
        for version, rc in (("untrusted server log only\n", 0),
                            ("Keycloak 26.8.0\n", 1)):
            with self.subTest(version=version, rc=rc):
                res = self.run_version_fixture(version, rc)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn("KEYCLOAK_VERSION=UNVERIFIED", res.stdout)
                self.assertIn("AFTER_PREFLIGHT_VERSION=YES", res.stdout)
                self.assertNotIn("untrusted server log", res.stdout)

if __name__ == "__main__":
    unittest.main()
