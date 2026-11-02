"""Offline safety contract: pinned Git-object Keycloak SQL review wrapper."""
from pathlib import Path
import subprocess
import unittest

SCRIPT = (Path(__file__).resolve().parent / "keycloak-resource-guard"
          / "live_exact_client_readonly.sh")
SQL = (Path(__file__).resolve().parent / "keycloak-resource-guard"
       / "realm_scope_readonly.sql")


class KeycloakClientReviewReadOnlyTests(unittest.TestCase):
    def test_script_bash_syntax_and_only_expected_targets(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("prp-mcp-oauth-stage-auth-db-1", src)
        self.assertIn("realm_scope_readonly.sql", src)
        self.assertIn("PIN=$1", src)
        self.assertIn("^[0-9a-f]{40}$", src)
        self.assertIn('git -C "$REPO" show "$PIN:$SQL"', src)
        self.assertIn('exec psql -X -q -v ON_ERROR_STOP=1 -w -U "$POSTGRES_USER"', src)
        self.assertIn('-d "$POSTGRES_DB" -A -t -F "="', src)
        self.assertIn('KEYCLOAK_PG_CONNECTION_CONFIG=UNAVAILABLE', src)
        self.assertIn('docker exec -i "$PG" sh -ec', src)
        self.assertNotIn("-U keycloak -d keycloak", src)
        self.assertNotIn("docker inspect -f '{{.Config.Env}}'", src)
        self.assertNotIn("env |", src)
        self.assertNotIn("printenv", src)
        self.assertNotIn("POSTGRES_PASSWORD", src)
        self.assertIn("MCP_DEPLOYMENT_PERMITTED=NO", src)
        self.assertIn("set -Eeuo pipefail", src)
        self.assertIn("KEYCLOAK_PG_CONTAINER=NOT_RUNNING", src)
        self.assertNotIn("docker compose", src)
        self.assertNotIn("docker run", src)
        self.assertNotIn("kcadm.sh", src)
        self.assertNotIn("MYSQL_PWD", src)
        for forbidden in ("docker rm", "docker stop", "docker restart", "systemctl",
                          "chown ", "chmod ", "nginx -s", "curl -k", "ssh -o"):
            self.assertNotIn(forbidden, src)

    def test_inner_shell_syntax_and_missing_role_fails_before_psql(self):
        src = SCRIPT.read_text(encoding="utf-8")
        fragment = src.split("docker exec -i \"$PG\" sh -ec '", 1)[1].split("\n  '\n", 1)[0]
        subprocess.run(["sh", "-n"], input=fragment, text=True,
                       capture_output=True, check=True)
        import os
        env = dict(os.environ)
        env.pop("POSTGRES_USER", None)
        env.pop("POSTGRES_DB", None)
        result = subprocess.run(["sh", "-ec", fragment], env=env,
                                text=True, capture_output=True, check=False,
                                timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("KEYCLOAK_PG_CONNECTION_CONFIG=UNAVAILABLE", result.stderr)
        self.assertNotIn("password", result.stdout.lower())

    def test_sql_only_fixed_public_count_and_status_fields(self):
        src = SQL.read_text(encoding="utf-8")
        executable = "\n".join(line for line in src.splitlines()
                               if not line.lstrip().startswith("--"))
        statements = [x.strip() for x in executable.split(";") if x.strip()]
        self.assertEqual(statements[0].upper(), "BEGIN TRANSACTION READ ONLY")
        self.assertEqual(statements[-1].upper(), "COMMIT")
        self.assertEqual(len(statements), 6)
        self.assertEqual(executable.count(" AS check_name"), 4)
        self.assertEqual(executable.count(" AS observed"), 4)
        self.assertIn("'https://chatgpt.com/oauth/client.json'", executable)
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "GRANT ",
                          "COPY ", "CREATE ", "DO $$", "EXECUTE ", "SELECT *"):
            self.assertNotIn(forbidden, executable.upper())

    def test_missing_sha_is_rejected_before_docker(self):
        for arg in ("", "HEAD", "main", "1" * 39, "g" * 40):
            with self.subTest(arg=arg):
                proc = subprocess.run(
                    ["bash", str(SCRIPT), arg], capture_output=True,
                    text=True, check=False, timeout=5)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout.strip(), "REVIEW_PIN_REQUIRED_40_LOWERCASE_HEX")
                self.assertNotIn("PASSWORD", proc.stdout)

if __name__ == "__main__":
    unittest.main()
