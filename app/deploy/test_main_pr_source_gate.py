"""Synthetic regression tests for the proposed main PR source gate."""
import unittest
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


if __name__ == "__main__":
    unittest.main()
