#!/usr/bin/env python3
"""Offline S0 inventory JSON shape review; NEVER host or deployment approval.

Reads one LOCAL JSON file. Does not execute Docker, SSH or any host command.
Prints only fixed status/reason codes; never echoes source contents or secrets.
A well-formed report does not prove server identity, free ports or readiness.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

PORTS = {"11000", "18081", "18082", "18083"}
HINTS = {
    "production_name_hint", "legacy_18081_name_hint", "v2_18082_name_hint",
    "newdb_18083_name_hint", "unified_stage_candidate_hint",
}
ROOT = {
    "schema_version", "observed_utc", "scope", "ports",
    "project_name_hints", "capacity", "host_identity_verified",
    "docker_metadata_proves_ownership", "dns_tls_keycloak_database_flyway_verified",
    "staging_deployment_authorized", "production_deployment_authorized",
    "new_stage_ready", "absence_is_not_availability_proof",
}
HOST_STATES = {"UNKNOWN", "LISTENER_OBSERVED", "NO_LISTENER_OBSERVED"}
PUBLISH_STATES = {"UNKNOWN_QUERY", "PUBLISHED_TCP_OBSERVED", "NO_PUBLISH_OBSERVED"}
NAME_STATES = {"UNKNOWN_QUERY", "NAME_MATCH_OBSERVED", "NO_NAME_MATCH_OBSERVED"}
CAPACITY_STATES = {"UNKNOWN", "ABOVE_REVIEW_THRESHOLD", "BELOW_REVIEW_THRESHOLD"}


def exact_dict(value, keys):
    return isinstance(value, dict) and set(value) == keys


def is_enum(value, allowed):
    return isinstance(value, str) and value in allowed


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def assess(document, *, now=None):
    """Fail closed. Valid means FORMAT ONLY, never an authorized host."""
    problems = set()
    if not exact_dict(document, ROOT):
        problems.add("TOP_LEVEL_SCHEMA_MISMATCH")
    else:
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            problems.add("SCHEMA_VERSION_INVALID")
        if document["scope"] != "POINT_IN_TIME_READ_ONLY_METADATA":
            problems.add("SCOPE_INVALID")
        for key in (
            "host_identity_verified", "docker_metadata_proves_ownership",
            "dns_tls_keycloak_database_flyway_verified",
            "staging_deployment_authorized", "production_deployment_authorized",
        ):
            if document[key] is not False:
                problems.add("UNTRUSTED_AUTHORIZATION_FLAG")
        if document["new_stage_ready"] != "NOT_ESTABLISHED" or document["absence_is_not_availability_proof"] is not True:
            problems.add("UNTRUSTED_READINESS_FLAG")
        ports = document["ports"]
        if not exact_dict(ports, PORTS):
            problems.add("PORT_SCHEMA_INVALID")
        elif any(not exact_dict(v, {"host_tcp", "docker_tcp_publish"})
                 or not is_enum(v["host_tcp"], HOST_STATES)
                 or not is_enum(v["docker_tcp_publish"], PUBLISH_STATES)
                 for v in ports.values()):
            problems.add("PORT_STATE_INVALID")
        projects = document["project_name_hints"]
        if not exact_dict(projects, HINTS):
            problems.add("PROJECT_HINT_SCHEMA_INVALID")
        elif any(not exact_dict(v, {"containers", "volumes", "networks"})
                 or any(not is_enum(state, NAME_STATES) for state in v.values())
                 for v in projects.values()):
            problems.add("PROJECT_HINT_STATE_INVALID")
        capacity = document["capacity"]
        if not exact_dict(capacity, {
            "available_memory_2gib", "root_free_disk_25gib",
            "thresholds_are_heuristics_not_sizing_approval",
        }):
            problems.add("CAPACITY_SCHEMA_INVALID")
        elif (not is_enum(capacity["available_memory_2gib"], CAPACITY_STATES)
              or not is_enum(capacity["root_free_disk_25gib"], CAPACITY_STATES)
              or capacity["thresholds_are_heuristics_not_sizing_approval"] is not True):
            problems.add("CAPACITY_STATE_INVALID")
        timestamp = document["observed_utc"]
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            problems.add("TIMESTAMP_INVALID")
        else:
            try:
                observed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
                current = now or datetime.now(timezone.utc)
                if observed > current + timedelta(minutes=5):
                    problems.add("TIMESTAMP_FUTURE")
                elif current - observed > timedelta(hours=24):
                    problems.add("REPORT_OLDER_THAN_24H")
            except ValueError:
                problems.add("TIMESTAMP_INVALID")
    return {
        "s0_report_format": "VALID" if not problems else "REJECTED",
        "reason_codes": sorted(problems),
        "operator_host_identity_confirmation": "REQUIRED",
        "port_ownership_and_isolation_confirmation": "REQUIRED",
        "stage_deployment_authorized": False,
        "production_deployment_authorized": False,
        "stage_readiness": "NOT_ESTABLISHED",
    }


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"s0_report_format": "REJECTED", "reason_codes": ["ONE_LOCAL_JSON_PATH_REQUIRED"],
                          "stage_deployment_authorized": False, "production_deployment_authorized": False}))
        return 2
    try:
        path = Path(sys.argv[1])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024:
            raise ValueError("UNTRUSTED_OR_OVERSIZE_LOCAL_REPORT")
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
        result = assess(data)
    except (OSError, ValueError, UnicodeError, TypeError):
        result = {
            "s0_report_format": "REJECTED", "reason_codes": ["UNREADABLE_OR_INVALID_JSON"],
            "operator_host_identity_confirmation": "REQUIRED",
            "port_ownership_and_isolation_confirmation": "REQUIRED",
            "stage_deployment_authorized": False, "production_deployment_authorized": False,
            "stage_readiness": "NOT_ESTABLISHED",
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["s0_report_format"] == "VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
