#!/usr/bin/env python3
"""Offline review of an existing Deploy PRP artifact. Never publishes or authorizes."""
import argparse
import datetime as dt
import hashlib
import json
import re
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = "micor-cjj-spec/matrix-prp"
REPO_ID = 1261866723
MAX_BYTES = 800 * 1024 * 1024
MAX_FILES = 10000
MAX_JSON = 2 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def positive(v):
    return type(v) is int and v > 0


def hexstr(v, n):
    return type(v) is str and re.fullmatch("[a-f0-9]{" + str(n) + "}", v) is not None


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def parse_json(raw):
    require(len(raw) <= MAX_JSON, "JSON_TOO_LARGE")
    data = json.loads(raw, object_pairs_hook=unique)
    require(type(data) is dict, "INVALID_JSON_OBJECT")
    return data


def read_json(path):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= MAX_JSON,
            "INVALID_METADATA_FILE")
    return parse_json(path.read_bytes())


def utc(v):
    require(type(v) is str and v.endswith("Z"), "INVALID_TIMESTAMP")
    return dt.datetime.fromisoformat(v[:-1] + "+00:00")


def digest_stream(source, target=None, limit=MAX_BYTES):
    digest = hashlib.sha256()
    size = 0
    while True:
        block = source.read(1024 * 1024)
        if not block:
            break
        size += len(block)
        require(size <= limit, "ARTIFACT_SIZE_LIMIT")
        digest.update(block)
        if target is not None:
            target.write(block)
    return digest.hexdigest(), size


def valid_name(name):
    return (type(name) is str and len(name) <= 512 and
            re.fullmatch(r"[A-Za-z0-9._/-]+", name) is not None and
            all(part not in ("", ".", "..") for part in name.split("/")))


def provenance(snapshot, commit, now):
    require(type(snapshot) is dict and set(snapshot) == {"run", "jobs", "artifacts"},
            "INVALID_PROVENANCE_SHAPE")
    run, jobs, artifacts = (snapshot[k] for k in ("run", "jobs", "artifacts"))
    require(all(type(v) is dict for v in (run, jobs, artifacts)), "INVALID_METADATA_OBJECT")
    require(run.get("name") == "Deploy PRP" and run.get("path") == ".github/workflows/deploy-prp.yml"
            and run.get("event") == "workflow_run" and run.get("head_branch") == "main"
            and run.get("head_sha") == commit and run.get("status") == "completed"
            and run.get("conclusion") == "success" and positive(run.get("id"))
            and positive(run.get("run_attempt"))
            and (run.get("head_repository") or {}).get("full_name") == REPO
            and (run.get("repository") or {}).get("full_name") == REPO,
            "UNSUPPORTED_RELEASE_RUN")
    records = jobs.get("jobs")
    require(type(records) is list and type(jobs.get("total_count")) is int
            and 0 < len(records) == jobs["total_count"] <= 100, "INCOMPLETE_JOBS")
    require(all(type(j) is dict and positive(j.get("id")) and j.get("run_id") == run["id"]
                and j.get("run_attempt") == run["run_attempt"] and j.get("head_sha") == commit
                and j.get("status") == "completed" for j in records), "JOB_BINDING_MISMATCH")
    require(len({j["id"] for j in records}) == len(records), "DUPLICATE_JOB")
    for name in ("release_control", "build"):
        match = [j for j in records if j.get("name") == name]
        require(len(match) == 1 and match[0].get("conclusion") == "success",
                "REQUIRED_BUILD_JOB_NOT_SUCCESS")
    require(all(j.get("conclusion") in ("success", "skipped") for j in records),
            "UNSUCCESSFUL_JOB")
    items = artifacts.get("artifacts")
    require(type(items) is list and type(artifacts.get("total_count")) is int
            and len(items) == artifacts["total_count"] <= 100
            and all(type(a) is dict for a in items), "INCOMPLETE_ARTIFACTS")
    match = [a for a in items if a.get("name") == "prp-release"]
    require(len(match) == 1, "AMBIGUOUS_RELEASE_ARTIFACT")
    item = match[0]
    wr = item.get("workflow_run")
    require(type(wr) is dict and wr.get("id") == run["id"] and wr.get("head_sha") == commit
            and wr.get("head_branch") == "main" and wr.get("repository_id") == REPO_ID
            and wr.get("head_repository_id") == REPO_ID and positive(item.get("id"))
            and item.get("expired") is False and utc(item.get("expires_at")) > now,
            "STALE_OR_UNBOUND_ARTIFACT")
    digest = item.get("digest")
    require(type(digest) is str and digest.startswith("sha256:") and hexstr(digest[7:], 64),
            "MISSING_GITHUB_ARCHIVE_DIGEST")
    return run, item


