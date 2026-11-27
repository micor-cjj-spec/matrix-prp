#!/usr/bin/env python3
"""Operator-only S6.2A local preflight. No business write or cleanup entry point."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import types
from pathlib import Path

from unified_staging_s5_recovery import (
    S5_SOURCE_SHA256, assess_interrupted_journal, capture_baseline, compare_baseline,
)

HELPER_SHA256 = "8370a6c54b1ba4de73777ec7f1d91a74df03bd5076ec1bf50b7afcdf858b9b08"
IMAGES = {
    "backend": "sha256:47e21a8cec1251fa496dea71faa15a2f7c68d907d2fa6896c74456b742dd353e",
    "gateway": "sha256:f67163b616f1ee2fc931cc164934e5ddd5d89afd0b75c32cdb8a07b4b1999551",
    "mysql": "sha256:0f1a0ccadda3a1734d1db557e203ec58621d56fa248525016e85fe4f631311ec",
}
PATHS = {
    "task": "/api/tasks", "record": "/api/records", "video": "/api/video/folders",
    "practice": "/api/practice/subjects", "account": "/api/finance/accounts",
    "category": "/api/finance/categories", "finance": "/api/finance/transactions",
}
ISSUER = "https://auth-test.micor.top/realms/prp-mcp"
TARGET = "https://prp-test.micor.top"
LOCK = ".s5-cross-module.lock"


class PreflightError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise PreflightError(reason)


def private_parent(path):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve(strict=True) == path.parent,
            "PRIVATE_PATH_REQUIRED")
    info = path.parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "PRIVATE_DIRECTORY_REQUIRED")
    return path


def private_fd(path, *, helper=False):
    path = private_parent(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        mode = stat.S_IMODE(s.st_mode)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and s.st_nlink == 1 and
                ((mode & 0o7022 == 0 and mode & 0o400) if helper else mode == 0o600),
                "PRIVATE_FILE_REQUIRED")
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_private(path, limit, *, helper=False):
    with os.fdopen(private_fd(path, helper=helper), "rb") as f:
        require(os.fstat(f.fileno()).st_size <= limit, "PRIVATE_FILE_TOO_LARGE")
        raw = f.read(limit + 1)
    require(len(raw) <= limit, "PRIVATE_FILE_TOO_LARGE")
    return raw


def load_helper(path):
    """Only execute the exact existing #420 helper bytes, never its main()."""
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    raw = read_private(path, 65536, helper=True)
    require(hashlib.sha256(raw).hexdigest() == HELPER_SHA256, "HELPER_DIGEST_MISMATCH")
    m = types.ModuleType("p420_verified")
    m.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), m.__dict__)
    require(m.BASE_URL == "http://127.0.0.1:23080"
            and m.TARGET_HOST == "prp-test.micor.top"
            and m.PROJECT == "prp-unified-396"
            and m.DB_NAME == "matrix_prp_unified_stage"
            and m.DB_USER == "prp_unified", "HELPER_TARGET_MISMATCH")
    return m


