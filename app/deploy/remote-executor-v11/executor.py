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
import pwd
import sys
from pathlib import Path
import sqlite3
import signal
import socket
import struct
import uuid
import subprocess
import tempfile
import stat
import time

from protocol import InvalidJob, canonical, parse, require, validate_job, relative_path, validate_request, MAX_ARTIFACT

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "REJECTED", "RECONCILE_REQUIRED"})
MAX_RESULT = 16 * 1024
CHUNK = 1024 * 1024
MAX_RETAINED_JOBS = 32
MAX_RESERVED_BYTES = 1024 * 1024 * 1024
MAX_RETAINED_REQUESTS = 1024

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
        validate_request(req, now)
        require(type(comment_id) is int and 0 < comment_id <= 2**63-1,
                "invalid comment identity")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Refresh live authorization after waiting on a contended lock.
            validate_request(req, now)
            # Queries must resolve an existing job with the exact digest.
            if req["action"] != "submit":
                self._get(con, req["jobId"], req["manifestSha256"])
            require(con.execute("SELECT count(*) FROM requests").fetchone()[0] < MAX_RETAINED_REQUESTS,
                    "request retention capacity exhausted")
            claimed_at = int(time.time() if now is None else now)
            validate_request(req, claimed_at)
            try:
                con.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
                            (req["requestId"], req["nonce"], comment_id,
                             req["jobId"], req["manifestSha256"], req["action"], claimed_at))
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
            con.execute("BEGIN IMMEDIATE")
            retained = con.execute("SELECT manifest FROM jobs").fetchall()
            require(len(retained) < MAX_RETAINED_JOBS, "job retention capacity exhausted")
            reserved = sum(f["size"] for row in retained for f in parse(row["manifest"].encode("ascii"))["files"])
            incoming = sum(f["size"] for f in job["manifest"]["files"])
            require(reserved + incoming <= MAX_RESERVED_BYTES, "spool reservation exhausted")
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
        # Live callers must evaluate time after the write lock, not before
        # waiting for SQLite. Explicit now is a fixed clock for offline tests.
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            checked_at = int(time.time() if now is None else now)
            row = self._get(con, job_id, digest)
            require(row["state"] == "VERIFIED" and row["expires"] > checked_at, "claim not allowed")
            require(con.execute("SELECT 1 FROM jobs WHERE state IN ('RUNNING','RECONCILE_REQUIRED') LIMIT 1").fetchone() is None,
                    "another job active or uncertain")
            manifest = parse(row["manifest"].encode("ascii"))
            if allowed_operations is not None:
                require(manifest["operation"] in allowed_operations, "operation not supported by worker")
            self._verify_manifest_files(job_id, manifest)
            claimed_at = int(time.time() if now is None else now)
            require(row["expires"] > claimed_at, "claim expired during verification")
            con.execute("UPDATE jobs SET state='RUNNING',updated=? WHERE id=?", (claimed_at, job_id))
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


# Candidate host entrypoints. No installation, service creation or gate write.
INSTALL_ROOT = Path("/opt/matrix-prp-remote-executor-v11")
CONFIG_ROOT = Path("/etc/matrix-prp-remote-executor-v11")
LEDGER_ROOT = Path("/var/lib/matrix-prp-remote-executor-v11")
SERVICE_USER = "prp-remote-v11"  # receiver only
WORKER_USER = "prp-remote-worker-v11"
WORK_ROOT = Path("/var/lib/matrix-prp-remote-worker-v11")
HANDOFF_ROOT = Path("/run/prp-remote-v11-handoff")
HANDOFF_SOCKET = HANDOFF_ROOT / "worker.sock"
RECEIVER_GATE = CONFIG_ROOT / "receiver.enabled"
WORKER_GATE = CONFIG_ROOT / "worker.enabled"

def host_gate(path, expected):
    """Fixed root-owned opt-in; no environment override."""
    try:
        _trusted_path(path, False)
        st = path.stat()
        require(stat.S_IMODE(st.st_mode) == 0o444 and st.st_size == len(expected)
                and path.read_bytes() == expected, "host gate disabled")
    except OSError as exc:
        raise InvalidJob("host gate unavailable") from exc

def service_identity(name=SERVICE_USER):
    require(name in (SERVICE_USER, WORKER_USER), "unknown service identity")
    try:
        account = pwd.getpwnam(name)
        require(account.pw_uid > 0 and account.pw_gid > 0
                and os.geteuid() == os.getuid() == account.pw_uid
                and os.getegid() == os.getgid() == account.pw_gid
                and set(os.getgroups()) <= {account.pw_gid},
                "unexpected service identity or groups")
        return account
    except (OSError, KeyError) as exc:
        raise InvalidJob("service identity unavailable") from exc

