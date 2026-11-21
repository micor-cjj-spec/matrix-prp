"""Synthetic regression tests for the proposed main PR source gate."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from check_main_pr_source import allowed_source

REPO = "micor-cjj-spec/matrix-prp"


def event(source="dev", source_repo=REPO, target="main", target_repo=REPO,
          outer_repo=REPO):
    return {
        "repository": {"full_name": outer_repo},
        "pull_request": {
            "head": {"ref": source, "repo": {"full_name": source_repo}},
            "base": {"ref": target, "repo": {"full_name": target_repo}},
        },
    }


class MainSourceGateTests(unittest.TestCase):
    def test_same_repository_dev_to_main(self):
        self.assertTrue(allowed_source(event(), REPO))

    def test_feature_branch_to_main_denied(self):
        self.assertFalse(allowed_source(event(source="feature/my-work"), REPO))

    def test_fork_dev_to_main_denied(self):
        self.assertFalse(allowed_source(event(source_repo="some-fork/matrix-prp"), REPO))

    def test_dev_to_other_target_denied(self):
        self.assertFalse(allowed_source(event(target="release"), REPO))

    def test_wrong_target_repository_denied(self):
        self.assertFalse(allowed_source(event(target_repo="some-fork/matrix-prp"), REPO))

    def test_forged_top_level_repository_denied(self):
        self.assertFalse(allowed_source(event(outer_repo="some-fork/matrix-prp"), REPO))

    def test_branch_name_case_sensitive(self):
        self.assertFalse(allowed_source(event(source="Dev"), REPO))

    def test_missing_or_wrong_type_fields_fail_closed(self):
        for payload in ({}, {"pull_request": None}, {"repository": {"full_name": REPO}},
                        {"repository": {"full_name": REPO}, "pull_request": {"head": "dev"}},
                        {"repository": {"full_name": REPO}, "pull_request": {"base": {}, "head": {}}},
                        None, [], "dev"):
            with self.subTest(payload=payload):
                self.assertFalse(allowed_source(payload, REPO))

    def test_empty_expected_repository_denied(self):
        self.assertFalse(allowed_source(event(), ""))



class MainSourceGateEntrypointTests(unittest.TestCase):
    """Run the real release-gate CLI using a synthetic GitHub event file."""

    def invoke(self, payload, repository=REPO, malformed=False):
        with tempfile.TemporaryDirectory(prefix="prp-source-gate-") as temp:
            event_path = Path(temp) / "event.json"
            event_path.write_text("{invalid-json" if malformed else json.dumps(payload),
                                  encoding="utf-8")
            env = {"GITHUB_REPOSITORY": repository, "GITHUB_EVENT_PATH": str(event_path)}
            return subprocess.run(
                [sys.executable, "-I",
                 str(Path(__file__).with_name("check_main_pr_source.py"))],
                env=env, text=True, capture_output=True, timeout=10, check=False,
            )

    def test_cli_accepts_exact_same_repository_dev(self):
        result = self.invoke(event())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS:", result.stdout)

    def test_cli_rejects_feature_branch_and_fork_dev(self):
        for payload in [event(source="feat/ui"), event(source_repo="fork/matrix-prp"),
                        event(target="release"), {"pull_request": None}]:
            with self.subTest(payload=payload):
                result = self.invoke(payload)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("::error::", result.stdout)

    def test_cli_rejects_malformed_json_and_missing_context(self):
        result = self.invoke(event(), malformed=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("::error::", result.stdout)
        result = self.invoke(event(), repository="")
        self.assertEqual(result.returncode, 2)
        self.assertIn("::error::", result.stdout)

    def test_workflow_does_not_execute_untrusted_pull_request_head(self):
        # Structural smoke check; reviewers still must audit workflow changes.
        path = Path(__file__).resolve().parents[2] / ".github/workflows/main-pr-source-guard.yml"
        workflow = path.read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("name: main-pr-source-dev", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("ref: $" + "{{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request.head.sha", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)


if __name__ == "__main__":
    unittest.main()
