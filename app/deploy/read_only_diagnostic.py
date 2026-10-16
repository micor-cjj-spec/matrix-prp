#!/usr/bin/python3 -I
"""Root-only, fixed-path deployment failure classifier.

This is NOT a raw log reader. It emits a fixed-schema, secret-free report.
The approved forced SSH gateway may expose it as the literal "diagnose"
command after independent administrator review and installation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import stat

LOG_PATH = Path("/var/lib/matrix-prp-deploy/last-error.log")
MAX_BYTES = 64 * 1024
MAX_AGE_SECONDS = 2 * 3600
KNOWN_TABLES = frozenset(('prp_ai_agent_tasks', 'prp_ai_codex_jobs', 'prp_ai_conversation_meta', 'prp_ai_conversations', 'prp_ai_message_blocks', 'prp_ai_messages', 'prp_ai_preferences', 'prp_ai_provider_credentials', 'prp_ai_tool_audit', 'prp_ai_usage', 'prp_finance_accounts', 'prp_finance_categories', 'prp_finance_transactions', 'prp_finance_transfers', 'prp_invitations', 'prp_notification_deliveries', 'prp_notification_messages', 'prp_notification_rules', 'prp_practice_ai_usage', 'prp_practice_attempts', 'prp_practice_banks', 'prp_practice_imports', 'prp_practice_questions', 'prp_practice_subjects', 'prp_push_subscriptions', 'prp_record_tags', 'prp_records', 'prp_reviews', 'prp_tags', 'prp_tasks', 'prp_users', 'prp_video_assets', 'prp_video_folders', 'prp_video_progress', 'prp_video_uploads', 'prp_wellness_ai_action_targets', 'prp_wellness_ai_drafts', 'prp_wellness_body_metrics', 'prp_wellness_dish_templates', 'prp_wellness_exercises', 'prp_wellness_foods', 'prp_wellness_goals', 'prp_wellness_meal_items', 'prp_wellness_meals', 'prp_wellness_profiles'))
HISTORICAL_ROW = re.compile(
    r"Historical row changed or deleted['\"],\s*['\"](prp_[a-z][a-z0-9_]{0,62})['\"]"
)
APPROVED_STAGES = (
    ("assert_preserved", "preservation_check"),
    ("rehearse", "migration_rehearsal"),
    ("deploy_backend", "backend_deploy"),
    ("migrate", "database_migration"),
    ("check", "health_check"),
    ("deploy", "deployment"),
)
SAFE_ERRORS = {
    "AssertionError", "ValueError", "RuntimeError", "CalledProcessError",
    "TimeoutExpired", "PermissionError", "FileNotFoundError", "OSError",
}


def classify(trace: str) -> dict[str, str | None]:
    # Never return traceback lines, SQL, rows, primary keys or free text.
    result: dict[str, str | None] = {
        "code": "DEPLOY_ERROR_UNKNOWN",
        "stage": "unknown",
        "table": None,
        "exception": None,
    }
    for function, stage in APPROVED_STAGES:
        if re.search(r"\bin " + re.escape(function) + r"\s*(?:\n|$)", trace):
            result["stage"] = stage
            break

    found = re.findall(r"(?m)^(?:[\w.]*\.)?(\w+):", trace)
    if found and found[-1] in SAFE_ERRORS:
        result["exception"] = found[-1]

    match = HISTORICAL_ROW.search(trace)
    if match and match.group(1) in KNOWN_TABLES:
        result.update(code="PRESERVED_ROW_CHANGED", stage="preservation_check", table=match.group(1))
    elif "Unexpected new business table" in trace:
        result.update(code="UNEXPECTED_BUSINESS_TABLE", stage="preservation_check")
    elif "Unexpected records in new table" in trace:
        result.update(code="UNEXPECTED_MIGRATION_ROWS", stage="preservation_check")
    elif "Existing food row changed or deleted" in trace:
        result.update(code="PRESERVED_FOOD_CHANGED", stage="preservation_check")
    elif "Video ownership or records changed" in trace:
        result.update(code="PRESERVED_VIDEO_CHANGED", stage="preservation_check")
    elif "assert_preserved" in trace and "AssertionError" in trace:
        result.update(code="PRESERVATION_ASSERTION", stage="preservation_check")
    elif "Flyway" in trace or "Migration failed" in trace:
        result.update(code="MIGRATION_FAILED", stage="database_migration")
    elif "CalledProcessError" in trace:
        result["code"] = "DEPLOY_COMMAND_FAILED"
    return result


def report(path: Path = LOG_PATH, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    base = {
        "schema_version": 1,
        "state": "no_log",
        "code": "NO_DIAGNOSTIC",
        "stage": "unknown",
        "table": None,
        "exception": None,
        "timestamp_utc": None,
    }
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as file:
            st = os.fstat(file.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o022:
                return {**base, "state": "unavailable", "code": "DIAGNOSTIC_UNAVAILABLE"}
            if st.st_size == 0:
                return base
            age = now.timestamp() - st.st_mtime
            if age < -300 or age > MAX_AGE_SECONDS:
                return {**base, "state": "stale", "code": "STALE_DIAGNOSTIC"}
            file.seek(max(0, st.st_size - MAX_BYTES))
            raw = file.read(MAX_BYTES).decode("utf-8", errors="replace")
        utc = datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(microsecond=0)
        return {
            **base,
            **classify(raw),
            "state": "available",
            "timestamp_utc": utc.isoformat().replace("+00:00", "Z"),
        }
    except FileNotFoundError:
        return base
    except (OSError, ValueError, OverflowError):
        return {**base, "state": "unavailable", "code": "DIAGNOSTIC_UNAVAILABLE"}


def main() -> int:
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 2
    # Only allowlist fields can reach stdout. Never print caught exceptions.
    print(json.dumps(report(), ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
