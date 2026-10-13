#!/usr/bin/env python3
"""Fail-closed SHA256 attestation of the root-owned production controller.

A restricted forced SSH command returns a single standard sha256sum line.
This verifier never executes the production controller or accesses secrets.
"""
from __future__ import annotations
import argparse
import hmac
import json
from pathlib import Path
import re
import sys

CONTROLLER_PATH = "/usr/local/sbin/prp-release"
HASH_RE = re.compile(r"[a-f0-9]{64}\Z")
RESPONSE_RE = re.compile(r"([a-f0-9]{64})  /usr/local/sbin/prp-release\Z")


class AttestationError(ValueError):
    """Fail closed for unknown or unapproved production controller."""


def approved_sha256(manifest: dict) -> str:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise AttestationError("Unsupported controller manifest schema")
    approval = manifest.get("approved_controller")
    if not isinstance(approval, dict) or approval.get("path") != CONTROLLER_PATH:
        raise AttestationError("Unexpected approved controller path")
    digest = approval.get("sha256")
    if not isinstance(digest, str) or HASH_RE.fullmatch(digest) is None:
        raise AttestationError("Missing or malformed approved SHA256")
    return digest


def verify_response(manifest: dict, output: str) -> str:
    expected = approved_sha256(manifest)
    # Permit an optional final newline, but never banners or multiple lines.
    if output.endswith("\n"):
        output = output[:-1]
    match = RESPONSE_RE.fullmatch(output)
    if match is None:
        raise AttestationError("Malformed or missing production controller attestation")
    actual = match.group(1)
    if not hmac.compare_digest(actual, expected):
        raise AttestationError("Production deploy controller drift detected; deployment blocked")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        response = args.response.read_text(encoding="utf-8")
        attested = verify_response(manifest, response)
    except (AttestationError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("::error::PRP controller verification failed: " + str(exc), file=sys.stderr)
        return 1
    print("Production controller SHA256 attested: " + attested)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
