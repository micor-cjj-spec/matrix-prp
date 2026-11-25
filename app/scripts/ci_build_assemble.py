#!/usr/bin/env python3
"""Same-attempt build output assembly, exclusively for disposable PR #412 CI."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ci_build_output import REPO, PR, LIMIT, require, git, positive, copy_payload

JOBS = {"backend": "backend-tests", "web": "web-build"}


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_KEY")
        result[k] = v
    return result


def context(root, env):
    sha = git(root, "rev-parse", "HEAD")
    require(env.get("GITHUB_REPOSITORY") == REPO and env.get("GITHUB_EVENT_NAME") == "pull_request"
            and env.get("GITHUB_REF") == "refs/pull/" + PR + "/merge"
            and env.get("GITHUB_WORKFLOW") == "CI" and env.get("GITHUB_JOB") == "ci-rehearsal-assemble"
            and env.get("GITHUB_SHA") == sha and re.fullmatch(r"[a-f0-9]{40}", sha)
            and positive(env.get("GITHUB_RUN_ID")) and positive(env.get("GITHUB_RUN_ATTEMPT")),
            "NOT_EXACT_REHEARSAL_CONTEXT")
    return {"schema_version": 1, "repository": REPO, "pull_request": int(PR),
            "tested_commit": sha, "run_id": int(env["GITHUB_RUN_ID"]),
            "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]), "scope": "CI_REHEARSAL_ONLY",
            "production_authorized": False}


def allowed(name, kind):
    return (isinstance(name, str) and len(name) <= 512
            and re.fullmatch(r"[A-Za-z0-9._/-]+", name) is not None
            and all(x not in ("", ".", "..") for x in name.split("/"))
            and (name == "backend.jar" if kind == "backend" else name.startswith("web/")))


def inspect(root, folder, kind, expected):
    require(folder.is_dir() and not folder.is_symlink(), "INVALID_ARTIFACT_DIRECTORY")
    p = folder/"ci-output.json"
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= 2*1024*1024, "INVALID_MANIFEST")
    m = json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(type(m) is dict and set(m) == set(expected)|{"kind","job","source_tree","files"},
            "INVALID_MANIFEST_SHAPE")
    require(all(type(m[k]) is type(v) and m[k] == v for k,v in expected.items()),
            "CROSS_RUN_ATTEMPT_OR_CHECKOUT")
    source = git(root, "rev-parse", "HEAD:app/" + kind)
    require(m["kind"] == kind and m["job"] == JOBS[kind] and m["source_tree"] == source,
            "SOURCE_OR_JOB_MISMATCH")
    files = m["files"]
    require(type(files) is dict and 0 < len(files) <= 10000 and
            all(allowed(name,kind) for name in files), "INVALID_PAYLOAD_LIST")
    require(set(files)=={"backend.jar"} if kind=="backend" else "web/index.html" in files,
            "REQUIRED_PAYLOAD_MISSING")
    entries = list(folder.rglob("*"))
    require(len(entries) <= 20000 and all(not p.is_symlink() and (p.is_file() or p.is_dir())
                                        for p in entries), "UNSAFE_ARTIFACT_ENTRY")
    require({p.relative_to(folder).as_posix() for p in entries if p.is_file()} ==
            set(files)|{"ci-output.json"}, "UNDECLARED_OR_MISSING_PAYLOAD")
    total = 0
    for name, entry in files.items():
        require(type(entry) is dict and set(entry)=={"sha256","size"} and
                type(entry["size"]) is int and 0 < entry["size"] <= LIMIT and
                isinstance(entry["sha256"],str) and re.fullmatch(r"[a-f0-9]{64}",entry["sha256"]),
                "INVALID_FILE_BINDING")
        p = folder/name
        require(p.stat().st_size == entry["size"], "FILE_SIZE_MISMATCH")
        total += entry["size"]
        require(total <= LIMIT, "TOTAL_SIZE_LIMIT")
        with p.open("rb") as inp:
            digest = hashlib.file_digest(inp,"sha256").hexdigest()
        require(digest == entry["sha256"], "FILE_HASH_MISMATCH")
    return m


def restore(root, backend, web, expected):
    b = inspect(root,backend,"backend",expected)
    w = inspect(root,web,"web",expected)
    jar = root/"app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar"
    dist = root/"app/web/dist"
    require(not any(p.is_symlink() for p in (root/"app",root/"app/backend",root/"app/web",jar.parent,dist))
            and not jar.parent.exists() and not dist.exists(), "OUTPUT_NOT_FRESH")
    require(not (root/"release.tar.gz").exists() and not (root/"release.tar.gz").is_symlink(),
            "RELEASE_OUTPUT_NOT_FRESH")
    require(sum(e["size"] for m in (b,w) for e in m["files"].values()) <= LIMIT, "COMBINED_SIZE_LIMIT")
    try:
        for folder,m in ((backend,b),(web,w)):
            for name,entry in m["files"].items():
                target = jar if name=="backend.jar" else dist/name.removeprefix("web/")
                require(copy_payload(folder/name,target,LIMIT)==entry, "COPY_HASH_MISMATCH")
    except Exception:
        for path in (jar.parent,dist):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
        raise
    return b,w


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    temp=Path(os.environ["RUNNER_TEMP"]).resolve()
    require(args.output == temp/"prp-ci-rehearsal-assembled" and
            not args.output.exists() and not args.output.is_symlink(), "INVALID_OUTPUT")
    expected=context(root,os.environ)
    b,w=restore(root,temp/"prp-ci-input-backend",temp/"prp-ci-input-web",expected)
    release_id="ci-rehearsal-r"+str(expected["run_id"])+"-"+str(expected["run_attempt"])
    subprocess.run(["python3","app/deploy/package-release.py",release_id],cwd=root,check=True)
    tar=root/"release.tar.gz"
    require(tar.is_file() and not tar.is_symlink(),"MISSING_ASSEMBLED_ARCHIVE")
    args.output.mkdir()
    checksum=copy_payload(tar,args.output/"ci-rehearsal-release.tar.gz",LIMIT)
    summary=dict(expected,state="CI_REHEARSAL_ASSEMBLED",release_id=release_id,
                 backend_source_tree=b["source_tree"],web_source_tree=w["source_tree"],
                 archive=checksum,release_eligible=False,live_verified=False)
    (args.output/"assembly-review.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",
                                                    encoding="utf-8")
    print("CI_REHEARSAL_ASSEMBLED; NOT PRODUCTION ELIGIBLE")


if __name__=="__main__":
    main()
