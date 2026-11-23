#!/usr/bin/env python3
"""Health V30 synthetic-user smoke, ONLY on an approved disposable GitHub PR runner.

Never use real hosts, user accounts, backups, secrets or production.
The env file is generated in RUNNER_TEMP by smoke_disposable.sh and discarded.
Only fixed, loopback HTTP endpoints are contacted; tokens are never logged.
"""
import json
import os
from pathlib import Path
import secrets
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:23080"
HOST = "prp-unified.example.org"


def guard():
    expected = (
        os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.getenv("GITHUB_REPOSITORY") == "micor-cjj-spec/matrix-prp"
        and os.getenv("GITHUB_EVENT_NAME") == "pull_request"
        and os.getenv("GITHUB_BASE_REF") == "dev"
        and len(sys.argv) == 2
    )
    if not expected or not os.getenv("RUNNER_TEMP"):
        raise RuntimeError("DISPOSABLE_PR_RUNNER_ONLY")
    path = Path(sys.argv[1])
    if (path.is_symlink() or path.parent.resolve() != Path(os.environ["RUNNER_TEMP"]).resolve()
            or not path.name.startswith("prp-unified-stage-ci-")
            or path.suffix != ".env" or not path.is_file()):
        raise RuntimeError("UNTRUSTED_CI_ENVFILE")
    values = dict(line.split("=", 1) for line in path.read_text(encoding="ascii").splitlines()
                  if "=" in line)
    if (values.get("PRP_UNIFIED_PUBLIC_HOST") != HOST
            or values.get("PRP_UNIFIED_LOOPBACK_PORT") != "23080"
            or values.get("PRP_UNIFIED_BOOTSTRAP_USERNAME") != "synthetic_stage_owner"
            or not values.get("PRP_UNIFIED_BOOTSTRAP_PASSWORD")):
        raise RuntimeError("CI_ENV_VALUES_NOT_ISOLATED")
    return values


def http(path, token=None, data=None):
    if not path.startswith("/api/") or any(x in path for x in ("\r", "\n", "#", "//")):
        raise RuntimeError("UNREVIEWED_LOCAL_ENDPOINT")
    headers = {"Host": HOST, "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    else:
        payload = None
    req = Request(BASE + path, headers=headers, data=payload,
                  method="POST" if data is not None else "GET")
    try:
        with urlopen(req, timeout=8) as result:
            code = result.status
            body = result.read(300_000)
    except HTTPError as error:
        code = error.code
        body = b""
    except (OSError, URLError) as error:
        raise RuntimeError("CI_LOOPBACK_HTTP_UNAVAILABLE") from error
    if code != 200:
        return code, None
    try:
        parsed = json.loads(body)
        if not isinstance(parsed, dict) or "data" not in parsed:
            raise ValueError("missing data")
        return code, parsed["data"]
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("INVALID_CI_API_RESPONSE") from error


def data(path, token=None, payload=None):
    status, content = http(path, token, payload)
    if status != 200:
        raise RuntimeError("HEALTH_SYNTHETIC_HTTP_UNEXPECTED_STATUS")
    return content


def rejected(path, token=None):
    status, _ = http(path, token)
    if status not in (401, 403, 404):
        raise RuntimeError("HEALTH_SYNTHETIC_ACCESS_NOT_DENIED")


def verify():
    config = guard()
    rejected("/api/wellness/summary/nutrition-trends?days=7")
    login = data("/api/auth/login", payload={
        "username": config["PRP_UNIFIED_BOOTSTRAP_USERNAME"],
        "password": config["PRP_UNIFIED_BOOTSTRAP_PASSWORD"],
    })
    owner_a = login.get("token")
    if not isinstance(owner_a, str) or len(owner_a) < 30:
        raise RuntimeError("CI_OWNER_A_TOKEN_UNAVAILABLE")
    invitation = data("/api/auth/invitations", owner_a, {})
    code = invitation.get("code") if isinstance(invitation, dict) else None
    if not code:
        raise RuntimeError("CI_TEST_INVITATION_UNAVAILABLE")
    owner_b_data = data("/api/auth/register", payload={
        "username": "ci_health_" + secrets.token_hex(6),
        "password": secrets.token_urlsafe(24),
        "displayName": "Synthetic CI Health Owner B",
        "invitationCode": code,
    })
    owner_b = owner_b_data.get("token") if isinstance(owner_b_data, dict) else None
    if not isinstance(owner_b, str) or len(owner_b) < 30:
        raise RuntimeError("CI_OWNER_B_TOKEN_UNAVAILABLE")

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    unique_key = "ci-v30-" + secrets.token_hex(12)
    meal = {
        "mealDate": today, "mealType": "LUNCH",
        "note": "Synthetic CI health V30 item; discard with runner",
        "idempotencyKey": unique_key,
        "items": [{"name": "Synthetic CI test meal", "grams": 100, "calories": 123}],
    }
    created = data("/api/wellness/meals/snapshots", owner_a, meal)
    meal_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(meal_id, int) or meal_id <= 0:
        raise RuntimeError("HEALTH_SYNTHETIC_MEAL_NOT_CREATED")
    replayed = data("/api/wellness/meals/snapshots", owner_a, meal)
    if replayed.get("id") != meal_id:
        raise RuntimeError("HEALTH_SYNTHETIC_IDEMPOTENCY_FAILED")
    meals_a = data("/api/wellness/meals?date=" + today, owner_a)
    meals_b = data("/api/wellness/meals?date=" + today, owner_b)
    if not isinstance(meals_a, list) or len(meals_a) != 1 or meals_b != []:
        raise RuntimeError("HEALTH_SYNTHETIC_CROSS_OWNER_LIST_LEAK")

    details = data("/api/wellness/meals/" + str(meal_id) + "/analysis", owner_a)
    if (not isinstance(details, dict)
            or details.get("meal", {}).get("id") != meal_id
            or details.get("analyses") != []
            or details.get("nutrients") != []):
        raise RuntimeError("HEALTH_SYNTHETIC_V30_EMPTY_ENRICHMENT_FAILED")
    rejected("/api/wellness/meals/" + str(meal_id) + "/analysis", owner_b)

    trends_a = data("/api/wellness/summary/nutrition-trends?days=7", owner_a)
    trends_b = data("/api/wellness/summary/nutrition-trends?days=7", owner_b)
    if not isinstance(trends_a, list) or not isinstance(trends_b, list):
        raise RuntimeError("HEALTH_SYNTHETIC_TRENDS_INVALID")
    row_a = next((row for row in trends_a if row.get("date") == today), None)
    row_b = next((row for row in trends_b if row.get("date") == today), None)
    if (row_a is None or row_b is None
            or row_a.get("foodItemCount") != 1
            or row_a.get("knownProteinCount") != 0
            or row_a.get("proteinG") is not None
            or row_b.get("foodItemCount") != 0
            or row_b.get("proteinG") is not None):
        raise RuntimeError("HEALTH_SYNTHETIC_UNKNOWN_MACRO_OR_OWNER_TREND_FAILED")
    print("PASS: synthetic Health V30 meal idempotency, empty analysis, unknown macro, cross-owner denial")
    print("CI_HEALTH_V30_REAL_HTTP_SYNTHETIC_ONLY=PASS")


if __name__ == "__main__":
    try:
        verify()
    except Exception:
        # Deliberately do not print exception bodies/URLs/request payloads/tokens.
        print("FAIL: synthetic Health V30 isolated HTTP contract", file=sys.stderr)
        sys.exit(1)
