#!/usr/bin/env python3
"""Pin and syntax-check V2 raw-URI REVIEW artifacts; never deploy or reload.

Only examines the known, fixed review directory. Rebuilds the candidate from
SHA-pinned source bytes and checks exact equality, hashes, and the review
manifest. Uses a separate temporary Nginx config with a synthetic certificate.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

import isolated_v2_nginx_syntax as isolated
import prepare_v2_raw_uri_review as candidate

ROOT = isolated.ROOT
REVIEW_DIR = ROOT / "review-only-v2-guard-20261027-rawuri-01"
PINNED_MAIN = "da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b"
PINNED_TEST = "9210c70352be9633bb72de18bb803c72b4629cfa173dd8667d8d091420bbbbfc"
REQUIRED = {candidate.MAIN_FILENAME, candidate.TEST_FILENAME, "review-report.json"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_files(directory=REVIEW_DIR, root=ROOT):
    # No command-line directory override, symlink traversal or shared writable
    # configuration paths. The fixed task root is outside /etc/nginx.
    directory = Path(directory)
    root = Path(root)
    if (directory.parent != root
            or not directory.name.startswith("review-only-v2-guard-")):
        raise ValueError("REVIEW_DIRECTORY_OUTSIDE_ALLOWED_PARENT")
    for path in (root, directory):
        s = path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_mode & 0o022:
            raise ValueError("REVIEW_DIRECTORY_PERMISSIONS_UNSAFE")
    if directory.stat().st_mode & 0o777 != 0o700:
        raise ValueError("REVIEW_DIRECTORY_NOT_PRIVATE")
    names = set(os.listdir(directory))
    if names != REQUIRED:
        raise ValueError("REVIEW_DIRECTORY_CONTENTS_DRIFT")
    result = {}
    for name in REQUIRED:
        path = directory / name
        st = path.lstat()
        if (not stat.S_ISREG(st.st_mode)
                or st.st_nlink != 1 or st.st_mode & 0o777 != 0o600):
            raise ValueError("REVIEW_FILE_METADATA_UNSAFE")
        result[name] = isolated.read_regular(path)
    return result


def verify_artifact(files=None, sources=None, expected_main=PINNED_MAIN,
                    expected_test=PINNED_TEST):
    if files is None:
        files = checked_files()
    if sources is None:
        sources = isolated.inspect_sources()
    regenerated, original_report = candidate.build(sources)
    actual_main = files[candidate.MAIN_FILENAME]
    actual_test = files[candidate.TEST_FILENAME]
    if (sha(actual_main) != expected_main or
            sha(actual_test) != expected_test):
        raise ValueError("NEW_REVIEW_CANDIDATE_SHA256_DRIFT")
    if actual_main != regenerated[candidate.MAIN_FILENAME]:
        raise ValueError("REVIEW_MAIN_DIFFERS_FROM_REGENERATED_SOURCE")
    if actual_test != regenerated[candidate.TEST_FILENAME]:
        raise ValueError("REVIEW_TEST_DIFFERS_FROM_TWO_GUARD_PROJECTION")
    manifest = json.loads(files["review-report.json"].decode("utf-8"))
    for key, value in original_report.items():
        if manifest.get(key) != value:
            raise ValueError("REVIEW_MANIFEST_LINEAGE_DRIFT")
    if set(manifest) != set(original_report):
        raise ValueError("REVIEW_MANIFEST_UNREVIEWED_FIELD")
    return actual_main, actual_test, {
        "review_directory_contents_verified": True,
        "review_main_candidate_sha256": sha(actual_main),
        "review_test_candidate_sha256": sha(actual_test),
        "source_four_sha256_pins_verified": True,
        "main_unchanged_from_old_review": True,
        "test_exactly_two_raw_uri_guards_against_old_review": True,
        "review_manifest_provenance_verified": True,
    }


def check_nginx(candidate_pair, sources, *, temp_parent=ROOT):
    nginx, openssl = shutil.which("nginx"), shutil.which("openssl")
    if not nginx or not openssl:
        raise ValueError("ISOLATED_NGINX_OR_OPENSSL_MISSING")
    with tempfile.TemporaryDirectory(prefix="v2-rawuri-review-syntax-", dir=temp_parent) as work:
        temp = Path(work)
        result = subprocess.run([
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-keyout", str(temp / "key.pem"),
            "-out", str(temp / "cert.pem"), "-subj", "/CN=localhost",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if result.returncode:
            raise ValueError("SYNTHETIC_CERTIFICATE_FAILED")
        actual = dict(sources)
        actual["review_main"], actual["review_test"] = candidate_pair
        transformed = isolated.prepare(actual, temp)
        existing_zone, active_files = isolated.recover_single_active_rate_limit(temp)
        cfg = temp / "nginx.conf"
        cfg.write_text(
            "worker_processes 1;\n"
            "pid " + str(temp / "nginx.pid") + ";\n"
            "error_log " + str(temp / "nginx-error.log") + " warn;\n"
            "events { worker_connections 16; }\n"
            "http {\n  " + existing_zone + "\n"
            "  include " + str(temp / "main.conf") + ";\n"
            "  include " + str(temp / "test.conf") + ";\n}\n",
            encoding="utf-8")
        process = subprocess.run([
            nginx, "-t", "-p", str(temp) + "/", "-c", str(cfg),
            "-e", str(temp / "nginx-error.log")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if process.returncode:
            # Never print raw stderr, config, paths or cert material.
            return {
                "syntax_passed": False,
                "exit_code": process.returncode,
                "sanitized_error": isolated.classify_nginx_failure(
                    (process.stdout + b"\n" + process.stderr).decode("utf-8", "replace")),
            }
        return {
            "syntax_passed": True,
            "exit_code": 0,
            "dependency_config_files_scanned": active_files,
            "synthetic_tls_only": True,
            "transformed": transformed,
            "no_nginx_listener_started": True,
        }


def execute():
    os.umask(0o077)
    files = checked_files()
    sources = isolated.inspect_sources()
    main, test, report = verify_artifact(files, sources)
    syntax = check_nginx((main, test), sources)
    return {
        "status": ("V2_RAW_URI_REVIEW_ARTIFACT_VERIFIED"
                   if syntax["syntax_passed"] else
                   "V2_RAW_URI_REVIEW_NGINX_SYNTAX_FAILED"),
        **report,
        "isolated_nginx_syntax": syntax,
        "production_nginx_installed_or_reloaded": False,
        "keycloak_changed": False,
        "b2_approved": False,
        "public_route_acceptance_tested": False,
        "chatgpt_oauth_proven": False,
        "release_approved": False,
    }


if __name__ == "__main__":
    try:
        output = execute()
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        output = {
            "status": "V2_RAW_URI_REVIEW_ARTIFACT_BLOCKED",
            "blocker": str(error) if isinstance(error, ValueError) else
                       type(error).__name__,
            "production_nginx_installed_or_reloaded": False,
            "b2_approved": False,
            "release_approved": False,
        }
    print(json.dumps(output, indent=2, sort_keys=True))
    if output["status"] != "V2_RAW_URI_REVIEW_ARTIFACT_VERIFIED":
        sys.exit(2)
