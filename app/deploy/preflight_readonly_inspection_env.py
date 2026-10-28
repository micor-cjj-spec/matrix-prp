#!/usr/bin/env python3
"""Fail-closed local validation of the existing PRP read-only SSH workflow.

Only checks *presence and basic shape* of env values. No network, no
GitHub API, no SSH call, no input value printed, no deployment authority.
This check does not confirm that an SSH endpoint can be reached.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys


def valid_host(value: str) -> bool:
    if not value or len(value) > 253 or value != value.strip():
        return False
    if any(ord(c) < 33 or ord(c) > 126 for c in value):
        return False
    try:
        return not ipaddress.ip_address(value).is_unspecified
    except ValueError:
        pass
    if value.endswith("."):
        value = value[:-1]
    labels = value.split(".")
    return bool(labels) and all(
        len(label) <= 63 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


def valid_private_key(value: str) -> bool:
    normalized = value.strip()
    return (
        len(normalized) >= 100
        and normalized.startswith((
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
        ))
        and normalized.endswith("-----END PRIVATE KEY-----")
        or (
            len(normalized) >= 100
            and normalized.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
            and normalized.endswith("-----END OPENSSH PRIVATE KEY-----")
        )
        or (
            len(normalized) >= 100
            and normalized.startswith("-----BEGIN RSA PRIVATE KEY-----")
            and normalized.endswith("-----END RSA PRIVATE KEY-----")
        )
        or (
            len(normalized) >= 100
            and normalized.startswith("-----BEGIN EC PRIVATE KEY-----")
            and normalized.endswith("-----END EC PRIVATE KEY-----")
        )
    )


def valid_host_keys(value: str) -> bool:
    # Actual host signature matching is independently enforced later
    # by ssh-keygen -F and OpenSSH StrictHostKeyChecking=yes.
    return bool(value.strip()) and len(value) <= 128 * 1024 and "\x00" not in value


def check(values: dict[str, str]) -> bool:
    return all(
        isinstance(values.get(field), str) for field in (
            "INSPECT_KEY", "INSPECT_KNOWN_HOSTS", "INSPECT_HOST"
        )
    ) and (
        valid_private_key(values["INSPECT_KEY"])
        and valid_host_keys(values["INSPECT_KNOWN_HOSTS"])
        and valid_host(values["INSPECT_HOST"])
    )


def main() -> int:
    values = {
        field: os.environ.get(field, "") for field in (
            "INSPECT_KEY", "INSPECT_KNOWN_HOSTS", "INSPECT_HOST"
        )
    }
    if not check(values):
        print("INSPECTION_CONNECTION_CONFIG_MISSING_OR_INVALID", file=sys.stderr)
        return 2
    print("INSPECTION_CONNECTION_ENV_SHAPE_VALID_NOT_CONNECTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
