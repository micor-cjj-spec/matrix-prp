#!/usr/bin/env python3
"""Review a REDACTED Health V2 staging attestation; no network, Docker or secrets.

This checks declarations for contradictions; it cannot independently prove a live
service is safe, replace operator sign-off, or authorize any deployment/UAT.
"""
import argparse
import json
import re
import sys
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
_SECRET = re.compile(r"(?:password|secret|credential|private_key|access_token|refresh_token|authorization|cookie)", re.I)
_RESERVED_DB = {"matrix_prp", "matrix_prp_mcp_stage", "matrix_prp_mcp_newdb_review"}
_RESERVED_HOST = {"micor.top", "www.micor.top", "prp-test.micor.top", "auth-test.micor.top", "auth.micor.top"}
_RESERVED_PORT = {11000, 18081, 18082, 18083}


class EvidenceBlocked(ValueError):
    pass


def _need(value, code):
    if not value:
        raise EvidenceBlocked(code)


def _object(value, code):
    _need(type(value) is dict, code)
    return value


def _value(obj, key):
    if key not in obj:
        raise EvidenceBlocked("MISSING_" + key.upper())
    return obj[key]


def _host(value, code):
    _need(type(value) is str and 4 <= len(value) <= 253 and _HOST.fullmatch(value), code)
    labels = value.split(".")
    _need(len(labels) >= 2 and all(1 <= len(x) <= 63 and not x.startswith("-") and not x.endswith("-") for x in labels), code)
    _need(value not in _RESERVED_HOST, "SHARED_OR_PRODUCTION_HOST")
    return value


def _walk_no_secrets(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            _need(type(key) is str and not _SECRET.search(key), "SENSITIVE_FIELD_FORBIDDEN")
            _walk_no_secrets(value)
    elif isinstance(obj, list):
        for item in obj:
            _walk_no_secrets(item)


def review(evidence, expected_sha):
    """Validate the shape of self-reported evidence, not its real-world truth."""
    _need(type(expected_sha) is str and _SHA.fullmatch(expected_sha), "INVALID_EXPECTED_SHA")
    ev = _object(evidence, "INVALID_EVIDENCE")
    _walk_no_secrets(ev)
    _need(_value(ev, "schema") == "health-v2-stage-readiness-v1", "UNSUPPORTED_SCHEMA")
    stage = _object(_value(ev, "stage"), "INVALID_STAGE")
    observed = _object(_value(ev, "observed"), "INVALID_OBSERVED")

    _need(_value(stage, "kind") == "dedicated-health-v2", "NOT_DEDICATED_HEALTH_STAGE")
    host = _host(_value(stage, "public_host"), "INVALID_STAGE_HOST")
    oidc_host = _host(_value(stage, "oidc_host"), "INVALID_OIDC_HOST")
    _need(host != oidc_host, "OIDC_HOST_NOT_SEPARATE")
    port = _value(stage, "gateway_port")
    _need(type(port) is int and 1024 <= port <= 65535 and port not in _RESERVED_PORT, "GATEWAY_PORT_COLLISION")
    db = _value(stage, "database_name")
    _need(type(db) is str and re.fullmatch(r"[a-z][a-z0-9_]{5,63}", db) and db not in _RESERVED_DB, "SHARED_OR_PRODUCTION_DB")
    for key in ("db_isolated", "oidc_isolated", "test_identities_only", "owner_approved"):
        _need(_value(stage, key) is True, "STAGE_GUARD_" + key.upper())
    for key in ("production_mounts_present", "production_data_used", "shared_v2_modified"):
        _need(_value(stage, key) is False, "UNSAFE_" + key.upper())

    for key in ("source_sha", "backend_source_sha", "web_source_sha"):
        _need(_value(observed, key) == expected_sha, "SOURCE_SHA_MISMATCH")
    for key in ("backend_image_digest", "web_image_digest"):
        digest = _value(observed, key)
        _need(type(digest) is str and _IMAGE.fullmatch(digest), "IMAGE_DIGEST_UNVERIFIED")
    _need(_value(observed, "flyway_version") == 30 and type(_value(observed, "flyway_version")) is int, "FLYWAY_V30_NOT_VERIFIED")
    _need(_value(observed, "flyway_failed_count") == 0 and type(_value(observed, "flyway_failed_count")) is int, "FLYWAY_HISTORY_NOT_CLEAN")
    _need(_value(observed, "https_hostname_verified") is True, "HTTPS_NOT_VERIFIED")
    _need(_value(observed, "oidc_issuer_host") == oidc_host, "OIDC_ISSUER_MISMATCH")
    _need(_value(observed, "write_enabled") is False, "WRITES_MUST_REMAIN_DISABLED_BEFORE_UAT_APPROVAL")
    _need(_value(observed, "actual_runtime_observation") is True, "SOURCE_ONLY_NOT_RUNTIME_EVIDENCE")
    return "DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED"


def main(argv=None):
    p = argparse.ArgumentParser(description="Check redacted Health V2 staging evidence, OFFLINE and READ-ONLY")
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--expected-sha", required=True)
    args = p.parse_args(argv)
    try:
        _need(args.evidence.is_file() and args.evidence.stat().st_size <= 32768, "EVIDENCE_MISSING_OR_OVERSIZE")
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = review(data, args.expected_sha)
    except (EvidenceBlocked, ValueError, OSError, UnicodeError) as e:
        # Deliberately never prints raw evidence or sensitive field values.
        code = str(e) if isinstance(e, EvidenceBlocked) else "INVALID_EVIDENCE_FILE"
        print("BLOCKED:" + code)
        return 2
    print(result)
    print("REAL_HOST_VALIDATION=NOT_PERFORMED; UAT_APPROVAL=NOT_GRANTED; PRODUCTION_RELEASE=NO_GO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