def verify_tar(stream, expected, release_id):
    files, seen, meta, policy = {}, set(), None, None
    size = 0
    # No extraction, execution, or use of filesystem paths from the archive.
    with tarfile.open(fileobj=stream, mode="r|gz") as tar:
        for member in tar:
            name = member.name
            require(valid_name(name) and name not in seen and len(seen) < MAX_FILES
                    and (member.isfile() or member.isdir()), "UNSAFE_TAR_MEMBER")
            seen.add(name)
            require(name in ("release.json", "migration-policy.json", "backend.jar", "web")
                    or name.startswith("web/"), "UNEXPECTED_TAR_MEMBER")
            if member.isdir():
                require(name == "web" or name.startswith("web/"), "UNEXPECTED_DIRECTORY")
                continue
            require(name != "web" and 0 <= member.size <= MAX_BYTES, "INVALID_MEMBER")
            size += member.size
            require(size <= MAX_BYTES, "ARTIFACT_SIZE_LIMIT")
            src = tar.extractfile(member)
            require(src is not None, "MISSING_MEMBER")
            with src:
                if name in ("release.json", "migration-policy.json"):
                    require(member.size <= MAX_JSON, "JSON_TOO_LARGE")
                    raw = src.read(MAX_JSON + 1)
                    value = parse_json(raw)
                    if name == "release.json":
                        meta = value
                    else:
                        policy = value
                        files[name] = hashlib.sha256(raw).hexdigest()
                else:
                    checksum, count = digest_stream(src, limit=member.size)
                    require(count == member.size, "MEMBER_SIZE_MISMATCH")
                    files[name] = checksum
    require(type(meta) is dict and set(meta) == {"id", "commit", "schema_version",
            "backend_source", "web_source", "files"}, "INVALID_RELEASE_MANIFEST")
    require(meta["id"] == release_id and meta["commit"] == expected["commit"]
            and type(meta["schema_version"]) is int and meta["schema_version"] == expected["schema"]
            and meta["backend_source"] == expected["backend_source"]
            and meta["web_source"] == expected["web_source"], "MANIFEST_BINDING_MISMATCH")
    require(meta["files"] == files and {"backend.jar", "web/index.html", "migration-policy.json"}
            <= set(files), "MANIFEST_CHECKSUM_MISMATCH")
    require(type(policy) is dict and policy.get("commit") == expected["commit"],
            "MIGRATION_POLICY_COMMIT_MISMATCH")
    return len(files)


def review(expected, snapshot, archive, now=None):
    require(type(expected) is dict and set(expected) == {"commit", "schema", "backend_source", "web_source"}
            and hexstr(expected["commit"], 40) and hexstr(expected["backend_source"], 40)
            and hexstr(expected["web_source"], 64) and type(expected["schema"]) is int
            and 7 <= expected["schema"] <= 1000, "INVALID_EXPECTED_CANDIDATE")
    run, item = provenance(snapshot, expected["commit"], now or dt.datetime.now(dt.timezone.utc))
    archive = Path(archive)
    require(not archive.is_symlink() and archive.is_file() and 0 < archive.stat().st_size <= MAX_BYTES,
            "INVALID_ARCHIVE_FILE")
    release_id = "r" + str(run["id"]) + "-" + str(run["run_attempt"])
    with archive.open("rb") as raw:
        checksum, _ = digest_stream(raw)
        require("sha256:" + checksum == item["digest"], "GITHUB_ARCHIVE_DIGEST_MISMATCH")
        raw.seek(0)
        with zipfile.ZipFile(raw) as outer:
            members = outer.infolist()
            require(len(members) == 1 and members[0].filename == "release.tar.gz"
                    and not members[0].is_dir() and not stat.S_ISLNK(members[0].external_attr >> 16)
                    and 0 < members[0].file_size <= MAX_BYTES, "UNSAFE_GITHUB_ARCHIVE")
            with tempfile.TemporaryFile() as inner, outer.open(members[0]) as payload:
                tar_digest, size = digest_stream(payload, inner)
                require(size == members[0].file_size, "TAR_SIZE_MISMATCH")
                inner.seek(0)
                count = verify_tar(inner, expected, release_id)
    artifact_digest = "sha256:" + tar_digest
    # This is only an asserted evidence record. Feed it to the existing offline
    # inventory if independently reviewed. No trusted source is established here.
    return {"schema_version": 1, "state": "LOCAL_BYTES_MATCH_REVIEW_INPUT",
            "commit": expected["commit"], "schema": expected["schema"],
            "run_id": run["id"], "run_attempt": run["run_attempt"], "artifact_id": item["id"],
            "github_archive_digest": item["digest"], "release_tar_digest": artifact_digest,
            "file_count": count, "evidence_trust": "unverified_caller_metadata",
            "artifact_evidence": {"source": "build_manifest", "environment": "review",
                "commit": expected["commit"], "status": "pass",
                "ref": "github:artifact:" + str(item["id"]),
                "artifact_digest": artifact_digest, "schema": expected["schema"]},
            "release_eligible": False, "deployment_authorized": False, "live_verified": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("expected", "snapshot", "archive", "output"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    paths = (args.expected, args.snapshot, args.archive, args.output)
    require(len({p.resolve() for p in paths}) == len(paths), "PATH_COLLISION")
    require(not args.output.is_symlink() and not args.output.exists(), "OUTPUT_EXISTS")
    try:
        result = review(read_json(args.expected), read_json(args.snapshot), args.archive)
    except (ValueError, TypeError, OSError, AttributeError, OverflowError, EOFError,
            tarfile.TarError, zipfile.BadZipFile, RuntimeError):
        print("ARTIFACT_REVIEW_BLOCKED")
        return 1
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
