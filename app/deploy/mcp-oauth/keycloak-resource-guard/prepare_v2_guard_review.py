#!/usr/bin/env python3
"""Prepare a V2-compatible *review-only* guard pair from exact pinned sources.

Does not mutate /etc, active services, original host-guard, manifests,
approved-install.safe.json or fresh-b2-restore.safe.json. No install,
reload or approval action. A review pair still requires complete independent
Nginx, security/public-acceptance testing and separate human authorization.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path("/root/prp-mcp-cimd-stage-b")
REVIEW_PREFIX = "review-only-v2-guard-"
OLD = b"127.0.0.1:18081"
NEW = b"127.0.0.1:18082"

# Original B2 runbook and 2026-10-26 read-only operator SHA lineage.
PINNED = {
    "active_main": "ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b",
    "active_test": "35bb31322b23efef536c97e12619ceac7087aa4cf2d56c57f3307232f9362397",
    "backup_main": "ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b",
    "backup_test": "be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d",
    "guard_main": "da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b",
    "guard_test": "90814118bda4c8ca0be3d87ae36accb003a4be7f593954d552bfe05c1c98e6bd",
    "projected_test": "728b4a3290353f90ea692a2e1ae38a1656101e4381ee3bbdbce6c1cb80964421",
}
DEFAULT_FILES = {
    "active_main": Path("/etc/nginx/conf.d/micor.top.conf"),
    "active_test": Path("/etc/nginx/conf.d/prp-mcp-test.conf"),
    "backup_main": ROOT / "host-guard/install-backup-20261022T084744Z/micor.top.conf",
    "backup_test": ROOT / "host-guard/install-backup-20261022T084744Z/prp-mcp-test.conf",
    "guard_main": ROOT / "host-guard/micor.top.candidate.conf",
    "guard_test": ROOT / "host-guard/prp-test.guard-only.conf",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def secure_read(path):
    # O_NOFOLLOW + fstat prevent symlink substitution between lstat/open.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= 1024 * 1024:
            raise ValueError("Input is not a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) != st.st_size:
            raise ValueError("Input modified concurrently or oversized")
        return data
    finally:
        os.close(fd)


def build_review(files=DEFAULT_FILES, pinned=PINNED):
    source = {name: secure_read(files[name]) for name in DEFAULT_FILES}
    for name in DEFAULT_FILES:
        if sha(source[name]) != pinned[name]:
            raise ValueError("SOURCE_SHA256_MISMATCH:" + name)

    if source["active_main"] != source["backup_main"]:
        raise ValueError("DEFAULT_VHOST_DRIFT")
    current, backup = source["active_test"], source["backup_test"]
    if (current.count(NEW) != 2 or OLD in current
            or backup.count(OLD) != 2 or NEW in backup
            or current.replace(NEW, OLD) != backup):
        raise ValueError("ACTIVE_V2_NOT_EXACT_PORT_ONLY_LINEAGE")

    candidate = source["guard_test"]
    if candidate.count(OLD) != 2 or NEW in candidate:
        raise ValueError("GUARD_ONLY_SOURCE_NOT_EXPECTED")
    new_test = candidate.replace(OLD, NEW)
    if sha(new_test) != pinned["projected_test"]:
        raise ValueError("V2_GUARD_PROJECTION_SHA_MISMATCH")

    # Build both vhosts as an atomic review pair. Never modify the old guard.
    files_out = {
        "micor.top.guard-v2.REVIEW.conf": source["guard_main"],
        "prp-test.guard-v2.REVIEW.conf": new_test,
    }
    report = {
        "status": "REVIEW_ONLY_PINNED_PAIR_PREPARED",
        "source_sha256_verified": True,
        "active_v2_port_only_lineage_verified": True,
        "main_review_sha256": sha(source["guard_main"]),
        "test_review_sha256": sha(new_test),
        "test_loopback_18082_references": new_test.count(NEW),
        "test_loopback_18081_references": new_test.count(OLD),
        "nginx_syntax_tested": False,
        "public_security_acceptance_passed": False,
        "manifest_authorized": False,
        "host_guard_install_authorized": False,
        "b2_cutover_authorized": False,
        "active_configuration_changed": False,
    }
    return files_out, report


def write_review(root, target, files_out, report):
    # Review artifacts live only in a NEW directory immediately under the
    # historic task root. No existing directory or /etc target is permitted.
    if not target.is_absolute() or not target.name.startswith(REVIEW_PREFIX):
        raise ValueError("REVIEW_TARGET_MUST_USE_APPROVED_PREFIX")
    if target.parent.resolve(strict=True) != root.resolve(strict=True):
        raise ValueError("REVIEW_TARGET_MUST_BE_DIRECT_CHILD_OF_TASK_ROOT")
    if target.exists() or target.is_symlink():
        raise FileExistsError("REVIEW_TARGET_ALREADY_EXISTS")
    target.mkdir(mode=0o700)
    created = []
    try:
        for name, body in {
            **files_out,
            "review-report.json": (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        }.items():
            dest = target / name
            with os.fdopen(os.open(dest,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600), "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            created.append(dest)
    except Exception:
        # Only remove files created in this brand-new review directory.
        for file in created:
            file.unlink()
        target.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="V2 guard-only pair: safe SHA-based review, never install/approve"
    )
    parser.add_argument("--output-dir", type=Path,
                        help="Optional fresh review-only directory under the B2 task root")
    args = parser.parse_args()
    try:
        artifacts, report = build_review()
        if args.output_dir is not None:
            write_review(ROOT, args.output_dir, artifacts, report)
            report["review_files_written_outside_active_nginx"] = True
        else:
            report["review_files_written_outside_active_nginx"] = False
        print(json.dumps(report, sort_keys=True, indent=2))
    except (OSError, ValueError) as exc:
        # No input paths, raw config, or credentials are printed on failure.
        print(json.dumps({"status": "REVIEW_ONLY_BLOCKED",
                          "reason": type(exc).__name__,
                          "host_guard_install_authorized": False,
                          "b2_cutover_authorized": False,
                          "active_configuration_changed": False}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
