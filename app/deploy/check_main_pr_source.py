#!/usr/bin/env python3
"""Evaluate a GitHub pull_request_target event from trusted base-branch code.

This checker is intentionally independent of checkout of the PR's head.
The rule is a proposed *additional* required status check, not a substitute
for GitHub Ruleset enforcement or the repository publication hold.
"""
import json
import os
import sys
from pathlib import Path


def allowed_source(event: object, expected_repo: str) -> bool:
    """Only this repository's exact refs/heads/dev may merge toward main."""
    if not isinstance(event, dict) or not expected_repo:
        return False
    if (event.get("repository") or {}).get("full_name") != expected_repo:
        return False
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return False
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    if not isinstance(base, dict) or not isinstance(head, dict):
        return False
    base_repo = base.get("repo") or {}
    head_repo = head.get("repo") or {}
    if not isinstance(base_repo, dict) or not isinstance(head_repo, dict):
        return False
    return (
        base.get("ref") == "main"
        and base_repo.get("full_name") == expected_repo
        and head.get("ref") == "dev"
        and head_repo.get("full_name") == expected_repo
    )


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not event_path or not repo:
        print("::error::Missing trusted GitHub event context")
        return 2
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        print("::error::Unable to read GitHub pull request event")
        return 2
    if allowed_source(event, repo):
        print("PASS: main PR source is this repository's exact dev branch")
        return 0
    print("::error::A pull request targeting main must originate from the same repository's dev branch")
    return 1


if __name__ == "__main__":
    sys.exit(main())
