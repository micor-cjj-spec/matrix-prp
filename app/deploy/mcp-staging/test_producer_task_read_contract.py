"""Source/manifest contract for a DISABLED future production task-read bridge.

No API server, outbound network, database, Keycloak or user tokens.
This test MUST NOT itself create or authorize the proposed endpoint.
"""
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path(__file__).resolve().parent / "producer_task_read.review.json"
JAVA = ROOT / "backend/src/main/java/com/matrix/prp"


def java(path):
    return (JAVA / path).read_text(encoding="utf-8")


class ProducerTaskReadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = json.loads(REVIEW.read_text(encoding="utf-8"))

    def test_review_only_no_implicit_deployment_or_enabled_route(self):
        c = self.c
        self.assertEqual(c["status"], "REVIEW_ONLY_NOT_AUTHORIZED_NOT_IMPLEMENTED")
        self.assertIs(c["authority"]["deployment_permitted"], False)
        self.assertIs(c["authority"]["github_ci_can_approve"], False)
        self.assertEqual(c["authority"]["g0_b2"], "NO_GO")
        self.assertEqual(c["authority"]["real_chatgpt_tasks"], "NOT_CONNECTED")
        self.assertIs(c["transport"]["feature_default_off"], True)
        self.assertIs(c["transport"]["no_active_ingress_change"], True)
        self.assertIs(c["transport"]["no_direct_mysql_cross_connection"], True)
        self.assertIs(c["transport"]["no_generic_api_proxy"], True)
        self.assertIs(c["transport"]["mcp_write_disabled"], True)

    def test_exact_get_only_private_internal_candidate(self):
        ep = self.c["candidate_endpoint"]
        self.assertEqual(ep["path"], "/internal/mcp/tasks")
        self.assertEqual(ep["method"], "GET")
        self.assertEqual(ep["allowed_methods"], ["GET"])
        self.assertIs(ep["public_ingress"], False)
        self.assertEqual(ep["max_records"], 20)
        self.assertEqual(ep["request_parameters"]["limit"]["max"], 20)
        self.assertGreaterEqual(ep["request_parameters"]["limit"]["min"], 1)
        self.assertEqual(
            ep["request_parameters"]["status"]["allowed"],
            ["todo", "in_progress", "done", "canceled"],
        )
        forbidden = {item.lower() for item in ep["forbidden_inputs"]}
        for item in ("userid", "ownerid", "x-user-id", "x-prp-owner",
                     "x-forwarded-user", "database-url", "prp-jwt-from-chat",
                     "mcp-tool-userid"):
            self.assertIn(item, forbidden)

    def test_producer_must_verify_both_service_and_owner_delegation(self):
        a = self.c["authentication"]
        self.assertIs(a["no_client_supplied_prp_user_id"], True)
        self.assertIs(a["fail_closed"], True)
        self.assertEqual(a["scope"], "prp.tasks.read")
        self.assertIn("verified production PRP owner", a["subject"])
        self.assertIn("rechecked by producer on every read",
                      a["consent_revocation"])
        self.assertEqual(
            a["verified_external_identity"],
            ["keycloak_issuer", "keycloak_subject", "verified_mcp_client_id"],
        )
        self.assertIn("audience", a)
        self.assertIn("service_peer", a)
        self.assertIn("delegation", a)

    def test_task_owner_filter_still_determined_by_verified_principal(self):
        repo = java("tasks/repository/MyBatisTaskRepository.java")
        current = java("auth/security/CurrentUser.java")
        service = java("tasks/service/TaskService.java")
        self.assertIn(".eq(TaskEntity::getUserId, CurrentUser.id())", repo)
        self.assertIn(".last(\"LIMIT \" + limit)", repo)
        self.assertIn("return taskRepository.listLimited(filter, limit)", service)
        self.assertIn("getPrincipal() instanceof UserProfile user", current)
        self.assertIn("return user.id();", current)
        self.assertIn("HttpStatus.UNAUTHORIZED", current)

    def test_regular_api_tasks_is_not_the_new_internal_bridge(self):
        controller = java("tasks/api/TaskController.java")
        security = java("config/SecurityConfig.java")
        self.assertIn('@RequestMapping("/api/tasks")', controller)
        self.assertIn("taskService.list(new TaskFilter(", controller)
        self.assertNotIn('/internal/mcp/tasks', controller)
        self.assertIn(".anyRequest().authenticated()", security)
        self.assertNotIn('"/internal/**"', security)

    def test_task_tool_has_scope_max_20_and_no_owner_id_argument(self):
        tool = java("mcp/PrpMcpTools.java")
        self.assertIn('scopes.require("prp.tasks.read")', tool)
        self.assertIn("tasks.listLimited(new TaskFilter(status, null, null, null), 20)", tool)
        start = tool.index('name = "prp_tasks_list"')
        end = tool.index('name = "prp_task_get"')
        list_method = tool[start:end]
        self.assertNotIn("userId", list_method)
        self.assertNotIn("ownerId", list_method)

    def test_contract_task_fields_mirror_model_without_owner_id(self):
        model = java("tasks/model/TaskItem.java")
        match = re.search(r"public record TaskItem\(([^)]*)\)", model)
        self.assertIsNotNone(match)
        names = {
            pair.split()[-1].strip()
            for pair in match.group(1).split(",")
            if pair.strip()
        }
        self.assertEqual(set(self.c["data"]["fields"]), names)
        self.assertNotIn("userId", names)
        forbidden = self.c["data"]["never_return"]
        self.assertIn("userId", forbidden)
        self.assertIn("finance", forbidden)
        self.assertIn("wellness", forbidden)

    def test_review_has_no_credential_or_real_record_payloads(self):
        text = REVIEW.read_text(encoding="utf-8")
        for prohibited in (
            "BEGIN PRIVATE KEY", "Bearer eyJ", "passwordHash=\",
            "root@micor-server", "mysql://root", "127.0.0.1:11000",
        ):
            self.assertNotIn(prohibited, text)


if __name__ == "__main__":
    unittest.main()
