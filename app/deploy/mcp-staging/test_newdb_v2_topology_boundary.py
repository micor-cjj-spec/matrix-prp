"""Prevents conflating old V2's read-only OAuth route and fresh NewDB lab.

This deliberately does NOT introduce an installation option, change a
public route, enable OAuth, or grant deployment permissions.
"""
from pathlib import Path
import unittest

from approval_routes_pending import render_readonly_link_routes

ROOT = Path(__file__).resolve().parent
NEWDB = ROOT / "compose.newdb.review.yaml"
G0_DECISION = ROOT / "G0-NEWDB-V2-TOPOLOGY-DECISION-20261027.md"


class NewdbV2NoImplicitPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = NEWDB.read_text(encoding="utf-8")
        cls.v2_route = render_readonly_link_routes()
        cls.decision = G0_DECISION.read_text(encoding="utf-8")

    def test_existing_first_party_review_routes_remain_v2_only(self):
        # These snippets have no authority to touch the new 18083 project.
        self.assertEqual(self.v2_route.count(
            "proxy_pass http://127.0.0.1:18082;"), 18)
        self.assertNotIn("proxy_pass http://127.0.0.1:18083;", self.v2_route)
        self.assertNotIn("proxy_pass http://127.0.0.1:18081;", self.v2_route)
        with self.assertRaises(ValueError):
            render_readonly_link_routes(port=18083)

    def test_newdb_review_cannot_replace_v2_or_legacy_port(self):
        self.assertIn('name: prp-mcp-newdb-review', self.review)
        self.assertIn('"127.0.0.1:18083:8080"', self.review)
        self.assertNotIn("127.0.0.1:18082:8080", self.review)
        self.assertNotIn("127.0.0.1:18081:8080", self.review)
        self.assertIn("matrix_prp_mcp_newdb_review", self.review)
        self.assertNotIn("matrix_prp_mcp_stage", self.review)
        self.assertIn("newdb_mysql:/var/lib/mysql", self.review)
        self.assertNotIn("stage_mysql:/var/lib/mysql", self.review)
        self.assertNotIn("prp-mcp-v2", self.review)
        self.assertIn('profiles: ["newdb-review"]', self.review)

    def test_first_party_and_every_data_grant_stays_disabled_in_review(self):
        for env in (
            "MATRIX_PRP_MCP_ENABLED",
            "MATRIX_PRP_MCP_OAUTH_ENABLED",
            "MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED",
            "MATRIX_PRP_MCP_WRITE_ENABLED",
        ):
            self.assertIn(env + ': "false"', self.review)

    def test_release_decision_expressly_separates_newdb_and_real_data(self):
        for required in (
            "G0-A", "G0-B/B2", "G0-C",
            "127.0.0.1:18082", "127.0.0.1:18083",
            "existing PRP", "newdb-review",
            "NO-GO", "not a deployment instruction",
        ):
            self.assertIn(required.lower(), self.decision.lower())

    def test_review_routes_no_backend_write_or_mcp_data_wildcards(self):
        self.assertNotIn("location ^~ /api/", self.v2_route)
        self.assertNotIn("location = /api/mcp {", self.v2_route)
        self.assertNotIn("location = /api/finance", self.v2_route)


if __name__ == "__main__":
    unittest.main()
