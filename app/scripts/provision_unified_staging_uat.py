#!/usr/bin/env python3
"""Manual-only provisioning + first read-only smoke for PRP unified staging.

Default is read-only preflight. Account creation requires the explicit flag.
This script never changes production, host routing, Docker services, releases or MCP grants.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TARGET_HOST = "prp-test.micor.top"
BASE_URL = "http://127.0.0.1:23080"
PROJECT = "prp-unified-396"
DB_NAME = "matrix_prp_unified_stage"
DB_USER = "prp_unified"
BACKEND = "prp-unified-396-backend-1"
GATEWAY = "prp-unified-396-gateway-1"
MYSQL = "prp-unified-396-mysql-1"
CREDENTIAL_DIR = Path("/root/.config/prp-unified-396-uat")
CREDENTIAL_FILE = CREDENTIAL_DIR / "credentials.json"
REPORT_FILE = CREDENTIAL_DIR / "last-smoke-report.json"

class ProvisionError(RuntimeError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _run(command, *, input_text=None, timeout=15):
    try:
        result = subprocess.run(command, input=input_text, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except Exception:
        raise ProvisionError("LOCAL_COMMAND_FAILED") from None
    if result.returncode != 0:
        raise ProvisionError("LOCAL_COMMAND_FAILED")
    return result.stdout.strip()

def _inspect(name):
    raw = _run(["docker", "inspect", name])
    try:
        item = json.loads(raw)[0]
        env = {}
        for entry in item.get("Config", {}).get("Env") or []:
            if "=" in entry:
                key, value = entry.split("=", 1)
                env[key] = value
        return {
            "state": item.get("State", {}).get("Status"),
            "project": (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project"),
            "env": env,
            "ports": item.get("NetworkSettings", {}).get("Ports") or {},
        }
    except Exception:
        raise ProvisionError("DOCKER_METADATA_INVALID") from None

def validate_target(metadata):
    for key in ("backend", "gateway", "mysql"):
        item = metadata[key]
        if item["state"] != "running" or item["project"] != PROJECT:
            raise ProvisionError("BLOCKED_CONTAINER_IDENTITY")
    backend = metadata["backend"]["env"]
    gateway = metadata["gateway"]["env"]
    mysql = metadata["mysql"]["env"]
    if not backend.get("MATRIX_PRP_DB_URL", "").startswith(
        "jdbc:mysql://mysql:3306/" + DB_NAME + "?"
    ):
        raise ProvisionError("BLOCKED_DATABASE_TARGET")
    if backend.get("MATRIX_PRP_DB_USER") != DB_USER:
        raise ProvisionError("BLOCKED_DATABASE_ACCOUNT")
    if gateway.get("PRP_STAGE_HOST") != TARGET_HOST:
        raise ProvisionError("BLOCKED_STAGE_HOST")
    if mysql.get("MYSQL_DATABASE") != DB_NAME or mysql.get("MYSQL_USER") != DB_USER:
        raise ProvisionError("BLOCKED_MYSQL_TARGET")
    if not mysql.get("MYSQL_ROOT_PASSWORD"):
        raise ProvisionError("BLOCKED_MYSQL_ADMIN_SECRET")
    gateway_bindings = metadata["gateway"]["ports"].get("8080/tcp") or []
    if not any(
        binding.get("HostIp") == "127.0.0.1" and binding.get("HostPort") == "23080"
        for binding in gateway_bindings
    ):
        raise ProvisionError("BLOCKED_GATEWAY_BINDING")
    for key in ("backend", "mysql"):
        for bindings in metadata[key]["ports"].values():
            if bindings:
                raise ProvisionError("BLOCKED_BACKEND_OR_DB_PUBLISHED")
    return True

def inspect_target():
    if os.geteuid() != 0:
        raise ProvisionError("BLOCKED_ROOT_REQUIRED")
    return {
        "backend": _inspect(BACKEND),
        "gateway": _inspect(GATEWAY),
        "mysql": _inspect(MYSQL),
    }

def mysql_query(sql):
    command = [
        "docker", "exec", "-i", MYSQL, "sh", "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --protocol=socket -uroot '
        "--database=" + DB_NAME + " --batch --skip-column-names",
    ]
    return _run(command, input_text=sql + "\n", timeout=20).splitlines()

def prepare_private_dir():
    CREDENTIAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = CREDENTIAL_DIR.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0:
        raise ProvisionError("BLOCKED_CREDENTIAL_DIRECTORY")
    os.chmod(CREDENTIAL_DIR, 0o700)
    if CREDENTIAL_FILE.exists() or CREDENTIAL_FILE.is_symlink():
        raise ProvisionError("BLOCKED_CREDENTIALS_ALREADY_EXIST")
    if REPORT_FILE.exists() or REPORT_FILE.is_symlink():
        raise ProvisionError("BLOCKED_PRIOR_REPORT_EXISTS")

def write_private_new(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise ProvisionError("CREDENTIAL_WRITE_FAILED") from None
    os.chmod(path, 0o600)

def write_private_replace(path, data):
    temporary = path.with_name(path.name + ".tmp")
    write_private_new(temporary, data)
    os.replace(temporary, path)
    os.chmod(path, 0o600)

def http_json(path, *, method="GET", payload=None, token=None):
    if not path.startswith("/api/") or path.startswith("//"):
        raise ProvisionError("BLOCKED_HTTP_PATH")
    headers = {"Host": TARGET_HOST, "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=8) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ProvisionError("RESPONSE_TOO_LARGE")
            content_type = response.headers.get("Content-Type", "")
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:
                parsed = None
            return response.status, content_type, parsed
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), None
    except ProvisionError:
        raise
    except Exception:
        raise ProvisionError("HTTP_REQUEST_FAILED") from None

def valid_json_type(content_type):
    return bool(re.match(
        r"^application/(?:[\w.+-]*\+)?json(?:\s*;|$)",
        content_type or "", re.IGNORECASE,
    ))

def run_readonly_smoke(token, expected_user):
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)
    local_date = now.date().isoformat()
    month = local_date[:7]
    groups = [
        ("U09", [("/users/me", "identity")]),
        ("U01", [("/dashboard/summary", "object")]),
        ("U02", [("/modules/domains", "array")]),
        ("U03", [("/tasks/summary", "object")]),
        ("U04", [
            ("/wellness/summary/daily?date=" + local_date, "object"),
            ("/wellness/summary/nutrition-trends?days=7", "array"),
        ]),
        ("U05", [("/finance/summary/monthly?month=" + month, "object")]),
        ("U06", [("/video/folders", "array"), ("/practice/subjects", "array")]),
        ("U07", [("/goals", "array")]),
        ("U08", [("/ai/conversations/page?limit=1", "object")]),
    ]
    cases = []
    stopped = False
    for case_id, checks in groups:
        if stopped:
            cases.append({"id": case_id, "state": "PENDING", "checks": []})
            continue
        results = []
        for index, (path, shape) in enumerate(checks, start=1):
            try:
                status, content_type, body = http_json("/api" + path, method="GET", token=token)
                if status != 200:
                    result = "HTTP_" + str(status)
                    if status in (401, 429):
                        stopped = True
                elif not valid_json_type(content_type) or not isinstance(body, dict):
                    result = "NOT_JSON"
                elif body.get("code") != "SUCCESS":
                    result = "RESPONSE_CONTRACT_MISMATCH"
                else:
                    data = body.get("data")
                    if shape == "identity":
                        okay = (
                            isinstance(data, dict)
                            and data.get("id") == expected_user["id"]
                            and data.get("username") == expected_user["username"]
                            and data.get("administrator") is False
                        )
                        result = "OK" if okay else "IDENTITY_MISMATCH"
                        if not okay:
                            stopped = True
                    else:
                        okay = isinstance(data, dict) if shape == "object" else isinstance(data, list)
                        result = "OK" if okay else "RESPONSE_CONTRACT_MISMATCH"
            except ProvisionError:
                result = "REQUEST_FAILED"
            results.append({"check": index, "result": result})
            if stopped:
                break
        passed = len(results) == len(checks) and all(x["result"] == "OK" for x in results)
        cases.append({
            "id": case_id,
            "state": "API_PASS" if passed else "REVIEW_REQUIRED",
            "checks": results,
        })
    all_pass = all(case["state"] == "API_PASS" for case in cases)
    return {
        "schemaVersion": 1,
        "source": "live_operator_runner",
        "state": "API_SMOKE_PASS" if all_pass else "API_SMOKE_INCOMPLETE",
        "cases": cases,
        "liveVerified": False,
        "deploymentAuthorized": False,
        "productionAuthorized": False,
    }

def provision_and_smoke():
    metadata = inspect_target()
    validate_target(metadata)
    prepare_private_dir()
    admin_rows = mysql_query(
        "SELECT id FROM prp_users WHERE is_admin=1 AND enabled=1 ORDER BY id LIMIT 1;"
    )
    if not admin_rows or not re.fullmatch(r"[1-9][0-9]*", admin_rows[0]):
        raise ProvisionError("BLOCKED_NO_ENABLED_STAGE_ADMIN")
    issuer_id = int(admin_rows[0])
    existing_uat = mysql_query(
        "SELECT COUNT(*) FROM prp_users WHERE LEFT(username, 8)='prp_uat_';"
    )
    if not existing_uat or existing_uat[0] != "0":
        raise ProvisionError("BLOCKED_EXISTING_UAT_ACCOUNT_REVIEW")

    username = "prp_uat_" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    invitation = secrets.token_urlsafe(32)
    invitation_hash = hashlib.sha256(invitation.encode("utf-8")).hexdigest()
    credentials = {
        "status": "provisioning",
        "target": TARGET_HOST,
        "username": username,
        "password": password,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "administrator": False,
        "mcp_grants_expected": 0,
    }
    write_private_new(CREDENTIAL_FILE, credentials)
    try:
        rows = mysql_query(
            "INSERT INTO prp_invitations (code_hash, issuer_user_id, expires_at) "
            "VALUES ('" + invitation_hash + "', " + str(issuer_id) +
            ", DATE_ADD(NOW(6), INTERVAL 1 DAY));\nSELECT ROW_COUNT();"
        )
        if not rows or rows[-1] != "1":
            raise ProvisionError("INVITATION_CREATE_FAILED")
        status, content_type, body = http_json(
            "/api/auth/register",
            method="POST",
            payload={
                "username": username,
                "password": password,
                "displayName": "PRP Unified Staging UAT",
                "invitationCode": invitation,
            },
        )
        data = body.get("data") if isinstance(body, dict) else None
        user = data.get("user") if isinstance(data, dict) else None
        token = data.get("token") if isinstance(data, dict) else None
        identity_ok = (
            status == 200 and valid_json_type(content_type)
            and body.get("code") == "SUCCESS"
            and isinstance(user, dict)
            and isinstance(user.get("id"), int)
            and user.get("username") == username
            and user.get("administrator") is False
            and data.get("tokenType") == "Bearer"
            and isinstance(data.get("expiresInSeconds"), int)
            and data.get("expiresInSeconds") > 0
            and isinstance(token, str)
            and bool(re.fullmatch(r"[-_A-Za-z0-9]+\.[-_A-Za-z0-9]+\.[-_A-Za-z0-9]+", token))
        )
        if not identity_ok:
            credentials["status"] = "registration_outcome_requires_manual_review"
            write_private_replace(CREDENTIAL_FILE, credentials)
            raise ProvisionError("REGISTRATION_OUTCOME_REQUIRES_REVIEW")

        user_id = user["id"]
        credentials.update({
            "status": "active",
            "user_id": user_id,
            "invitation_issuer_user_id": issuer_id,
        })
        write_private_replace(CREDENTIAL_FILE, credentials)

        grant_rows = mysql_query(
            "SELECT CONCAT("
            "(SELECT COUNT(*) FROM prp_mcp_client_grants WHERE user_id=" + str(user_id) + "), '|', "
            "(SELECT COUNT(*) FROM prp_mcp_identity_links WHERE user_id=" + str(user_id) + "), '|', "
            "(SELECT COUNT(*) FROM prp_mcp_link_tickets WHERE user_id=" + str(user_id) + "), '|', "
            "(SELECT COUNT(*) FROM prp_mcp_oidc_link_flows WHERE user_id=" + str(user_id) + ")"
            ");"
        )
        if not grant_rows or grant_rows[0] != "0|0|0|0":
            raise ProvisionError("BLOCKED_UNEXPECTED_MCP_LINK_OR_GRANT")

        report = run_readonly_smoke(token, {"id": user_id, "username": username})
        report["accountCreated"] = True
        report["ordinaryNonAdmin"] = True
        report["mcpGrantRows"] = 0
        write_private_new(REPORT_FILE, report)
        return report
    except ProvisionError:
        raise
    except Exception:
        raise ProvisionError("PROVISIONING_REQUIRES_MANUAL_REVIEW") from None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create-account-and-smoke", action="store_true",
        help="Create one ordinary UAT user and execute the bounded GET-only smoke.",
    )
    args = parser.parse_args()
    try:
        metadata = inspect_target()
        validate_target(metadata)
        if not args.create_account_and_smoke:
            print(json.dumps({
                "state": "PREFLIGHT_PASS",
                "target": TARGET_HOST,
                "project": PROJECT,
                "accountCreated": False,
                "writesPerformed": False,
            }, indent=2))
            return 0
        report = provision_and_smoke()
        print(json.dumps(report, indent=2))
        return 0 if report["state"] == "API_SMOKE_PASS" else 1
    except ProvisionError as exc:
        print(json.dumps({
            "state": "BLOCKED",
            "reason": str(exc),
            "writesPerformed": False if str(exc).startswith("BLOCKED") else "REVIEW_REQUIRED",
            "productionAccess": False,
        }, indent=2))
        return 2

if __name__ == "__main__":
    sys.exit(main())