def next_verified(ledger, now=None):
    """Select one exact, unexpired, submit-bound job from durable state.

    Selection is read-only; dispatch performs the actual atomic job claim.
    No automatic retry of RUNNING or RECONCILE_REQUIRED jobs. Unknown
    operations remain outside this worker's allowlist.
    """
    now = int(time.time() if now is None else now)
    with ledger._connect() as con:
        if con.execute("SELECT 1 FROM jobs WHERE state IN ('RUNNING','RECONCILE_REQUIRED') LIMIT 1").fetchone():
            return None
        rows = con.execute("""SELECT j.id,j.digest,j.manifest FROM jobs j
            WHERE j.state='VERIFIED' AND j.expires>?
              AND EXISTS (SELECT 1 FROM requests r WHERE r.action='submit'
                  AND r.job_id=j.id AND r.digest=j.digest AND r.nonce=j.nonce)
            ORDER BY j.updated,j.id LIMIT ?""", (now, MAX_RETAINED_JOBS)).fetchall()
        for row in rows:
            operation = parse(row["manifest"].encode("ascii"))["operation"]
            if operation in SANDBOX_OPS or operation in FIXED_LOCAL_OPS:
                return row["id"], row["digest"]
    return None

def worker_once(ledger, *, enabled=False, now=None):
    require(enabled is True, "worker disabled")
    selected = next_verified(ledger, now)
    if selected is None:
        return None
    return dispatch_verified_job(ledger, *selected, enabled=True, now=now)

def _handoff_accounts():
    receiver = pwd.getpwnam(SERVICE_USER)
    worker = pwd.getpwnam(WORKER_USER)
    require(receiver.pw_uid > 0 and worker.pw_uid > 0 and receiver.pw_uid != worker.pw_uid
            and receiver.pw_gid > 0 and worker.pw_gid > 0 and receiver.pw_gid != worker.pw_gid,
            "distinct handoff identities required")
    return receiver, worker

def _peer(conn, account):
    _, uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                     struct.calcsize("3i")))
    require((uid, gid) == (account.pw_uid, account.pw_gid), "unexpected local peer")

def _handoff_dir(receiver, worker):
    _trusted_path(HANDOFF_ROOT.parent, True)
    st = HANDOFF_ROOT.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == worker.pw_uid
            and st.st_gid == receiver.pw_gid and stat.S_IMODE(st.st_mode) == 0o2750,
            "unsafe handoff directory")

def _handoff_socket(receiver, worker):
    _handoff_dir(receiver, worker)
    st = HANDOFF_SOCKET.lstat()
    require(stat.S_ISSOCK(st.st_mode) and st.st_uid == worker.pw_uid
            and st.st_gid == receiver.pw_gid and stat.S_IMODE(st.st_mode) == 0o660,
            "unsafe handoff socket")

@contextmanager
def _handoff_stream(conn):
    from bridge import _Pipe
    deadline = time.monotonic() + 240
    with conn.makefile("rb", buffering=0) as incoming, conn.makefile("wb", buffering=0) as outgoing:
        yield _Pipe(incoming, deadline), _Pipe(outgoing, deadline)

def handoff_receiver(conn, ledger, *, now=None):
    """Receiver owns the authoritative claim and ledger, never launches scripts.
    Caller must authenticate the local worker peer first."""
    from bridge import write_control, read_control, encode_file_stream, _write_all
    from protocol import validate_job, exact
    selected = next_verified(ledger, now)
    with _handoff_stream(conn) as (incoming, outgoing):
        if selected is None:
            write_control(outgoing, {"idle": True})
            conn.shutdown(socket.SHUT_WR)
            require(incoming.read(1) == b"", "unexpected idle response")
            return None
        jid, md = selected
        manifest = ledger.claim(jid, md, now, allowed_operations=SANDBOX_OPS | FIXED_LOCAL_OPS)
        try:
            with ledger._connect() as con:
                row = ledger._get(con, jid, md)
                # The original absolute expiry is retained. The derived local
                # issuedAt is a serialization field, not renewed authorization.
                job = {"version":11,"jobId":jid,"nonce":row["nonce"],
                       "issuedAt":row["expires"]-300,"expiresAt":row["expires"],
                       "manifest":manifest,"manifestSha256":md}
            validate_job(job, now)
            token = uuid.uuid4().hex
            binding = {"jobId":jid,"manifestSha256":md,"claim":token}
            write_control(outgoing, {"job":job,"claim":token})
            for item in manifest["files"]:
                path = ledger._directory(jid) / item["path"]
                _private_file(path)
                with path.open("rb") as source:
                    for frame in encode_file_stream(source, jid, md, item):
                        _write_all(outgoing, frame)
            write_control(outgoing, dict(binding, done=True))
            conn.shutdown(socket.SHUT_WR)
            reply = read_control(incoming)
            exact(reply, "jobId manifestSha256 claim state result")
            require(all(reply[k] == v for k,v in binding.items()), "handoff result mismatch")
            require(incoming.read(1) == b"", "trailing handoff response")
            if reply["state"] == "RECONCILE_REQUIRED":
                require(reply["result"] is None, "unexpected uncertain result")
                ledger.mark_uncertain(jid, md, now)
            else:
                require(reply["state"] in ("SUCCEEDED", "FAILED"), "invalid worker result state")
                ledger.finish(jid, md, reply["state"], reply["result"], now)
            return ledger.snapshot(jid, md, include_result=True)
        except Exception:
            if ledger.status(jid, md)["state"] == "RUNNING":
                ledger.mark_uncertain(jid, md, now)
            raise InvalidJob("handoff uncertain") from None

