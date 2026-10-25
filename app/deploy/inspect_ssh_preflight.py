#!/usr/bin/env python3
"""Fail-closed credential/host validation for the manual read-only inspector.

No network requests. No secret values, SSH stderr, key material or hostnames
are logged or persisted as evidence. Never authorizes a production change.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess

HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")


def valid_host(host: str) -> bool:
    return bool(HOST.fullmatch(host) and all(
        label and len(label) <= 63 and not label.startswith("-")
        and not label.endswith("-") for label in host.split(".")))


def _probe(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command, check=False, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=8, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def prepare(values: dict[str, str], identity: Path, known_hosts: Path) -> str:
    key = values.get("PRP_INSPECT_SSH_KEY", "")
    known = values.get("PRP_INSPECT_KNOWN_HOSTS", "")
    host = values.get("PRP_INSPECT_HOST", "")
    if not key.strip():
        return "INSPECT_KEY_MISSING"
    if not known.strip():
        return "INSPECT_KNOWN_HOSTS_MISSING"
    if not host.strip():
        return "INSPECT_HOST_MISSING"
    if not valid_host(host):
        return "INSPECT_HOST_INVALID"
    try:
        identity.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Exclusively create files: never replace a pre-existing identity.
        for path, value in ((identity, key), (known_hosts, known)):
            with path.open("x", encoding="utf-8") as stream:
                os.chmod(path, 0o600)
                stream.write(value.rstrip("\r\n") + "\n")
        if not _probe(["ssh-keygen", "-y", "-P", "", "-f", str(identity)]):
            return "INSPECT_KEY_INVALID"
        # A successful parse of an unrelated known_hosts entry is not enough:
        # the exact configured host must have a pin, including hashed pins.
        if not _probe(["ssh-keygen", "-F", host, "-f", str(known_hosts)]):
            return "INSPECT_HOST_KEY_NOT_PINNED"
        return "INSPECT_PREFLIGHT_VALID"
    except (OSError, UnicodeError, ValueError):
        return "INSPECT_FILESYSTEM_UNAVAILABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    names = ("PRP_INSPECT_SSH_KEY", "PRP_INSPECT_KNOWN_HOSTS", "PRP_INSPECT_HOST")
    result = prepare({name: os.environ.get(name, "") for name in names},
                     args.identity, args.known_hosts)
    # The workflow owns cleanup of the isolated RUNNER_TEMP directory.
    # Never delete a preexisting file after exclusive-creation failure.
    print("INSPECT_SSH_PREFLIGHT=" + result)
    try:
        with args.summary.open("a", encoding="utf-8") as stream:
            stream.write("\nRead-only SSH prerequisite: \u0060" + result + "\u0060. No secret contents checked into logs.\n")
    except OSError:
        # Failure to publish a summary cannot turn a negative result positive.
        if result == "INSPECT_PREFLIGHT_VALID":
            return 2
    return 0 if result == "INSPECT_PREFLIGHT_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
