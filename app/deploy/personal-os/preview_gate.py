#!/usr/bin/env python3
"""Offline, fail-closed check of REDACTED Personal OS preview evidence.

This checks self-reported declarations and candidate source consistency only.
It does NOT inspect a live host, prove isolation, or approve any deployment.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z][a-z0-9_-]{5,62}\Z")
DB_NAME = re.compile(r"[a-z][a-z0-9_]{5,62}\Z")
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z")
SECRET_KEY = re.compile(r"password|secret|credential|private.?key|access.?token|refresh.?token|cookie|authorization", re.I)
RESERVED_HOSTS = {
    "micor.top", "www.micor.top", "prp-test.micor.top", "auth-test.micor.top",
    "auth.micor.top", "prp-health-test.micor.top",
}
RESERVED_PORTS = {11000, 18080, 18081, 18082, 18083, 18084}
RESERVED_DATABASES = {"matrix_prp", "matrix_prp_mcp_stage", "matrix_prp_mcp_newdb_review"}
ROOT_KEYS = {"schema", "stage", "observed"}
STAGE_KEYS = {
    "kind", "public_host", "gateway_port", "database_name", "compose_project",
    "isolated_host", "fresh_empty_database", "synthetic_users_only", "owner_approved",
    "production_mounts_present", "production_data_used", "existing_v2_modified",
}
OBSERVED_KEYS = {
    "source_sha", "backend_source_sha", "web_source_sha", "backend_image_digest",
    "web_image_digest", "flyway_version", "flyway_failed_count",
    "https_verified", "actual_runtime_observation", "mcp_enabled", "oauth_link_enabled",
    "automatic_chat_extraction_enabled", "model_egress_enabled", "mcp_write_enabled",
}
MIGRATIONS = {
    30: "V30__wellness_analysis_details.sql",
    31: "V31__personal_os_goals_and_assertions.sql",
}


class Blocked(ValueError):
    """Sanitized gate error; never include secrets or user data."""


def need(condition, code):
    if not condition:
        raise Blocked(code)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Blocked("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def safe_json_file(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 32768,
         "EVIDENCE_OR_POLICY_MISSING_OR_OVERSIZE")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, Blocked):
            raise
        raise Blocked("INVALID_JSON") from None


def exact_keys(obj, keys, code):
    need(type(obj) is dict, "INVALID_" + code)
    need(not any(SECRET_KEY.search(str(k)) for k in obj), "SENSITIVE_FIELD_FORBIDDEN")
    need(set(obj) == keys, "UNRECOGNIZED_" + code + "_FIELDS")


def valid_host(host):
    need(type(host) is str and len(host) <= 253, "INVALID_HOST")
    need(host not in RESERVED_HOSTS, "RESERVED_OR_IP_HOST")
    parts = host.split(".")
    need(len(parts) >= 3 and all(1 <= len(p) <= 63 and HOST_LABEL.fullmatch(p) for p in parts), "INVALID_HOST")
    need(host not in RESERVED_HOSTS and not all(part.isdecimal() for part in parts), "RESERVED_OR_IP_HOST")
    need(host != "localhost" and not host.endswith(".localhost") and not host.endswith(".local"), "LOCAL_HOST_FORBIDDEN")


def verify_candidate_migrations(candidate_root):
    """Compare V30/V31 policy SHA256 to actual candidate SQL bytes, never run SQL."""
    root = Path(candidate_root)
    policy = safe_json_file(root / "app/deploy/migration-policy.json")
    need(type(policy) is dict and policy.get("schema_version") == 1 and
         type(policy.get("rules")) is list, "INVALID_MIGRATION_POLICY")
    matches = {}
    seen = set()
    for rule in policy["rules"]:
        need(type(rule) is dict and type(rule.get("version")) is int,
             "INVALID_MIGRATION_RULE")
        version = rule["version"]
        need(version not in seen, "DUPLICATE_MIGRATION_VERSION")
        seen.add(version)
        if version in MIGRATIONS:
            need(rule.get("file") == MIGRATIONS[version] and
                 rule.get("mode") == "create-empty" and
                 type(rule.get("sha256")) is str and
                 re.fullmatch(r"[0-9a-f]{64}", rule["sha256"]),
                 "MIGRATION_POLICY_MISMATCH")
            matches[version] = rule
    need(set(matches) == set(MIGRATIONS) and bool(seen) and max(seen) == 31,
         "REVIEWED_V30_V31_MIGRATIONS_REQUIRED")
    for version, filename in MIGRATIONS.items():
        path = root / "app/backend/src/main/resources/db/migration" / filename
        need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 1048576,
             "SQL_FILE_MISSING_OR_OVERSIZE")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        need(matches[version]["sha256"] == digest, "MIGRATION_SHA256_MISMATCH")


def review(doc, expected_sha, candidate_root):
    need(type(expected_sha) is str and SHA.fullmatch(expected_sha), "INVALID_EXPECTED_SHA")
    exact_keys(doc, ROOT_KEYS, "ROOT")
    need(doc["schema"] == "personal-os-preview-v1", "UNSUPPORTED_SCHEMA")
    stage, observed = doc["stage"], doc["observed"]
    exact_keys(stage, STAGE_KEYS, "STAGE")
    exact_keys(observed, OBSERVED_KEYS, "OBSERVED")
    need(stage["kind"] == "dedicated-personal-os", "NOT_DEDICATED_PREVIEW")
    valid_host(stage["public_host"])
    port = stage["gateway_port"]
    need(type(port) is int and 1024 <= port <= 65535 and port not in RESERVED_PORTS,
         "GATEWAY_PORT_RESERVED")
    db, project = stage["database_name"], stage["compose_project"]
    need(type(db) is str and DB_NAME.fullmatch(db) and db.startswith("prp_pos_") and
         db not in RESERVED_DATABASES and not db.startswith("matrix_prp"), "SHARED_DATABASE")
    need(type(project) is str and NAME.fullmatch(project) and project.startswith("prp-pos-"),
         "INVALID_COMPOSE_PROJECT")
    for key in ("isolated_host", "fresh_empty_database", "synthetic_users_only", "owner_approved"):
        need(stage[key] is True, "STAGE_GUARD_" + key.upper())
    for key in ("production_mounts_present", "production_data_used", "existing_v2_modified"):
        need(stage[key] is False, "STAGE_GUARD_" + key.upper())
    for key in ("source_sha", "backend_source_sha", "web_source_sha"):
        need(observed[key] == expected_sha, "SOURCE_SHA_MISMATCH")
    for key in ("backend_image_digest", "web_image_digest"):
        need(type(observed[key]) is str and IMAGE.fullmatch(observed[key]), "IMAGE_DIGEST_MISSING")
    need(type(observed["flyway_version"]) is int and observed["flyway_version"] == 31,
         "FLYWAY_VERSION_MISMATCH")
    need(type(observed["flyway_failed_count"]) is int and observed["flyway_failed_count"] == 0,
         "FLYWAY_FAILURE_OR_UNVERIFIED")
    for key in ("https_verified", "actual_runtime_observation"):
        need(observed[key] is True, "RUNTIME_GUARD_" + key.upper())
    for key in ("mcp_enabled", "oauth_link_enabled", "automatic_chat_extraction_enabled",
                "model_egress_enabled", "mcp_write_enabled"):
        need(observed[key] is False, "PREVIEW_FEATURE_MUST_BE_OFF_" + key.upper())
    verify_candidate_migrations(candidate_root)
    return "DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline, no-network Personal OS preview gate")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--candidate-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = review(safe_json_file(args.evidence), args.expected_sha, args.candidate_root)
    except (Blocked, OSError, TypeError) as exc:
        code = str(exc) if isinstance(exc, Blocked) else "EVIDENCE_UNREADABLE"
        print("NO_GO:" + code)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
