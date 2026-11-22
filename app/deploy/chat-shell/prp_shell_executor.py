#!/usr/bin/env python3
"""Review-only PRP chat-approved shell executor.

This file is NOT a server installer. Deployment requires an independent
administrator review of the root-owned HMAC key, sudo boundary, dedicated
unprivileged account, SSH forced command and result-return path.

Protocol: the PRP backend signs an exact immutable UTF-8 JSON job as
  {"ticket": base64url(payload), "mac": HMAC_SHA256(secret, raw_payload).hex()}
The signature covers the *whole* command, target, principal, expiry and nonce.
The GitHub runner transports this envelope but never receives the HMAC key.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID

TARGET = "prp-production"
EXEC_USER = "prp-shell"
KEY_PATH = Path("/etc/matrix-prp-chat-shell.key")
STATE_DIR = Path("/var/lib/matrix-prp-chat-shell")
STATE_DB = STATE_DIR / "used.sqlite3"
MAX_INPUT = 24 * 1024
MAX_COMMAND = 8192
MAX_OUTPUT = 16384
MAX_SECONDS = 30
TICKET_KEYS = frozenset((
    "jobId", "ownerId", "target", "command", "issuedAt",
    "expiresAt", "runSeconds", "nonce",
))


class Denied(Exception):
    pass


def _object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Denied("DUPLICATE_FIELD")
        result[key] = value
    return result


def _read_json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(Denied("INVALID_NUMBER")))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Denied("INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise Denied("INVALID_ENVELOPE")
    return value


def _base64url(text):
    if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise Denied("INVALID_TICKET")
    try:
        padding = "=" * (-len(text) % 4)
        result = base64.b64decode(text + padding, altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise Denied("INVALID_TICKET") from exc
    if base64.urlsafe_b64encode(result).decode().rstrip("=") != text:
        raise Denied("NONCANONICAL_TICKET")
    return result


def verify_envelope(envelope, secret, now=None):
    """Pure verifier. No runner-controlled approval flag can authorize a job."""
    if not isinstance(envelope, dict) or set(envelope) != {"ticket", "mac"}:
        raise Denied("INVALID_ENVELOPE")
    raw = _base64url(envelope["ticket"])
    if not raw or len(raw) > MAX_INPUT:
        raise Denied("INVALID_TICKET_SIZE")
    mac = envelope["mac"]
    if not isinstance(mac, str) or not re.fullmatch(r"[0-9a-f]{64}", mac):
        raise Denied("INVALID_SIGNATURE")
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise Denied("MISSING_SIGNING_KEY")
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise Denied("SIGNATURE_MISMATCH")
    payload = _read_json(raw.decode("utf-8", errors="strict"))
    if set(payload) != TICKET_KEYS:
        raise Denied("INVALID_JOB_FIELDS")
    command = payload["command"]
    if not isinstance(command, str) or not command.strip():
        raise Denied("EMPTY_COMMAND")
    command_bytes = command.encode("utf-8")
    if len(command_bytes) > MAX_COMMAND or "\x00" in command:
        raise Denied("INVALID_COMMAND_SIZE")
    if payload["target"] != TARGET:
        raise Denied("INVALID_TARGET")
    if type(payload["ownerId"]) is not int or payload["ownerId"] <= 0:
        raise Denied("INVALID_OWNER")
    if type(payload["issuedAt"]) is not int or type(payload["expiresAt"]) is not int:
        raise Denied("INVALID_EXPIRY")
    if type(payload["runSeconds"]) is not int or not 1 <= payload["runSeconds"] <= MAX_SECONDS:
        raise Denied("INVALID_TIMEOUT")
    try:
        job_id = UUID(payload["jobId"])
        if str(job_id) != payload["jobId"]:
            raise ValueError("noncanonical")
    except (ValueError, TypeError, AttributeError) as exc:
        raise Denied("INVALID_JOB_ID") from exc
    if not isinstance(payload["nonce"], str) or not re.fullmatch(r"[a-f0-9]{32,64}", payload["nonce"]):
        raise Denied("INVALID_NONCE")
    current = int(time.time()) if now is None else int(now)
    if not current - 60 <= payload["issuedAt"] <= current + 15:
        raise Denied("STALE_ISSUANCE")
    if not current < payload["expiresAt"] <= payload["issuedAt"] + 300:
        raise Denied("EXPIRED_OR_LONG_LIVED")
    return payload


def _protected_file(path, owner, mode):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != owner or stat.S_IMODE(st.st_mode) != mode:
        raise Denied("INSECURE_FILE")


def _protected_dir(path):
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o700:
        raise Denied("INSECURE_STATE_DIRECTORY")


def _load_key():
    _protected_file(KEY_PATH, 0, 0o400)
    raw = KEY_PATH.read_bytes()
    if len(raw) != 32:
        raise Denied("INVALID_KEY")
    return raw


def claim_once(job_id, nonce):
    """Host-local atomic replay barrier; claim commits *before* any shell starts."""
    _protected_dir(STATE_DIR)
    if STATE_DB.exists():
        _protected_file(STATE_DB, 0, 0o600)
    with sqlite3.connect(STATE_DB, timeout=5, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS claimed (job_id TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL, created_at INTEGER NOT NULL)")
        try:
            db.execute("INSERT INTO claimed(job_id,nonce,created_at) VALUES(?,?,?)",
                       (job_id, nonce, int(time.time())))
        except sqlite3.IntegrityError as exc:
            db.execute("ROLLBACK")
            raise Denied("REPLAY_DENIED") from exc
        db.execute("COMMIT")
    os.chmod(STATE_DB, 0o600)


def run_command(payload):
    """Execute exactly the approved command as the *unprivileged* prp-shell user."""
    account = pwd.getpwnam(EXEC_USER)
    if account.pw_uid == 0 or account.pw_gid == 0:
        raise Denied("INVALID_EXECUTION_IDENTITY")

    def drop_privileges():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT * 2, MAX_OUTPUT * 2))

    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": account.pw_dir,
           "LANG": "C.UTF-8", "PRP_SHELL_JOB_ID": payload["jobId"]}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc", "-c", payload["command"]],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True, cwd="/", env=env, preexec_fn=drop_privileges,
            start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=payload["runSeconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(MAX_OUTPUT + 1)
        err = stderr.read(MAX_OUTPUT + 1)
        return {
            "jobId": payload["jobId"],
            "exitCode": proc.returncode,
            "timedOut": timed_out,
            "truncated": len(out) > MAX_OUTPUT or len(err) > MAX_OUTPUT,
            "stdout": out[:MAX_OUTPUT].decode("utf-8", "replace"),
            "stderr": err[:MAX_OUTPUT].decode("utf-8", "replace"),
        }


def main():
    # The trusted operator installs a root-owned exact-command sudo rule.
    # This script accepts no arguments, user IDs, approval booleans or URLs.
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise Denied("ROOT_GATEWAY_REQUIRED")
    envelope_raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(envelope_raw) > MAX_INPUT:
        raise Denied("REQUEST_TOO_LARGE")
    envelope = _read_json(envelope_raw)
    payload = verify_envelope(envelope, _load_key())
    claim_once(payload["jobId"], payload["nonce"])
    result = run_command(payload)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Denied as exc:
        # Deliberately emit only a fixed error category. No command, key or data.
        sys.stderr.write("PRP_SHELL_DENIED:" + str(exc) + "\n")
        sys.exit(2)
    except Exception:
        sys.stderr.write("PRP_SHELL_EXECUTION_FAILED\n")
        sys.exit(3)