def lock_identity(fd, path):
    opened, current = os.fstat(fd), path.lstat()
    require((opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
            and opened.st_nlink == 1 and current.st_uid == os.geteuid()
            and stat.S_IMODE(current.st_mode) == 0o600, "LOCK_CHANGED")


def verify_stage(m):
    meta = m.inspect_target()
    m.validate_target(meta)
    env = meta["backend"]["env"]
    require(env.get("MATRIX_PRP_MCP_OAUTH_ISSUER") == ISSUER
            and env.get("MATRIX_PRP_MCP_OAUTH_RESOURCE") == TARGET + "/api/mcp",
            "STAGE_OAUTH_MISMATCH")
    runtime = {}
    for kind, name in (("backend", m.BACKEND), ("gateway", m.GATEWAY), ("mysql", m.MYSQL)):
        parts = m._run(["docker", "inspect", "--format",
                       "{{.Id}} {{.Image}} {{.State.StartedAt}} {{.RestartCount}}", name]).split()
        require(len(parts) == 4 and re.fullmatch(r"[a-f0-9]{64}", parts[0])
                and parts[1] == IMAGES[kind] and parts[2] and parts[3].isdigit(),
                "STAGE_IMAGE_OR_RUNTIME_MISMATCH")
        runtime[kind] = tuple(parts)
    sql = ("START TRANSACTION READ ONLY;\n"
           "SELECT version FROM flyway_schema_history WHERE success=1 "
           "AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1;\n"
           "SELECT COUNT(*) FROM flyway_schema_history WHERE success=0;\nCOMMIT;\n")
    command = ["docker", "exec", "-i", m.MYSQL, "sh", "-c",
               'test "$MYSQL_DATABASE" = "matrix_prp_unified_stage" && '
               'test "$MYSQL_USER" = "prp_unified" && '
               'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --protocol=TCP --host=127.0.0.1 '
               '--user="$MYSQL_USER" --database="$MYSQL_DATABASE" --batch --skip-column-names']
    require(m._run(command, input_text=sql).splitlines() == ["31", "0"],
            "STAGE_SCHEMA_MISMATCH")
    # Compare complete helper metadata in memory; never export environment values.
    return runtime, hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()


def credentials(m, b_file):
    a = m.read_existing_credentials()
    original_dir, original_file = m.CREDENTIAL_DIR, m.CREDENTIAL_FILE
    b_file = private_parent(b_file)
    require(b_file != original_file and b_file.parent in
            (original_dir, original_dir.with_name(original_dir.name + "-b")),
            "B_FILE_NOT_DISTINCT_OR_OUTSIDE_EXISTING_DIRECTORY")
    try:
        m.CREDENTIAL_DIR, m.CREDENTIAL_FILE = b_file.parent, b_file
        b = m.read_existing_credentials()
    finally:
        m.CREDENTIAL_DIR, m.CREDENTIAL_FILE = original_dir, original_file
    require(a["user_id"] != b["user_id"] and a["username"] != b["username"],
            "DUPLICATE_IDENTITY")
    for c in (a, b):
        m.query_ordinary_identity_readonly(c)
    return {"A": a, "B": b}


def success(m, path, token=None, login_payload=None):
    # The only POST is the existing ordinary password-login route.
    if login_payload is not None:
        require(path == "/api/auth/login" and token is None, "HTTP_ROUTE_BLOCKED")
        result = m.http_json(path, method="POST", payload=login_payload)
    else:
        require(token is not None and (path in PATHS.values() or path == "/api/users/me"
                or re.fullmatch(r"/api/finance/summary/monthly\?month=[0-9]{4}-(?:0[1-9]|1[0-2])", path)),
                "HTTP_ROUTE_BLOCKED")
        result = m.http_json(path, method="GET", token=token)
    status, ctype, body = result
    require(status == 200 and m.valid_json_type(ctype) and isinstance(body, dict)
            and body.get("code") == "SUCCESS", "API_READ_CONTRACT_FAILURE")
    return body.get("data")


def same_user(user, c):
    return (isinstance(user, dict) and type(user.get("id")) is int
            and user["id"] == c["user_id"] and user.get("username") == c["username"]
            and user.get("administrator") is False)


def login(m, c):
    d = success(m, "/api/auth/login", login_payload={
        "username": c["username"], "password": c["password"]})
    require(isinstance(d, dict) and same_user(d.get("user"), c)
            and d.get("tokenType") == "Bearer"
            and type(d.get("expiresInSeconds")) is int and d["expiresInSeconds"] > 0
            and isinstance(d.get("token"), str) and len(d["token"]) <= 8192
            and re.fullmatch(r"[-_A-Za-z0-9]+\.[-_A-Za-z0-9]+\.[-_A-Za-z0-9]+", d["token"]),
            "LOGIN_IDENTITY_MISMATCH")
    token = d["token"]
    require(same_user(success(m, "/api/users/me", token), c), "CURRENT_IDENTITY_MISMATCH")
    return token


def observe(m, tokens, month):
    snapshots, summaries = {}, {}
    for who, token in tokens.items():
        for kind, path in PATHS.items():
            snapshots[who + "_" + kind] = success(m, path, token)
        data = success(m, "/api/finance/summary/monthly?month=" + month, token)
        require(isinstance(data, dict) and {"income", "expense", "balance"} <= set(data),
                "SUMMARY_SHAPE")
        summaries[who] = {k: data[k] for k in ("income", "expense", "balance")}
    return snapshots, summaries


def require_disjoint(snapshots):
    for kind in PATHS:
        require(not ({r["id"] for r in snapshots["A_" + kind]}
                     & {r["id"] for r in snapshots["B_" + kind]}), "CROSS_OWNER_LIST_OVERLAP")


def read_journal(path):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            require(k not in d, "DUPLICATE_JOURNAL_KEY")
            d[k] = v
        return d
    return json.loads(read_private(path, 65536), object_pairs_hook=unique)


def run_preflight(m, b_file, journal_file=None):
    lock_path = m.CREDENTIAL_DIR / LOCK
    # Do not create, truncate, replace or remove the existing shared lock.
    fd = private_fd(lock_path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_identity(fd, lock_path)
        first = verify_stage(m)
        accounts = credentials(m, b_file)
        tokens = {w: login(m, c) for w, c in accounts.items()}
        month = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)).strftime("%Y-%m")
        context = {"run": "UAT396-" + secrets.token_hex(8), "month": month,
                   "target": TARGET, "schema": 31, "images": dict(IMAGES),
                   "owners": {w: c["user_id"] for w, c in accounts.items()},
                   "sourceSha256": S5_SOURCE_SHA256}
        snapshots, summaries = observe(m, tokens, month)
        baseline = capture_baseline(context, snapshots, summaries)
        require_disjoint(snapshots)
        journal_state = "NOT_REQUESTED"
        if journal_file is not None:
            journal = read_journal(journal_file)
            journal_state = assess_interrupted_journal(journal, snapshots)["state"]
            require(journal_state in ("NO_MARKERS_OBSERVED", "NO_ATTEMPTS_OBSERVED"),
                    "JOURNAL_REVIEW_REQUIRED")
        current, current_summaries = observe(m, tokens, month)
        require(compare_baseline(baseline, context, current, current_summaries)["state"]
                == "BASELINE_DIGESTS_MATCH", "BASELINE_DRIFT_OR_INVALID")
        for who, c in accounts.items():
            m.query_ordinary_identity_readonly(c)
            require(same_user(success(m, "/api/users/me", tokens[who]), c), "CURRENT_IDENTITY_MISMATCH")
        require(verify_stage(m) == first, "RUNTIME_CHANGED")
        lock_identity(fd, lock_path)
        return {"state": "S5_LOCAL_PREFLIGHT_PASS", "schema": 31,
                "ownerLists": 14, "financeSummaries": 2, "baselineComparison": "MATCH",
                "journalState": journal_state, "businessWrites": 0, "accountCreated": False,
                "cleanupAuthorized": False, "baselineRestored": False, "liveVerified": False,
                "deploymentAuthorized": False, "productionAuthorized": False}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--helper", type=Path, required=True)
    p.add_argument("--b-file", type=Path, required=True)
    p.add_argument("--journal-file", type=Path)
    args = p.parse_args()
    try:
        report = run_preflight(load_helper(args.helper), args.b_file, args.journal_file)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        reason = str(exc) if type(exc) is PreflightError else "LOCAL_PREFLIGHT_FAILED"
        print(json.dumps({"state": "S5_LOCAL_PREFLIGHT_BLOCKED", "reason": reason,
                          "businessWrites": 0, "cleanupAuthorized": False,
                          "liveVerified": False, "deploymentAuthorized": False,
                          "productionAuthorized": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
