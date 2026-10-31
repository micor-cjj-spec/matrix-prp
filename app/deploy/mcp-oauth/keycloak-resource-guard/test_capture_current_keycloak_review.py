"""Offline contract: opt-in live-stage pg_dump capture is not a B2 receipt.

Tests never run the capture path or connect to Docker/PostgreSQL/Keycloak.
"""
from pathlib import Path
import os
import subprocess
import unittest

SOURCE = Path(__file__).with_name("capture_current_keycloak_review.sh")


class CaptureCurrentKeycloakReviewTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")

    def test_script_parses_and_has_fixed_nonproduction_scope(self):
        subprocess.run(["bash", "-n", str(SOURCE)], check=True)
        self.assertIn("DB=prp-mcp-oauth-stage-auth-db-1", self.source)
        self.assertIn("KEYCLOAK=prp-mcp-oauth-stage-keycloak-1", self.source)
        self.assertIn("ROOT=/root/prp-mcp-backups", self.source)
        self.assertIn('mktemp -d "$ROOT/keycloak-current-review-XXXXXXXX"', self.source)
        self.assertIn('pg_dump -w -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"', self.source)
        self.assertIn('docker exec -i "$DB" pg_restore --list', self.source)
        self.assertIn("G0_B2_INSTALL_PERMITTED=NO", self.source)
        self.assertIn("B2_RECEIPTS_ISSUED=NO", self.source)
        self.assertIn("CURRENT_KEYCLOAK_RESTORED=NO", self.source)
        self.assertIn("CURRENT_KEYCLOAK_SIGNING_KEYS_CLONE_VERIFIED=NO", self.source)
        self.assertIn("set -Eeuo pipefail", self.source)
        self.assertIn("umask 077", self.source)
        self.assertIn("02", self.source)  # mode/permissions masks fail closed

    def test_refuses_without_exact_capture_flag_before_any_privilege(self):
        for args in ([], ["--help"], ["--capture"], ["--capture-current", "extra"]):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(SOURCE), *args],
                                        capture_output=True, text=True,
                                        check=False, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn("EXPLICIT_CAPTURE_CURRENT_REQUIRED", result.stdout)
                self.assertNotIn("PRIVATE_BACKUP_PATH", result.stdout)

    @unittest.skipIf(os.geteuid() == 0, "nonroot guard requires nonroot runner")
    def test_explicit_capture_rejects_nonroot_before_docker(self):
        result = subprocess.run(["bash", str(SOURCE), "--capture-current"],
                                capture_output=True, text=True, check=False,
                                timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("AUTHORIZED_ROOT_OPERATOR_REQUIRED", result.stdout)

    def test_no_install_no_container_restart_no_arbitrary_delete(self):
        for forbidden in (
            "docker run", "docker stop", "docker restart", "docker rm",
            "docker compose", "systemctl restart", "kubectl", "kcadm",
            "pg_restore -d", "psql -c", "ALTER ", "DROP ", "INSERT ",
            "UPDATE ", "DELETE ", "rm -rf", "chown -R", "chmod -R",
            "approved-install.safe.json", "fresh-b2-restore.safe.json",
            "curl ", "wget ", "mysql ", "git reset",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_no_credential_echo_and_backup_protection(self):
        self.assertIn('chmod 0600 -- "$DUMP"', self.source)
        self.assertIn('stat -c \'%a\' -- "$DEST"', self.source)
        self.assertIn('OWNER', self.source.upper())
        self.assertIn('if (( (8#$mode & 0022) != 0 )); then', self.source)
        self.assertNotIn("printenv", self.source)
        self.assertNotIn("docker inspect -f '{{.Config.Env}}'", self.source)
        self.assertNotIn("echo \"$POSTGRES_PASSWORD", self.source)
        self.assertIn("pg-dump-error.private", self.source)
        self.assertIn('COMPLETE=0', self.source)
        self.assertIn('COMPLETE=1', self.source)


if __name__ == "__main__":
    unittest.main()
