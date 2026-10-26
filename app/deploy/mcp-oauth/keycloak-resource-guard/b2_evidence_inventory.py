#!/usr/bin/env python3
"""Read-only B2 operator inventory: presence is NOT authorization or recovery proof.

The script does not read private JSON content, secrets, Keycloak DB records,
Nginx configuration contents or TLS keys, and does not write any files.
It cannot approve, install, reload or bypass the B2 gate.
"""
import argparse
import json
import os
import stat
from pathlib import Path

REQUIRED = {
    "approved_install": "approved-install.safe.json",
    "fresh_b2_restore": "fresh-b2-restore.safe.json",
}
DEFAULT_ROOT = Path("/root/prp-mcp-cimd-stage-b/host-guard")
DEFAULT_PG_DUMP = Path("/root/prp-mcp-backups/snapshot-4G42atvf/keycloak-stage.dump")
EXPECTED_DUMP_BYTES_MAGIC = "PGDMP"  # informational; not read by this tool


def classify(path: Path):
    try:
        # lstat refuses to mistake a symlink for an authentic evidence file.
        item = path.lstat()
    except FileNotFoundError:
        return "MISSING"
    except PermissionError:
        return "ACCESS_DENIED"
    except OSError:
        return "METADATA_ERROR"
    if not stat.S_ISREG(item.st_mode):
        return "UNSAFE_NONREGULAR_OR_SYMLINK"
    if item.st_size == 0:
        return "EMPTY"
    if item.st_mode & 0o077:
        return "WEAK_FILE_PERMISSIONS"
    if item.st_mode & 0o6000:
        return "UNSAFE_SPECIAL_PERMISSIONS"
    if item.st_uid != 0:
        return "NONROOT_OWNER_REVIEW_REQUIRED"
    return "PRESENT_METADATA_ONLY_UNVERIFIED"


def examine(root: Path, dump: Path):
    # The root directory itself is also untrusted evidence. No control is
    # considered approved just because a file was put at the expected path.
    out = {"host_guard_directory": "UNCHECKED", "requirements": {}}
    try:
        info = root.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            out["host_guard_directory"] = "UNSAFE_PATH"
        elif info.st_uid != 0 or info.st_mode & 0o022:
            out["host_guard_directory"] = "UNSAFE_OWNER_OR_PERMISSIONS"
        else:
            out["host_guard_directory"] = "METADATA_OK_UNVERIFIED"
    except FileNotFoundError:
        out["host_guard_directory"] = "MISSING"
    except (PermissionError, OSError):
        out["host_guard_directory"] = "METADATA_ERROR"

    for name, filename in REQUIRED.items():
        out["requirements"][name] = (
            classify(root / filename)
            if out["host_guard_directory"] == "METADATA_OK_UNVERIFIED"
            else "NOT_INSPECTED_UNSAFE_PARENT"
        )
    out["snapshot_dump"] = classify(dump)
    out["operator_restore_test"] = (
        "PASSED_SEPARATELY_OPERATOR_REPORTED_NOT_A_B2_RECEIPT"
    )
    out["b2_authorization"] = "BLOCKED_UNTIL_INDEPENDENT_REVIEW"
    out["deployment_permitted"] = False
    return out


def main():
    parser = argparse.ArgumentParser(description="Read-only metadata inventory, never gate approval")
    parser.add_argument("--guard-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dump", type=Path, default=DEFAULT_PG_DUMP)
    args = parser.parse_args()
    # Neither glob nor traversal nor file read. Never expose supplied paths.
    print(json.dumps(examine(args.guard_root, args.dump), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
