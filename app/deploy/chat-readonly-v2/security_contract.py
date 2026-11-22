"""Offline-only security contracts for PRP readonly V2.

Not a runner, not a public interface, and not cryptographic authentication.
Caller-supplied runtime values must come from GitHub's trusted Actions
context; this module does NOT independently verify their provenance.
ReplayLedger requires an operator-controlled private SQLite directory; no
production filesystem, account, or SSH setup is implemented here.
"""
import base64
import json
import os
from pathlib import Path
import re
import stat
import sqlite3
import time
import uuid

from readonly_ops import RejectedRequest

REPO = "micor-cjj-spec/matrix-prp"
REPO_ID = 1261866723
OWNER = "micor-cjj-spec"
OWNER_ID = 123868412
PREFIX = "/prp-readonly-v2"
MAX_CIPHER_B64 = 24000
EVENT_FIELDS = frozenset(("event_name", "ref", "repository", "repository_id",
                          "actor", "actor_id"))
RESULT_FIELDS = frozenset(("version", "jobId", "operation", "ok", "observedAt",
                           "data", "errorCode"))
ERROR_CODES = frozenset(("REQUEST_REJECTED", "METRIC_UNAVAILABLE",
                         "PROBE_UNAVAILABLE", "INTERNAL_UNAVAILABLE"))
OPS = frozenset(("host_root_fs_usage", "prp_app_health"))


def _uuid(value):
    if type(value) is not str:
        raise RejectedRequest("invalid request")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError("not canonical")
    except (ValueError, AttributeError) as exc:
        raise RejectedRequest("invalid request") from exc
    return value


def _no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise RejectedRequest("invalid result")
        result[k] = v
    return result


