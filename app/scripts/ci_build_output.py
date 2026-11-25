#!/usr/bin/env python3
"""Stage only CI rehearsal build outputs, not a production release."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = "micor-cjj-spec/matrix-prp"
PR = "412"
LIMIT = 800 * 1024 * 1024


def require(value, reason):
    if not value:
        raise ValueError(reason)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def positive(s):
    return isinstance(s, str) and re.fullmatch(r"[1-9][0-9]{0,17}", s) is not None


def context(root, kind, env):
    sha = git(root, "rev-parse", "HEAD")
    require(env.get("GITHUB_REPOSITORY") == REPO and env.get("GITHUB_EVENT_NAME") == "pull_request"
            and env.get("GITHUB_REF") == "refs/pull/" + PR + "/merge"
            and env.get("GITHUB_WORKFLOW") == "CI" and env.get("GITHUB_SHA") == sha
            and re.fullmatch(r"[0-9a-f]{40}", sha) is not None
            and positive(env.get("GITHUB_RUN_ID")) and positive(env.get("GITHUB_RUN_ATTEMPT"))
            and env.get("GITHUB_JOB") == {"backend":"backend-tests", "web":"web-build"}[kind],
            "NOT_EXACT_REHEARSAL_CONTEXT")
    return {"schema_version": 1, "repository": REPO, "pull_request": int(PR),
            "tested_commit": sha, "run_id": int(env["GITHUB_RUN_ID"]),
            "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]), "kind": kind,
            "job": env["GITHUB_JOB"], "scope": "CI_REHEARSAL_ONLY",
            "source_tree": git(root, "rev-parse", "HEAD:app/backend" if kind=="backend" else "HEAD:app/web"),
            "production_authorized": False}


def copy_payload(src, dest, budget):
    require(src.is_file() and not src.is_symlink(), "INVALID_PAYLOAD")
    size = src.stat().st_size
    require(0 < size <= budget, "PAYLOAD_SIZE_LIMIT")
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    with src.open("rb") as inp, dest.open("xb") as out:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            total += len(block)
            require(total <= size, "PAYLOAD_CHANGED")
            digest.update(block)
            out.write(block)
    require(total == size, "PAYLOAD_CHANGED")
    return {"sha256": digest.hexdigest(), "size": total}


def stage(root, output, kind, metadata):
    require(kind in ("backend", "web"), "INVALID_KIND")
    require(not output.exists() and not output.is_symlink(), "OUTPUT_EXISTS")
    require(metadata["kind"] == kind and metadata["scope"] == "CI_REHEARSAL_ONLY"
            and metadata["production_authorized"] is False, "INVALID_CONTEXT")
    if kind == "backend":
        jar = root / "app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar"
        require(not any(p.is_symlink() for p in (jar.parent, jar.parent.parent, jar.parent.parent.parent)),
                "INVALID_PAYLOAD_ROOT")
        sources = [(jar, "backend.jar")]
    else:
        dist = root / "app/web/dist"
        require(dist.is_dir() and not any(p.is_symlink() for p in (dist, dist.parent, dist.parent.parent)),
                "INVALID_PAYLOAD_ROOT")
        entries = sorted(dist.rglob("*"))
        require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in entries),
                "UNSAFE_WEB_PAYLOAD")
        sources = [(p, "web/" + p.relative_to(dist).as_posix()) for p in entries if p.is_file()]
        require(any(name == "web/index.html" for _, name in sources), "WEB_INDEX_MISSING")
    require(0 < len(sources) <= 10000, "PAYLOAD_COUNT_LIMIT")
    require(all(re.fullmatch(r"[A-Za-z0-9._/-]+", name) and
                all(x not in ("", ".", "..") for x in name.split("/"))
                for _, name in sources), "INVALID_PAYLOAD_PATH")
    output.mkdir()
    try:
        files = {}
        budget = LIMIT
        for src, name in sources:
            entry = copy_payload(src, output / name, budget)
            budget -= entry["size"]
            files[name] = entry
        manifest = dict(metadata, files=files)
        (output / "ci-output.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n",
                                               encoding="utf-8")
        return manifest
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=("backend", "web"), required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    # Only fixed, fresh runner scratch output, not the repo or arbitrary paths.
    require(args.output == temp / ("prp-ci-rehearsal-" + args.kind), "INVALID_OUTPUT_PATH")
    metadata = context(root, args.kind, os.environ)
    stage(root, args.output, args.kind, metadata)
    print("CI_REHEARSAL_OUTPUT_STAGED:" + args.kind)


if __name__ == "__main__":
    main()
