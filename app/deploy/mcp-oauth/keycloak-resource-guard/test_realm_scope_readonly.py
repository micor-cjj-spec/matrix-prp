"""Static no-write contract for the Keycloak PostgreSQL G0 preflight."""
from pathlib import Path
import re
import unittest


SQL = Path(__file__).with_name("realm_scope_readonly.sql").read_text(encoding="utf-8")


class RealmScopeInventorySafetyTests(unittest.TestCase):
    def test_only_selects_inside_transaction_read_only(self):
        # Comments are advisory, not trusted as an executable safety check.
        code = "\n".join(line for line in SQL.splitlines()
                         if not line.lstrip().startswith("--")).strip()
        statements = [part.strip() for part in code.split(";") if part.strip()]
        self.assertEqual(statements[0].upper(), "BEGIN TRANSACTION READ ONLY")
        self.assertEqual(statements[-1].upper(), "COMMIT")
        self.assertEqual(len(statements), 6)
        for query in statements[1:-1]:
            self.assertRegex(query.upper(), r"^(SELECT|WITH)\b")
        self.assertNotRegex(code.upper(),
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|COPY|GRANT|REVOKE|DO|CALL|EXECUTE)\b")
        self.assertNotIn("\\", code)  # no psql meta-commands

    def test_no_secret_or_user_identifiers_in_output(self):
        code = "\n".join(line for line in SQL.splitlines()
                         if not line.lstrip().startswith("--")).lower()
        # The only projection aliases are safe inventory fields.
        self.assertEqual(code.count(" as check_name"), 4)
        self.assertEqual(code.count(" as observed"), 4)
        for field in ("username", "email", "password", "secret",
                      "credential", "private_key", "access_token", "refresh_token"):
            self.assertNotIn(field, code)

    def test_fixed_realm_two_clients_and_three_scopes(self):
        for expected in ("'prp-mcp'", "'basic'", "'offline_access'",
                         "'prp.tasks.read'",
                         "'https://chatgpt.com/oauth/client.json'",
                         "'prp-first-party-link'"):
            self.assertIn(expected, SQL)
        self.assertIn("FROM realm", SQL)
        self.assertIn("LEFT JOIN client_scope", SQL)
        self.assertIn("LEFT JOIN client c", SQL)


if __name__ == "__main__":
    unittest.main()