def parse_event_fixture(event, trusted_runtime, pinned_issue_number):
    """Pure validation of a simulated GitHub issue_comment message.

    No route number is inferred or defaulted: a separate reviewed V2 Issue
    must be pinned by a future adapter. This function must NEVER be treated
    as independent proof of ChatGPT user's conversational approval.
    """
    if (type(pinned_issue_number) is not int or pinned_issue_number <= 0 or
            type(trusted_runtime) is not dict or
            set(trusted_runtime) != EVENT_FIELDS or
            trusted_runtime != {
                "event_name": "issue_comment", "ref": "refs/heads/main",
                "repository": REPO, "repository_id": REPO_ID,
                "actor": OWNER, "actor_id": OWNER_ID,
            }):
        raise RejectedRequest("invalid event")
    if type(event) is not dict:
        raise RejectedRequest("invalid event")
    repo, sender, issue, comment = (
        event.get("repository"), event.get("sender"),
        event.get("issue"), event.get("comment"),
    )
    if any(type(x) is not dict for x in (repo, sender, issue, comment)):
        raise RejectedRequest("invalid event")
    if event.get("action") != "created":
        raise RejectedRequest("invalid event")
    if (repo.get("full_name") != REPO or type(repo.get("id")) is not int or
            repo["id"] != REPO_ID):
        raise RejectedRequest("invalid event")
    for user in (sender, comment.get("user")):
        if (type(user) is not dict or user.get("login") != OWNER or
                user.get("type") != "User" or
                type(user.get("id")) is not int or user["id"] != OWNER_ID):
            raise RejectedRequest("invalid event")
    if (type(issue.get("number")) is not int or
            issue["number"] != pinned_issue_number or
            "pull_request" in issue or
            type(comment.get("id")) is not int or comment["id"] <= 0):
        raise RejectedRequest("invalid event")
    body = comment.get("body")
    if type(body) is not str or len(body) > MAX_CIPHER_B64 + 100:
        raise RejectedRequest("invalid event")
    match = re.fullmatch(
        r"/prp-readonly-v2 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,24000})\n?",
        body,
    )
    if match is None:
        raise RejectedRequest("invalid event")
    job = _uuid(match.group(1))
    token = match.group(2)
    try:
        binary = base64.b64decode(token + "=" * (-len(token) % 4),
                                  altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RejectedRequest("invalid event") from exc
    if base64.urlsafe_b64encode(binary).decode("ascii").rstrip("=") != token:
        raise RejectedRequest("invalid event")
    return {"jobId": job, "ciphertextB64": token, "commentId": comment["id"]}


class ReplayLedger:
    """Durable atomic one-use claim for synthetic/local tests only.

    The caller must provide an absolute, private, non-symlink SQLite path.
    This prototype intentionally does NOT prune records: any previously
    claimed job ID or nonce stays rejected across restarts. Real deployment
    requires separately reviewed filesystem ownership/locking/retention.
    """

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise RejectedRequest("state unavailable")

    def _prepare_private_file(self):
        """Deny writable/shared directories, symlinks and preexisting loose files.

        This is an isolated prototype guard, not a production-safe guarantee
        against every filesystem race or privileged operator misconfiguration.
        """
        try:
            parent = self.path.parent
            parent_stat = parent.lstat()
            if (parent.is_symlink() or not stat.S_ISDIR(parent_stat.st_mode) or
                    parent_stat.st_uid != os.geteuid() or
                    stat.S_IMODE(parent_stat.st_mode) != 0o700):
                raise RejectedRequest("state unavailable")
            try:
                fd = os.open(
                    str(self.path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                pass
            else:
                os.close(fd)
            st = self.path.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
                raise RejectedRequest("state unavailable")
        except (OSError, ValueError) as exc:
            raise RejectedRequest("state unavailable") from exc

    def claim(self, job_id, nonce, expires_at, now=None):
        _uuid(job_id)
        timestamp = int(time.time()) if now is None else now
        if (type(nonce) is not str or re.fullmatch(r"[0-9a-f]{32}", nonce) is None or
                type(expires_at) is not int or type(timestamp) is not int or
                expires_at <= timestamp or expires_at - timestamp > 180):
            raise RejectedRequest("invalid request")
        connection = None
        try:
            self._prepare_private_file()
            connection = sqlite3.connect(str(self.path), isolation_level=None, timeout=2)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS claims ("
                "job_id TEXT PRIMARY KEY, nonce TEXT NOT NULL UNIQUE,"
                "expires_at INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO claims (job_id,nonce,expires_at) VALUES (?,?,?)",
                (job_id, nonce, expires_at),
            )
            connection.execute("COMMIT")
            return True
        except sqlite3.IntegrityError as exc:
            if connection is not None:
                connection.rollback()
            raise RejectedRequest("already claimed") from exc
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise RejectedRequest("state unavailable") from exc
        finally:
            if connection is not None:
                connection.close()


def _safe_data(operation, data):
    if type(data) is not dict:
        raise RejectedRequest("invalid result")
    if operation == "host_root_fs_usage":
        if set(data) != {"totalBytes", "usedBytes", "freeBytes", "usagePercent"}:
            raise RejectedRequest("invalid result")
        total, used, free, pct = (
            data["totalBytes"], data["usedBytes"], data["freeBytes"],
            data["usagePercent"],
        )
        if (any(type(v) is not int or v < 0 for v in (total, used, free)) or
                total == 0 or used > total or free > total or
                type(pct) not in (int, float) or not 0 <= pct <= 100 or
                abs(pct - 100 * used / total) > .02):
            raise RejectedRequest("invalid result")
    elif operation == "prp_app_health":
        if (set(data) != {"liveness", "readiness"} or
                data["liveness"] not in ("reachable", "unreachable", "unknown") or
                data["readiness"] != "unknown"):
            raise RejectedRequest("invalid result")
    else:
        raise RejectedRequest("invalid result")
    return data


def encode_result(job_id, operation, observed_at, data=None, error_code=None):
    """Produce an allowlisted JSON payload. CMS encryption is NOT provided."""
    _uuid(job_id)
    if (operation not in OPS or type(observed_at) is not int or
            observed_at < 0):
        raise RejectedRequest("invalid result")
    if error_code is None:
        payload_data = _safe_data(operation, data)
        ok = True
    else:
        if (type(error_code) is not str or error_code not in ERROR_CODES or
                data is not None):
            raise RejectedRequest("invalid result")
        payload_data = {}
        ok = False
    result = {
        "version": 2, "jobId": job_id, "operation": operation, "ok": ok,
        "observedAt": observed_at, "data": payload_data,
        "errorCode": error_code,
    }
    return json.dumps(result, sort_keys=True, separators=(",", ":")).encode()


def parse_result(raw, expected_job_id, expected_operation):
    """Validate a result AFTER authenticated CMS decryption by a caller."""
    _uuid(expected_job_id)
    if (type(expected_operation) is not str or
            expected_operation not in OPS or type(raw) is not bytes or
            not 0 < len(raw) <= 2048):
        raise RejectedRequest("invalid result")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               RejectedRequest("invalid result")))
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise RejectedRequest("invalid result") from exc
    if (type(value) is not dict or set(value) != RESULT_FIELDS or
            type(value["version"]) is not int or value["version"] != 2 or
            value["jobId"] != expected_job_id or
            value["operation"] != expected_operation or
            type(value["ok"]) is not bool or
            type(value["observedAt"]) is not int or value["observedAt"] < 0):
        raise RejectedRequest("invalid result")
    if value["ok"]:
        if value["errorCode"] is not None:
            raise RejectedRequest("invalid result")
        _safe_data(expected_operation, value["data"])
    else:
        if (type(value["errorCode"]) is not str or
                value["errorCode"] not in ERROR_CODES or
                value["data"] != {}):
            raise RejectedRequest("invalid result")
    return value
