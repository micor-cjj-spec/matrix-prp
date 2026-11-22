"""Disposable cross-language offline acceptance for #218 (no live resources)."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import check_offline_contract as offline


PLAN = {
    "purpose": "mcp218-review-video-readonly",
    "release_gate": "PREPARATION_ONLY",
    "project": "prp-mcp218-ci-contract",
    "resource_url": "https://mcp218-ci-contract.micor.top/api/mcp",
    "issuer_url": "https://auth-mcp218-ci-contract.micor.top/realms/prp-mcp218",
    "mysql_schema": "matrix_prp_mcp218_ci_contract",
    "mysql_volume": "mcp218_mysql_ci_contract",
    "keycloak_volume": "mcp218_pg_ci_contract",
    "database_source": "new-empty",
    "keycloak_source": "new-empty",
    "data_policy": "synthetic-only",
    "published": False,
    "mcp_enabled": False,
    "oauth_enabled": False,
    "write_enabled": False,
    "additional_read_tools_enabled": False,
    "review_video_read_tools_enabled": False,
    "advertised_scopes": ["prp.reviews.read", "prp.video.read"],
    "expected_tools": [
        "prp_reviews_list", "prp_video_folders", "prp_video_progress",
    ],
}


class SharedOfflinePlanContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="mcp218-contract-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nonsecret-plan.json"

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        return self.path

    def test_exact_plan_node_validator_and_realm_candidate_agree(self):
        self.assertIsNone(offline.check_contract(self.write(PLAN)))

    def test_scope_order_is_immaterial_but_extra_scopes_fail(self):
        reordered = {**PLAN, "advertised_scopes": list(reversed(PLAN["advertised_scopes"]))}
        self.assertIsNone(offline.check_contract(self.write(reordered)))
        extra = {**PLAN, "advertised_scopes": PLAN["advertised_scopes"] + ["prp.write.create"]}
        self.assertEqual(offline.check_contract(self.write(extra)), "PLAN_SHAPE_REJECTED")

    def test_shared_v2_resource_rejected_before_realm_generation(self):
        shared = {**PLAN, "resource_url": "https://prp-test.micor.top/api/mcp"}
        with patch("check_offline_contract.build_review_video_candidate") as builder:
            self.assertEqual(offline.check_contract(self.write(shared)), "PLAN_SHAPE_REJECTED")
            builder.assert_not_called()

    def test_bad_realm_binding_fails_closed_even_when_js_passes(self):
        self.write(PLAN)
        from review_realm import build_review_video_candidate
        invalid = build_review_video_candidate(PLAN["resource_url"])
        invalid["clients"][0]["attributes"]["resource_url"] = "https://wrong.test/api/mcp"
        with patch("check_offline_contract.build_review_video_candidate", return_value=invalid):
            self.assertEqual(offline.check_contract(self.path), "REALM_PLAN_CONTRACT_MISMATCH")

    def test_extra_realm_client_fails_closed(self):
        self.write(PLAN)
        from review_realm import build_review_video_candidate
        invalid = build_review_video_candidate(PLAN["resource_url"])
        invalid["clients"].append({"clientId": "unreviewed-login"})
        with patch("check_offline_contract.build_review_video_candidate", return_value=invalid):
            self.assertEqual(offline.check_contract(self.path), "REALM_PLAN_CONTRACT_MISMATCH")

    def test_login_client_review_receives_same_plan_resource_and_issuer(self):
        self.write(PLAN)
        from review_exact_clients import review_package
        with patch("check_offline_contract.review_package", wraps=review_package) as factory:
            self.assertIsNone(offline.check_contract(self.path))
            factory.assert_called_once_with(PLAN["resource_url"], PLAN["issuer_url"])

    def test_login_client_review_rejects_wrong_resource_and_issuer(self):
        self.write(PLAN)
        from review_exact_clients import review_package
        original = review_package(PLAN["resource_url"], PLAN["issuer_url"])
        for key, wrong in (
            ("resource", "https://prp-test.micor.top/api/mcp"),
            ("issuer", "https://auth-test.micor.top/realms/prp-mcp"),
        ):
            with self.subTest(key=key):
                mutated = {**original, key: wrong}
                with patch("check_offline_contract.review_package", return_value=mutated):
                    self.assertEqual(offline.check_contract(self.path),
                                     "CLIENT_PLAN_CONTRACT_MISMATCH")

    def test_login_client_review_rejects_broader_scope_even_with_correct_realm(self):
        self.write(PLAN)
        from copy import deepcopy
        from review_exact_clients import review_package
        malicious = deepcopy(review_package(PLAN["resource_url"], PLAN["issuer_url"]))
        malicious["proposed_clients"][1]["optionalClientScopes"].append("prp.write.create")
        with patch("check_offline_contract.review_package", return_value=malicious):
            self.assertEqual(offline.check_contract(self.path),
                             "CLIENT_PLAN_CONTRACT_MISMATCH")

    def test_login_client_review_rejects_allocated_owners_grants_and_deployable_flag(self):
        self.write(PLAN)
        from copy import deepcopy
        from review_exact_clients import review_package
        original = review_package(PLAN["resource_url"], PLAN["issuer_url"])
        for field, value in (
            ("actual_user_ids", [1, 2]),
            ("expanded_user_ids_setting", "1,2"),
            ("owner_client_grants", "ACTIVE"),
        ):
            with self.subTest(field=field):
                malicious = deepcopy(original)
                malicious["synthetic_owner_plan"][field] = value
                with patch("check_offline_contract.review_package", return_value=malicious):
                    self.assertEqual(offline.check_contract(self.path),
                                     "CLIENT_PLAN_CONTRACT_MISMATCH")
        deployable = {**original, "deployable": True}
        with patch("check_offline_contract.review_package", return_value=deployable):
            self.assertEqual(offline.check_contract(self.path),
                             "CLIENT_PLAN_CONTRACT_MISMATCH")

    def test_secret_field_rejected_without_echo(self):
        self.write({**PLAN, "client_secret": "PRIVATE_CI_SENTINEL_SHOULD_NOT_APPEAR"})
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = offline.main([str(self.path)])
        self.assertEqual(code, 2)
        self.assertEqual(
            stdout.getvalue().strip(),
            "MCP218_OFFLINE_CONTRACT_NO_GO PLAN_SHAPE_REJECTED",
        )
        self.assertNotIn("PRIVATE_CI_SENTINEL", stdout.getvalue())

    def test_missing_malformed_and_oversized_plan_fail_closed(self):
        self.assertEqual(offline.check_contract(self.path), "PLAN_UNREADABLE_OR_TOO_LARGE")
        self.path.write_text("{unparseable", encoding="utf-8")
        self.assertEqual(offline.check_contract(self.path), "PLAN_UNREADABLE_OR_TOO_LARGE")
        self.path.write_text(" " * (offline.MAX_PLAN_BYTES + 1), encoding="utf-8")
        self.assertEqual(offline.check_contract(self.path), "PLAN_UNREADABLE_OR_TOO_LARGE")

    def test_node_unavailable_and_timeout_fail_closed(self):
        self.write(PLAN)
        with patch("check_offline_contract.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(offline.check_contract(self.path), "PLAN_VALIDATOR_UNAVAILABLE")
        with patch("check_offline_contract.subprocess.run", side_effect=subprocess.TimeoutExpired("node", 10)):
            self.assertEqual(offline.check_contract(self.path), "PLAN_VALIDATOR_UNAVAILABLE")

    def test_cli_success_label_is_not_release_permission(self):
        self.write(PLAN)
        finished = subprocess.run(
            [sys.executable, str(Path(offline.__file__)), str(self.path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(finished.returncode, 0)
        self.assertEqual(finished.stdout.strip(), offline.PASS)
        self.assertEqual(finished.stderr, "")

    def test_no_plan_argument_is_a_fixed_no_go(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = offline.main([])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue().strip(),
                         "MCP218_OFFLINE_CONTRACT_NO_GO EXACT_PLAN_PATH_REQUIRED")


if __name__ == "__main__":
    unittest.main()
