#!/usr/bin/env python3
"""Base-owned PR source check. Never check out or execute a PR's head revision.

Designed for a future, explicitly approved pull_request_target workflow.
No GitHub API calls, secrets, writes, network access, or token privileges.
"""
import json
import os
import sys
from pathlib import Path


def repository_id(value):
    """Only a nonzero numeric repository ID is a trustworthy repository key."""
    identifier = value.get("id") if isinstance(value, dict) else None
    if type(identifier) is int and identifier > 0:
        return identifier
    return None


def is_same_repo_dev_to_main(event):
    if not isinstance(event, dict):
        return False
    repository = event.get("repository")
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return False
    owner_id = repository_id(repository)
    if owner_id is None:
        return False
    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return False
    return (
        base.get("ref") == "main"
        and head.get("ref") == "dev"
        and repository_id(base.get("repo")) == owner_id
        and repository_id(head.get("repo")) == owner_id
    )


def main():
    # The event file is injected by GitHub Actions, not from the pull request
    # checkout. It is deliberately read-only and may contain other untrusted
    # fields that we ignore (titles, descriptions, branch text, comments).
    try:
        location = os.environ["GITHUB_EVENT_PATH"]
        event = json.loads(Path(location).read_text(encoding="utf-8"))
    except (KeyError, ValueError, OSError, UnicodeError):
        print("FAIL main-pr-source-dev: invalid or unavailable event metadata",
              file=sys.stderr)
        return 1
    if not is_same_repo_dev_to_main(event):
        print("FAIL main-pr-source-dev: only same-repository dev -> main is allowed",
              file=sys.stderr)
        return 1
    print("PASS main-pr-source-dev: same-repository dev -> main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
