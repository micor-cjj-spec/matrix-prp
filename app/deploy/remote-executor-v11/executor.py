"""P2 offline job spool and durable lifecycle.

No SSH listener, credentials, or deployment entrypoint. The sandbox launcher
is default disabled and requires a separately verified dedicated host service.
A future trusted transport must authenticate owner and bind approval before
calling this internal API.
"""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import signal
import subprocess
import tempfile
import stat
import time

from protocol import InvalidJob, canonical, parse, require, validate_job, relative_path, validate_request

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "REJECTED", "RECONCILE_REQUIRED"})
MAX_RESULT = 16 * 1024
CHUNK = 1024 * 1024

def _private_dir(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "unsafe spool directory")

def _private_file(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
            "unsafe spool file")

def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

class Ledger:
    """Single trusted service identity; never expose this API directly to users."""
    def __init__(self, root):
        self.root = Path(root)
        _private_dir(self.root)
        self.spool = self.root / "jobs"
        self.spool.mkdir(mode=0o700, exist_ok=True)
        _private_dir(self.spool)
        self.db = self.root / "ledger.sqlite"
        fd = os.open(self.db, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        os.close(fd)
        _private_file(self.db)
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL,
                manifest TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL, expires INTEGER NOT NULL,
                updated INTEGER NOT NULL, result TEXT)""")
            con.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL,
                comment_id INTEGER UNIQUE NOT NULL, job_id TEXT NOT NULL,
                digest TEXT NOT NULL, action TEXT NOT NULL,
                received INTEGER NOT NULL)""")

    def claim_request(self, req, comment_id, now=None):
        """Durable request replay barrier, separate from the job execution claim.

        The caller MUST first authenticate the trusted event. Neither the
        request nonce nor the comment number proves authentication.
        """
        now = int(time.time() if now is None else now)
        validate_request(req, now)
        require(type(comment_id) is int and 0 < comment_id <= 2**63-1,
                "invalid comment identity")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Queries must resolve an existing job with the exact digest.
            if req["action"] != "submit":
                self._get(con, req["jobId"], req["manifestSha256"])
            try:
                con.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
                            (req["requestId"], req["nonce"], comment_id,
                             req["jobId"], req["manifestSha256"], req["action"], now))
            except sqlite3.IntegrityError as exc:
                raise InvalidJob("duplicate request, nonce or comment") from exc

    def snapshot(self, job_id, digest, *, include_result=False):
        """Read state and result together, never mutate execution state."""
        with self._connect() as con:
            row = self._get(con, job_id, digest)
            result = None
            if include_result and row["state"] in TERMINAL and row["result"]:
                result = parse(row["result"].encode("ascii"))
            return {"state": row["state"], "result": result}


    @contextmanager
    def _connect(self):
        _private_dir(self.root)
        _private_file(self.db)
        con = sqlite3.connect(self.db, timeout=10)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("PRAGMA synchronous=FULL")
            with con:
                yield con
        finally:
            con.close()

    def accept(self, job, now=None):
        now = int(time.time() if now is None else now)
        validate_job(job, now)
        job_id = job["jobId"]
        with self._connect() as con:
            try:
                con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,NULL)",
                            (job_id, job["nonce"], canonical(job["manifest"]).decode("ascii"),
                             job["manifestSha256"], "RECEIVED", job["expiresAt"], now))
            except sqlite3.IntegrityError as exc:
                raise InvalidJob("duplicate job or nonce") from exc
        return job_id

    def _get(self, con, job_id, digest):
        require(type(job_id) is str and type(digest) is str, "bad lookup")
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        require(row is not None and hmac.compare_digest(row["digest"], digest),
                "unknown or mismatched job")
        return row

    def status(self, job_id, digest):
        # Digest binds the lookup; it is not authentication or a bearer secret.
        # Only an independently authenticated/authorized transport may call this.
        with self._connect() as con:
            row = self._get(con, job_id, digest)
            return {k: row[k] for k in ("id", "digest", "state", "expires", "updated")}

    def result(self, job_id, digest):
        with self._connect() as con:
            row = self._get(con, job_id, digest)
            require(row["state"] in TERMINAL, "job not terminal")
            return parse(row["result"].encode("ascii")) if row["result"] else None

    def _directory(self, job_id):
        _private_dir(self.spool)
        path = self.spool / job_id
        path.mkdir(mode=0o700, exist_ok=True)
        _private_dir(path)
        return path

    def receive_file(self, job_id, digest, path, chunks, now=None):
        """Verified bounded streaming; no partial file is ever executable.

        Serialize transfer and state transition using existing SQLite write lock.
        The future transport must set a deadline on its chunk iterator.
        """
        now = int(time.time() if now is None else now)
        relative_path(path)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] in ("RECEIVED", "TRANSFERRING") and row["expires"] > now,
                    "transfer not allowed")
            manifest = parse(row["manifest"].encode("ascii"))
            item = next((f for f in manifest["files"] if f["path"] == path), None)
            require(item is not None, "unexpected file")
            folder = self._directory(job_id)
            dest = folder
            for part in path.split("/")[:-1]:
                dest = dest / part
                dest.mkdir(mode=0o700, exist_ok=True)
                _private_dir(dest)
            dest = dest / path.split("/")[-1]
            if dest.exists() or dest.is_symlink():
                _private_file(dest)
                self._verify_file(dest, item)
                raise InvalidJob("file already verified")
            # Temporary file uses an otherwise forbidden dot-prefixed name.
            temp = dest.parent / ("." + dest.name + ".partial")
            if temp.exists() or temp.is_symlink():
                _private_file(temp)
                temp.unlink()
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            count = 0
            hasher = hashlib.sha256()
            try:
                with os.fdopen(fd, "wb") as output:
                    for block in chunks:
                        require(type(block) is bytes and 0 < len(block) <= CHUNK, "invalid chunk")
                        count += len(block)
                        require(count <= item["size"], "file oversized")
                        hasher.update(block)
                        output.write(block)
                    require(count == item["size"] and hmac.compare_digest(hasher.hexdigest(), item["sha256"]),
                            "file mismatch")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, dest)
                _sync_dir(dest.parent)
            finally:
                if temp.exists():
                    temp.unlink()
            con.execute("UPDATE jobs SET state='TRANSFERRING',updated=? WHERE id=?", (now, job_id))

    @staticmethod
    def _verify_file(path, item):
        _private_file(path)
        hasher = hashlib.sha256()
        count = 0
        with path.open("rb") as f:
            while True:
                block = f.read(CHUNK)
                if not block:
                    break
                count += len(block)
                require(count <= item["size"], "file oversized")
                hasher.update(block)
        require(count == item["size"] and hmac.compare_digest(hasher.hexdigest(), item["sha256"]),
                "file mismatch")

    def verify(self, job_id, digest, now=None):
        now = int(time.time() if now is None else now)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] in ("RECEIVED", "TRANSFERRING") and row["expires"] > now,
                    "verification not allowed")
            self._verify_manifest_files(job_id, parse(row["manifest"].encode("ascii")))
            con.execute("UPDATE jobs SET state='VERIFIED',updated=? WHERE id=?", (now, job_id))

    def _verify_manifest_files(self, job_id, manifest):
        folder = self._directory(job_id)
        for item in manifest["files"]:
            dest = folder
            try:
                for part in item["path"].split("/")[:-1]:
                    dest = dest / part
                    _private_dir(dest)
                self._verify_file(dest / item["path"].split("/")[-1], item)
            except OSError as exc:
                raise InvalidJob("missing or inaccessible file") from exc

    def claim(self, job_id, digest, now=None, *, allowed_operations=None):
        """Durably claim once before side effects. No implicit retry.

        This does not authorize or implement execution. A future isolated worker
        must reverify immutable inputs and obtain the staging operation lock.
        """
        now = int(time.time() if now is None else now)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] == "VERIFIED" and row["expires"] > now, "claim not allowed")
            require(con.execute("SELECT 1 FROM jobs WHERE state IN ('RUNNING','RECONCILE_REQUIRED') LIMIT 1").fetchone() is None,
                    "another job active or uncertain")
            manifest = parse(row["manifest"].encode("ascii"))
            if allowed_operations is not None:
                require(manifest["operation"] in allowed_operations, "operation not supported by worker")
            self._verify_manifest_files(job_id, manifest)
            con.execute("UPDATE jobs SET state='RUNNING',updated=? WHERE id=?", (now, job_id))
            return manifest

    def finish(self, job_id, digest, state, result, now=None):
        require(state in ("SUCCEEDED", "FAILED", "TIMED_OUT"), "invalid completion state")
        require(type(result) is dict and set(result) == {"exitCode", "summary"}, "invalid result")
        require(type(result["exitCode"]) is int and -255 <= result["exitCode"] <= 255
                and type(result["summary"]) is str, "invalid result fields")
        require((state == "SUCCEEDED") == (result["exitCode"] == 0), "exit status mismatch")
        raw = canonical(result)
        require(len(raw) <= MAX_RESULT, "result too large")
        now = int(time.time() if now is None else now)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] == "RUNNING", "completion not allowed")
            con.execute("UPDATE jobs SET state=?,result=?,updated=? WHERE id=?",
                        (state, raw.decode("ascii"), now, job_id))

    def cancel_pending(self, job_id, digest, now=None):
        now = int(time.time() if now is None else now)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] in ("RECEIVED", "TRANSFERRING", "VERIFIED"), "cannot cancel active or terminal job")
            con.execute("UPDATE jobs SET state='CANCELLED',updated=? WHERE id=?", (now, job_id))

    def mark_uncertain(self, job_id, digest, now=None):
        """Explicit recovery only; never infer that a disconnected worker stopped."""
        now = int(time.time() if now is None else now)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._get(con, job_id, digest)
            require(row["state"] == "RUNNING", "not running")
            con.execute("UPDATE jobs SET state='RECONCILE_REQUIRED',updated=? WHERE id=?", (now, job_id))


