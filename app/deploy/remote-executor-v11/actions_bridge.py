"""P7.3B reviewed-only Actions adapter. No live workflow or credentials by default."""
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys

from bridge import GitHubProvider, MAX_COMMENT, relay_over_ssh, verify_event
from protocol import InvalidJob, REPOSITORY, require, uuid4_text

ISSUE = 506
RESULT = re.compile(r"/prp-remote-result-v11 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,60000})")
MAX_EVENT = 1024 * 1024

def post_receipt(receipt, token):
    """Only post an opaque receipt to the fixed V1.1 issue; no redirect/retry."""
    require(type(receipt) is str and len(receipt) <= MAX_COMMENT, "invalid receipt")
    match = RESULT.fullmatch(receipt)
    require(match is not None, "invalid receipt")
    uuid4_text(match.group(1))
    require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_.-]{16,4096}", token),
            "invalid token")
    conn = http.client.HTTPSConnection("api.github.com", timeout=15,
                                      context=ssl.create_default_context())
    try:
        conn.request("POST", "/repos/" + REPOSITORY + "/issues/506/comments",
                     body=json.dumps({"body": receipt}).encode("ascii"),
                     headers={"Authorization": "Bearer " + token,
                              "Content-Type": "application/json",
                              "Accept": "application/vnd.github+json",
                              "User-Agent": "prp-remote-executor-v11",
                              "X-GitHub-Api-Version": "2022-11-28"})
        response = conn.getresponse()
        try:
            require(response.status == 201, "receipt publication uncertain")
        finally:
            response.close()
    finally:
        conn.close()

def dispatch(event, repository, ref, *, enabled=False, host=None, private_key=None,
             known_hosts=None, token=None):
    require(enabled is True, "live relay disabled")
    verify_event(event, repository, ref, ISSUE)
    require(event["comment"].get("author_association") == "OWNER", "not owner")
    # Initial E2E permits inline/repository files only. No CI artifact producer
    # or redirect host is authorized. Keep provider and receipt scopes fixed.
    provider = GitHubProvider(token)
    receipt = relay_over_ssh(event, repository, ref, ISSUE, enabled=True,
                             host=host, private_key=private_key,
                             known_hosts=known_hosts, provider=provider,
                             approved_producers=frozenset(), timeout=240)
    post_receipt(receipt, token)

def main():
    require(os.environ.get("PRP_REX_V11_ENABLED") == "true"
            and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_EVENT_NAME") == "issue_comment",
            "trusted live entrypoint disabled")
    with Path(os.environ["GITHUB_EVENT_PATH"]).open("rb") as stream:
        data = stream.read(MAX_EVENT + 1)
    require(len(data) <= MAX_EVENT, "event oversized")
    event = json.loads(data)
    dispatch(event, os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF"),
             enabled=True, host=os.environ.get("PRP_REX_V11_HOST"),
             private_key=os.environ.get("PRP_REX_V11_SSH_KEY"),
             known_hosts=os.environ.get("PRP_REX_V11_KNOWN_HOSTS"),
             token=os.environ.get("GH_TOKEN"))

if __name__ == "__main__":
    try:
        main()
        print("REMOTE_V11_ENCRYPTED_RECEIPT_POSTED")
    except Exception:
        # Never print events, keys, endpoint details, receipt contents, errors
        # or plaintext. A failed publication is uncertain; query, do not replay.
        print("REMOTE_V11_BLOCKED_OR_UNCERTAIN", file=sys.stderr)
        sys.exit(2)
