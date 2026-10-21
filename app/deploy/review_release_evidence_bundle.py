#!/usr/bin/env python3
"""ENG-03G: read-only cross-binding of supplied deployment + CI evidence.

An offline audit aid, NEVER a production approval or independent attestation.
Trust cannot be inferred from JSON or bare hashes. No network, host access,
SQL execution, token processing, gateway change or live database operation.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from reconcile_running_release import (
    load, sha, verify as verify_running_release, require_dict_keys
)

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
CHECKS = {
    "localhost_health", "unauthorized_rejected", "login_and_user_identity",
    "finance_write_read", "tenant_isolation",
}
RECEIPT_FIELDS = {
    "schema_version", "classification", "production_deployment_attested",
    "production_authorized", "label", "source_commit", "jar_sha256", "checks",
}
RELEASE_FIELDS = {"id", "commit", "schema_version", "backend_source", "web_source", "files"}
GATES = (
    "P1_REAL_BACKUP_AUTHENTICITY",
    "P2_RESTORED_REAL_BACKUP_PRESERVATION",
    "P3_ACTUAL_MYSQL_DDL_AND_SCHEMA",
    "P4_METADATA_LOCK_TRAFFIC_REHEARSAL",
    "P5_REAL_PREVIOUS_AND_CANDIDATE_BINARY_COMPATIBILITY",
    "P6_REVIEWED_FLYWAY_SQL_SOURCE_AND_ARTIFACT",
    "P7_APPROVED_EXPAND_CONTROLLER_PATCH",
    "P8_INDEPENDENT_ROOT_AND_SSH_ATTESTATION",
    "P9_POST_CUTOVER_VERIFICATION",
)


def receipt(raw, label):
    result = load(raw, 8192)
    require_dict_keys(result, RECEIPT_FIELDS)
    if (type(result["schema_version"]) is not int or result["schema_version"] != 1 or
            result["classification"] != "CI_SYNTHETIC_JAR_HTTP_PROBE" or
            result["production_deployment_attested"] is not False or
            result["production_authorized"] is not False or
            result["label"] != label):
        raise ValueError("Invalid CI synthetic receipt")
    if (not isinstance(result["source_commit"], str) or
            not COMMIT.fullmatch(result["source_commit"]) or
            not isinstance(result["jar_sha256"], str) or
            not HEX64.fullmatch(result["jar_sha256"])):
        raise ValueError("Invalid source/JAR fingerprints")
    require_dict_keys(result["checks"], CHECKS)
    if any(value != "PASS" for value in result["checks"].values()):
        raise ValueError("Incomplete synthetic HTTP probes")
    return result


def release_metadata(raw):
    result = load(raw, 131072)
    require_dict_keys(result, RELEASE_FIELDS)
    if (not isinstance(result["commit"], str) or
            not COMMIT.fullmatch(result["commit"]) or
            type(result["schema_version"]) is not int or
            not 1 <= result["schema_version"] <= 1000 or
            not isinstance(result["id"], str) or not 1 <= len(result["id"]) <= 80):
        raise ValueError("Malformed candidate release")
    if type(result["files"]) is not dict or not 1 <= len(result["files"]) <= 3000:
        raise ValueError("Invalid candidate file digests")
    for name in ("backend.jar", "web/index.html"):
        value = result["files"].get(name)
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError("Missing artifact file digest")
    return result


def verify_bundle(
    host_observation_raw: bytes,
    deployed_release_raw: bytes,
    controller_manifest_raw: bytes,
    candidate_release_raw: bytes,
    baseline_ci_raw: bytes,
    candidate_ci_raw: bytes,
    *, now: datetime | None = None,
) -> dict:
    """All six artifacts are caller-supplied and UNTRUSTED until separately attested."""
    running = verify_running_release(
        host_observation_raw, deployed_release_raw, controller_manifest_raw, now=now)
    baseline = receipt(baseline_ci_raw, "baseline")
    candidate_ci = receipt(candidate_ci_raw, "candidate")
    deployed = release_metadata(deployed_release_raw)
    candidate = release_metadata(candidate_release_raw)
    if baseline["source_commit"] == candidate_ci["source_commit"]:
        raise ValueError("Separate baseline and candidate commits required")
    if (candidate["commit"] != candidate_ci["source_commit"] or
            candidate["files"]["backend.jar"] != candidate_ci["jar_sha256"]):
        raise ValueError("Candidate release artifact does not match candidate CI JAR")
    if candidate["schema_version"] < deployed["schema_version"]:
        raise ValueError("Candidate would downgrade schema")
    if (candidate["commit"] == deployed["commit"] or
            candidate["id"] == deployed["id"]):
        raise ValueError("Cannot treat active release as a distinct candidate")
    # One and only one candidate from the same supplied source tree. A hash
    # match is not a signature and does not authenticate build provenance.
    baseline_matches_deployed = (
        baseline["source_commit"] == running["release_commit"] and
        baseline["jar_sha256"] == running["backend_jar_sha256"]
    )
    # No real production restore, trusted live host source, real old binary
    # or DBA sign-off is supplied; NEVER treat them as passed.
    gates = {name: "NOT_VERIFIED" for name in GATES}
    gates["P5_REAL_PREVIOUS_AND_CANDIDATE_BINARY_COMPATIBILITY"] = (
        "CI_ONLY_BASELINE_DIGEST_MATCH_UNATTESTED" if baseline_matches_deployed
        else "BLOCKED_BASELINE_NOT_RUNNING_RELEASE"
    )
    gates["P6_REVIEWED_FLYWAY_SQL_SOURCE_AND_ARTIFACT"] = (
        "CANDIDATE_JAR_DIGEST_MATCH_CI_ONLY"
    )
    gates["P7_APPROVED_EXPAND_CONTROLLER_PATCH"] = (
        "EXISTING_CONTROLLER_DIGEST_MATCH_ONLY"
    )
    return {
        "schema_version": 1,
        "classification": "PRODUCTION_REVIEW_BLOCKED",
        "production_authorized": False,
        "publication_gate_passed": False,
        "live_host_independently_attested": False,
        "trusted_artifact_provenance_attested": False,
        "real_backup_rehearsal_completed": False,
        "runtime_jar_matches_supplied_ci_baseline": baseline_matches_deployed,
        "running_release_commit": running["release_commit"],
        "candidate_release_commit": candidate["commit"],
        "running_backend_jar_sha256": running["backend_jar_sha256"],
        "candidate_backend_jar_sha256": candidate["files"]["backend.jar"],
        "reviewed_inputs_sha256": {
            "host_observation": sha(host_observation_raw),
            "deployed_release": sha(deployed_release_raw),
            "controller_manifest": sha(controller_manifest_raw),
            "candidate_release": sha(candidate_release_raw),
            "baseline_ci_receipt": sha(baseline_ci_raw),
            "candidate_ci_receipt": sha(candidate_ci_raw),
        },
        "approval_gates": gates,
        "required_next_action": "INDEPENDENT_HUMAN_AND_DBA_REVIEW",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="ENG-03G offline, non-authorizing evidence review")
    for arg in ("host-observation", "deployed-release", "controller-manifest",
                "candidate-release", "baseline-ci-receipt", "candidate-ci-receipt"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        verdict = verify_bundle(
            args.host_observation.read_bytes(),
            args.deployed_release.read_bytes(),
            args.controller_manifest.read_bytes(),
            args.candidate_release.read_bytes(),
            args.baseline_ci_receipt.read_bytes(),
            args.candidate_ci_receipt.read_bytes(),
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        print(json.dumps({
            "schema_version": 1, "classification": "EVIDENCE_REJECTED",
            "production_authorized": False, "publication_gate_passed": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