# Fixed non-production service identity and dedicated immutable runtime.
# Installation and enable marker are NOT created by this module.
SANDBOX_ROOT = Path("/opt/matrix-prp-remote-executor-v11/rootfs")
SANDBOX_GATE = Path("/etc/matrix-prp-remote-executor-v11/sandbox.enabled")
SANDBOX_CGROUP = "/system.slice/prp-remote-executor-v11.service"
BWRAP = Path("/usr/bin/bwrap")
PRLIMIT = Path("/usr/bin/prlimit")
SANDBOX_OPS = frozenset({"sandbox.bash", "sandbox.python"})
SANDBOX_OUTPUT = 1000

def _trusted_path(path, is_directory):
    """Reject symlinks and paths modifiable by the unprivileged worker."""
    for i, component in enumerate((path, *path.parents)):
        info = component.lstat()
        kind = stat.S_ISDIR if i or is_directory else stat.S_ISREG
        require(kind(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, "untrusted runtime path")
    return path

def sandbox_preflight():
    """Local necessary checks, not a substitute for actual isolation acceptance."""
    try:
        require(os.geteuid() != 0 and os.getegid() != 0, "root execution forbidden")
        _trusted_path(SANDBOX_GATE, False)
        require(stat.S_IMODE(SANDBOX_GATE.stat().st_mode) == 0o444
                and SANDBOX_GATE.stat().st_size == len(b"PRP_STAGING_SANDBOX_V11\n")
                and SANDBOX_GATE.read_bytes() == b"PRP_STAGING_SANDBOX_V11\n",
                "sandbox disabled")
        for binary in (BWRAP, PRLIMIT):
            _trusted_path(binary, False)
            require(not binary.stat().st_mode & (stat.S_ISUID | stat.S_ISGID)
                    and os.access(binary, os.X_OK), "unsafe launcher")
        _trusted_path(SANDBOX_ROOT, True)
        for name in ("proc", "dev", "tmp", "input"):
            _trusted_path(SANDBOX_ROOT / name, True)
        # A dedicated rootfs must never be a bind of host / or contain host
        # submounts. Installation separately verifies its content provenance.
        require(SANDBOX_ROOT.stat().st_ino != Path("/").stat().st_ino
                or SANDBOX_ROOT.stat().st_dev != Path("/").stat().st_dev,
                "host root forbidden")
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            fields = line.split()
            require(len(fields) >= 6, "invalid mount metadata")
            # Fixed rootfs path contains no escaped whitespace.
            require(not fields[4].startswith(str(SANDBOX_ROOT) + "/"),
                    "nested runtime mount forbidden")
        status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
        require(status.get("NoNewPrivs", "").strip() == "1"
                and int(status.get("CapEff", "1"), 16) == 0
                and int(status.get("CapBnd", "1"), 16) == 0,
                "unsafe service privileges")
        require(Path("/proc/self/cgroup").read_text().strip() == "0::" + SANDBOX_CGROUP,
                "dedicated cgroup required")
        cg = Path("/sys/fs/cgroup") / SANDBOX_CGROUP.lstrip("/")
        memory = int((cg / "memory.max").read_text().strip())
        pids = int((cg / "pids.max").read_text().strip())
        quota, period = map(int, (cg / "cpu.max").read_text().split())
        swap = int((cg / "memory.swap.max").read_text().strip())
        require(0 < memory <= 512 * 1024 * 1024 and 0 < pids <= 64
                and 0 < quota <= period and swap == 0, "unbounded service resources")
    except (OSError, ValueError) as exc:
        raise InvalidJob("sandbox unavailable or disabled") from exc

def sandbox_argv(manifest, folder):
    """Pure fixed argv builder. No shell interpolation or host-path parameters."""
    from protocol import validate_manifest
    validate_manifest(manifest)
    require(manifest["operation"] in SANDBOX_OPS, "unsupported sandbox operation")
    folder = Path(folder)
    require(folder.is_absolute(), "absolute trusted spool required")
    entry = "/input/" + manifest["entrypoint"]
    script = (["/bin/bash", "--noprofile", "--norc", "--", entry]
              if manifest["operation"] == "sandbox.bash"
              else ["/usr/bin/python3", "-I", "-B", entry])
    return [str(PRLIMIT), "--core=0:0", "--fsize=65536:65536",
            "--nofile=64:64", "--", str(BWRAP),
            "--unshare-all", "--unshare-user", "--unshare-net",
            "--disable-userns", "--die-with-parent", "--new-session",
            "--cap-drop", "ALL", "--clearenv",
            "--ro-bind", str(SANDBOX_ROOT), "/", "--proc", "/proc",
            "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(folder), "/input", "--chdir", "/input",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "LANG", "C.UTF-8", "--", *script, *manifest["args"]]

def run_sandbox(ledger, job_id, digest):
    """Internal worker; trusted caller only. No fallback to host shell.

    A timeout is not automatically retried. Unexpected launcher/cleanup/ledger
    errors leave a durable uncertain state for explicit reconciliation.
    """
    sandbox_preflight()
    require(ledger.root.is_absolute(), "absolute trusted spool required")
    manifest = ledger.claim(job_id, digest, allowed_operations=SANDBOX_OPS)
    proc = None
    try:
        folder = ledger._directory(job_id)
        argv = sandbox_argv(manifest, folder)
        with tempfile.TemporaryFile(dir=ledger.root) as out, tempfile.TemporaryFile(dir=ledger.root) as err:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, cwd="/",
                                    env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                                    start_new_session=True, close_fds=True)
            try:
                code = proc.wait(timeout=manifest["timeoutSeconds"])
                state = "SUCCEEDED" if code == 0 else "FAILED"
            except subprocess.TimeoutExpired:
                # Kill outer launcher group; PID namespace and die-with-parent
                # must be verified to reap all descendants during host acceptance.
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
                # Do not certify descendant cleanup from outer process status.
                ledger.mark_uncertain(job_id, digest)
                return ledger.status(job_id, digest)
            out.seek(0)
            err.seek(0)
            stdout = out.read(SANDBOX_OUTPUT + 1)
            stderr = err.read(SANDBOX_OUTPUT + 1)
            # Treat script output as untrusted data. Never print it or send it
            # unencrypted. The result transport must additionally sanitize it.
            summary = canonical({
                "stdout": stdout[:SANDBOX_OUTPUT].decode("utf-8", "replace"),
                "stderr": stderr[:SANDBOX_OUTPUT].decode("utf-8", "replace"),
                "truncated": len(stdout) > SANDBOX_OUTPUT or len(stderr) > SANDBOX_OUTPUT
            }).decode("ascii")
            # Double-escaped output can grow; keep a fixed bounded receipt.
            if len(canonical({"exitCode": code, "summary": summary})) > MAX_RESULT:
                summary = "OUTPUT_OMITTED_LIMIT"
            ledger.finish(job_id, digest, state, {"exitCode": code, "summary": summary})
        return ledger.status(job_id, digest)
    except Exception:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        # If completion already committed or the DB is unavailable, don't
        # rewrite terminal evidence or automatically rerun.
        if ledger.status(job_id, digest)["state"] == "RUNNING":
            ledger.mark_uncertain(job_id, digest)
        raise InvalidJob("sandbox result uncertain") from None


# P4: a first fixed, local read-only operation. No subprocess, network,
# credentials, image import, Docker, filesystem mutation outside the ledger,
# or access to other jobs. The existing #396 hosted API smoke remains separate.
FIXED_LOCAL_OPS = frozenset({"artifact.inspect"})

def inspect_artifact(ledger, job_id, digest, *, enabled=False, now=None):
    """Return a bounded integrity receipt for already verified job inputs.

    This is metadata/hash inspection only, not Docker image validation,
    deployment, provenance acceptance or authorization for later mutation.
    A trusted worker must independently authorize invocation. Default off.
    """
    require(enabled is True, "fixed operations disabled")
    manifest = ledger.claim(job_id, digest, now, allowed_operations=FIXED_LOCAL_OPS)
    try:
        # claim already checked actual bytes before transitioning to RUNNING;
        # check again while preparing the receipt. No archive extraction.
        ledger._verify_manifest_files(job_id, manifest)
        files = [{"path": item["path"], "size": item["size"],
                  "sha256": item["sha256"]} for item in manifest["files"]]
        summary = canonical({"operation": "artifact.inspect",
                             "integrity": "MATCH",
                             "fileCount": len(files),
                             "bytes": sum(item["size"] for item in files),
                             "files": files}).decode("ascii")
        # If the manifest was accepted, the bounded receipt normally fits;
        # fail closed on unusual escaped summary overhead.
        ledger.finish(job_id, digest, "SUCCEEDED",
                      {"exitCode": 0, "summary": summary}, now)
        return ledger.snapshot(job_id, digest, include_result=True)
    except Exception:
        if ledger.status(job_id, digest)["state"] == "RUNNING":
            ledger.mark_uncertain(job_id, digest, now)
        raise InvalidJob("artifact inspection uncertain") from None

def dispatch_verified_job(ledger, job_id, digest, *, enabled=False, now=None):
    """Fixed worker routing, not an ingress or scheduler.

    Only an independently authorized trusted local worker calls this.
    Do not pass a shell string, operation name or filesystem path from
    the caller; route from the exact stored manifest. #396 stage.health
    remains blocked here: its independent hosted workflow owns credentials.
    """
    require(enabled is True, "worker disabled")
    with ledger._connect() as con:
        row = ledger._get(con, job_id, digest)
        require(row["state"] == "VERIFIED", "job not verified")
        operation = parse(row["manifest"].encode("ascii"))["operation"]
    if operation in FIXED_LOCAL_OPS:
        return inspect_artifact(ledger, job_id, digest, enabled=True, now=now)
    if operation in SANDBOX_OPS:
        return run_sandbox(ledger, job_id, digest)
    raise InvalidJob("operation unavailable; use existing authorized staging runner")