def handoff_worker(conn, work_root, *, now=None):
    """Worker receives only a bound job and verified bytes, not the receiver
    ledger, credentials or arbitrary host paths. Peer authenticated by caller."""
    from bridge import write_control, read_control, file_frame_chunks
    from protocol import exact, validate_job
    _private_dir(work_root)
    with _handoff_stream(conn) as (incoming, outgoing):
        request = read_control(incoming)
        if request == {"idle": True}:
            require(incoming.read(1) == b"", "trailing idle request")
            conn.shutdown(socket.SHUT_WR)
            return None
        exact(request, "job claim")
        token = request["claim"]
        require(type(token) is str and len(token) == 32
                and all(c in "0123456789abcdef" for c in token), "invalid handoff claim")
        job = validate_job(request["job"], now)
        require(job["manifest"]["operation"] in SANDBOX_OPS | FIXED_LOCAL_OPS, "unsupported handoff operation")
        jid, md = job["jobId"], job["manifestSha256"]
        binding = {"jobId":jid,"manifestSha256":md,"claim":token}
        with tempfile.TemporaryDirectory(dir=work_root) as directory:
            local = Ledger(Path(directory))
            local.accept(job, now)
            for item in job["manifest"]["files"]:
                local.receive_file(jid, md, item["path"],
                                   file_frame_chunks(incoming, jid, md, item, require_eof=False), now)
            require(read_control(incoming) == dict(binding, done=True), "handoff completion mismatch")
            require(incoming.read(1) == b"", "trailing handoff input")
            local.verify(jid, md, now)
            dispatch_verified_job(local, jid, md, enabled=True, now=now)
            result = local.snapshot(jid, md, include_result=True)
        # Cleanup precedes reporting success; any uncertain result blocks replay.
        write_control(outgoing, dict(binding, **result))
        conn.shutdown(socket.SHUT_WR)
        return result

def handoff_once(ledger, *, enabled=False):
    require(enabled is True, "local handoff disabled")
    receiver, worker = _handoff_accounts()
    service_identity(SERVICE_USER)
    _handoff_socket(receiver, worker)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(10)
        conn.connect(str(HANDOFF_SOCKET))
        _peer(conn, worker)
        return handoff_receiver(conn, ledger)

def worker_main():
    """Fixed one-shot worker; no receiver ledger or private key access."""
    require(sys.argv[1:] == ["worker-once"], "invalid worker invocation")
    receiver, worker = _handoff_accounts()
    service_identity(WORKER_USER)
    host_gate(WORKER_GATE, b"PRP_STAGING_WORKER_V11\n")
    sandbox_preflight()
    _private_dir(WORK_ROOT)
    _handoff_dir(receiver, worker)
    require(not HANDOFF_SOCKET.exists() and not HANDOFF_SOCKET.is_symlink(),
            "handoff socket already exists")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(HANDOFF_SOCKET))
        try:
            HANDOFF_SOCKET.chmod(0o660)
            _handoff_socket(receiver, worker)
            listener.listen(1)
            listener.settimeout(15)
            conn, _ = listener.accept()
            with conn:
                _peer(conn, receiver)
                handoff_worker(conn, WORK_ROOT)
        finally:
            HANDOFF_SOCKET.unlink()

if __name__ == "__main__":
    try:
        worker_main()
    except Exception:
        # No job content, command, file names or private values in journal.
        print("REMOTE_EXECUTOR_WORKER_BLOCKED_OR_UNCERTAIN", file=sys.stderr)
        sys.exit(2)
