#!/usr/bin/python3 -I
"""ENG-03F: administrator-reviewed, read-only host metadata collector.

Not a network service, not deployed automatically and not a publisher.
Reads only fixed application release/controller/process metadata; NEVER
prints cmdline, secrets, paths selected by callers or data records.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

BASE = Path("/srv/matrix-prp/releases")
CONTROLLER = Path("/usr/local/sbin/prp-release")
PROC = Path("/proc")
SERVICE = "matrix-prp.service"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
MAX_JAR = 256 * 1024 * 1024


def unique_fields(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate release metadata")
        obj[key] = value
    return obj


def safe_digest(path: Path, limit: int) -> str:
    if path.is_symlink():
        raise ValueError("Symlink not permitted")
    with path.open("rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= limit:
            raise ValueError("Unsafe metadata file")
        hasher = hashlib.sha256()
        while data := stream.read(65536):
            hasher.update(data)
        return hasher.hexdigest()


def collect() -> dict:
    if os.geteuid() != 0:
        raise ValueError("Administrator read-only evidence collection only")

    current = BASE / "current"
    if not current.is_symlink():
        raise ValueError("Release pointer absent")
    target = current.resolve(strict=True)
    if target.parent != BASE or not RELEASE_ID.fullmatch(target.name):
        raise ValueError("Unexpected active release pointer")

    metadata_path = target / "release.json"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise ValueError("Invalid release metadata")
    raw = metadata_path.read_bytes()
    if not 0 < len(raw) <= 131072:
        raise ValueError("Release metadata exceeds bound")
    metadata = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(metadata, dict) or set(metadata) != {
        "id", "commit", "schema_version", "backend_source", "web_source", "files"
    }:
        raise ValueError("Unexpected release metadata format")
    if metadata["id"] != target.name or not isinstance(metadata["commit"], str) or not COMMIT.fullmatch(metadata["commit"]):
        raise ValueError("Invalid active release identity")
    if type(metadata["schema_version"]) is not int or not 1 <= metadata["schema_version"] <= 1000:
        raise ValueError("Invalid version")
    files = metadata["files"]
    if not isinstance(files, dict) or not isinstance(files.get("backend.jar"), str) or not SHA.fullmatch(files["backend.jar"]):
        raise ValueError("Missing immutable packaged JAR checksum")

    jar_path = target / "backend.jar"
    jar_digest = safe_digest(jar_path, MAX_JAR)
    if jar_digest != files["backend.jar"]:
        raise ValueError("Active JAR differs from release metadata")

    command = subprocess.run(
        ["/usr/bin/systemctl", "show", SERVICE, "--no-pager",
         "--property=ActiveState", "--property=MainPID"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=ENV, check=False, timeout=6,
    )
    if command.returncode != 0 or len(command.stdout) > 512:
        raise ValueError("Service metadata unavailable")
    pairs = command.stdout.decode("ascii").splitlines()
    state = dict(line.split("=", 1) for line in pairs if line.count("=") == 1)
    pid_raw = state.get("MainPID", "")
    if state.get("ActiveState") != "active" or not re.fullmatch(r"[1-9][0-9]{0,8}", pid_raw):
        raise ValueError("Expected active Java process absent")
    pid = int(pid_raw)
    cmdline_raw = (PROC / str(pid) / "cmdline").read_bytes()
    if not 0 < len(cmdline_raw) <= 8192:
        raise ValueError("Unsafe process arguments")
    args = cmdline_raw.rstrip(b"\x00").split(b"\x00")
    try:
        jar_index = args.index(b"-jar")
    except ValueError as ex:
        raise ValueError("Running process is not a Java -jar invocation") from ex
    if jar_index + 1 >= len(args) or args.count(b"-jar") != 1:
        raise ValueError("Ambiguous runtime JAR")
    jar_arg = os.fsdecode(args[jar_index + 1])
    if not os.path.isabs(jar_arg):
        raise ValueError("Relative runtime JAR is not independently verifiable")
    try:
        resolved_process_jar = Path(jar_arg).resolve(strict=True)
        resolved_release_jar = jar_path.resolve(strict=True)
    except OSError as ex:
        raise ValueError("Running JAR cannot be resolved") from ex
    if resolved_process_jar != resolved_release_jar:
        raise ValueError("Running process points at a different JAR")

    st = CONTROLLER.lstat()
    if st.st_uid != 0 or st.st_gid != 0 or st.st_mode & 0o022 or st.st_nlink != 1:
        raise ValueError("Unexpected controller ownership or permissions")
    controller_digest = safe_digest(CONTROLLER, 8 * 1024 * 1024)
    # Detect pointer drift during observations; this is metadata-only and not
    # a filesystem snapshot, and cannot prove bytes loaded into JVM memory.
    if current.resolve(strict=True) != target or safe_digest(jar_path, MAX_JAR) != jar_digest:
        raise ValueError("Release changed during evidence collection")
    return {
        "schema_version": 1,
        "source": "MANUAL_ROOT_READ_ONLY",
        "observed_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "service_active": True,
        "process_jar_path_verified": True,
        "release": {"id": target.name, "commit": metadata["commit"],
                    "schema_version": metadata["schema_version"],
                    "backend_jar_sha256": jar_digest,
                    "release_metadata_sha256": hashlib.sha256(raw).hexdigest()},
        "controller_sha256": controller_digest,
        "production_authorized": False,
        "independent_attestation_completed": False,
    }


def main() -> int:
    # No user-supplied path/hostname/arguments, and no SSH access added.
    if len(sys.argv) != 1:
        return 2
    try:
        data = collect()
    except Exception:
        # Never echo exception/log/cmdline/SQL/secret text.
        return 1
    print(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
