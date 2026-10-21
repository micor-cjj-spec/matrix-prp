#!/usr/bin/env python3
"""ENG-03F: fail-closed reconciliation of *supplied* immutable release metadata.

This does NOT query production, authenticate a host, or authorize deployment.
A match of submitted JSON cannot establish independent host provenance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HEX64 = re.compile(r"[a-f0-9]{64}\Z")
COMMIT = re.compile(r"[a-f0-9]{40}\Z")
STAMP = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
RELEASE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
OBS_KEYS = {"schema_version", "source", "observed_utc", "service_active",
            "process_jar_path_verified", "release", "controller_sha256",
            "production_authorized", "independent_attestation_completed"}
REL_KEYS = {"id", "commit", "schema_version", "backend_jar_sha256", "release_metadata_sha256"}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate evidence key")
        result[key] = value
    return result


def load(raw, limit):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= limit:
        raise ValueError("Invalid evidence size")
    return json.loads(raw, object_pairs_hook=unique_pairs)


def require_dict_keys(obj, fields):
    if type(obj) is not dict or set(obj) != fields:
        raise ValueError("Invalid evidence shape")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(observation_raw: bytes, release_raw: bytes, manifest_raw: bytes,
           *, now=None) -> dict:
    observation = load(observation_raw, 8192)
    release = load(release_raw, 131072)
    manifest = load(manifest_raw, 131072)
    require_dict_keys(observation, OBS_KEYS)
    require_dict_keys(observation["release"], REL_KEYS)
    if (type(observation["schema_version"]) is not int or observation["schema_version"] != 1 or
            observation["source"] != "MANUAL_ROOT_READ_ONLY" or
            observation["service_active"] is not True or
            observation["process_jar_path_verified"] is not True or
            observation["production_authorized"] is not False or
            observation["independent_attestation_completed"] is not False):
        raise ValueError("Untrusted or falsely authorizing observation")
    stamp = observation["observed_utc"]
    if not isinstance(stamp, str) or not STAMP.fullmatch(stamp):
        raise ValueError("Invalid observation time")
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Must use UTC-aware current time")
    age = (current - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds()
    if not -60 <= age <= 600:
        raise ValueError("Stale or future evidence")

    observed = observation["release"]
    if not isinstance(observed["id"], str) or not RELEASE_ID.fullmatch(observed["id"]):
        raise ValueError("Invalid release identifier")
    if not isinstance(observed["commit"], str) or not COMMIT.fullmatch(observed["commit"]):
        raise ValueError("Invalid commit")
    if type(observed["schema_version"]) is not int or not 1 <= observed["schema_version"] <= 1000:
        raise ValueError("Invalid schema version")
    for key in ("backend_jar_sha256", "release_metadata_sha256"):
        if not isinstance(observed[key], str) or not HEX64.fullmatch(observed[key]):
            raise ValueError("Invalid evidence digest")

    require_dict_keys(release, {"id", "commit", "schema_version", "backend_source", "web_source", "files"})
    if not isinstance(release["files"], dict) or not 1 <= len(release["files"]) <= 3000:
        raise ValueError("Malformed release artifact file list")
    digest = release["files"].get("backend.jar")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ValueError("Missing artifact JAR digest")
    if type(release["schema_version"]) is not int:
        raise ValueError("Release schema version type")
    if (release["id"] != observed["id"] or release["commit"] != observed["commit"] or
            release["schema_version"] != observed["schema_version"] or
            digest != observed["backend_jar_sha256"] or
            sha(release_raw) != observed["release_metadata_sha256"]):
        raise ValueError("Running JAR does not match exact supplied release metadata")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("approved_controller"), dict):
        raise ValueError("Invalid reviewed controller manifest")
    approved = manifest["approved_controller"].get("sha256")
    if (not isinstance(approved, str) or not HEX64.fullmatch(approved) or
            not isinstance(observation["controller_sha256"], str) or
            not HEX64.fullmatch(observation["controller_sha256"]) or
            observation["controller_sha256"] != approved):
        raise ValueError("Controller is not the reviewed digest")
    return {
        "schema_version": 1,
        "classification": "MATCHES_SUPPLIED_METADATA_REVIEW_REQUIRED",
        "checked_observed_utc": stamp,
        "release_id": observed["id"],
        "release_commit": observed["commit"],
        "schema_version_observed": observed["schema_version"],
        "backend_jar_sha256": digest,
        "matched_controller_manifest": True,
        "process_path_consistency_claim": True,
        "live_host_independently_attested": False,
        "real_production_jar_verification_completed": False,
        "production_authorized": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Offline only: review supplied running JAR identity")
    p.add_argument("--observation", type=Path, required=True)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = verify(args.observation.read_bytes(), args.release.read_bytes(),
                        args.manifest.read_bytes())
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        print(json.dumps({"schema_version": 1, "classification": "EVIDENCE_REJECTED",
                          "production_authorized": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
