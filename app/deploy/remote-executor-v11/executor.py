"""P2 offline job spool and durable lifecycle.

No SSH listener, credentials, process launcher, or deployment entrypoint.
A future trusted transport must authenticate owner and bind approval before
calling this internal API. The test runner is injected; it is NOT a sandbox.
"""
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import stat
import time

from protocol import InvalidJob, canonical, parse, require, validate_job, relative_path

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

    def _connect(self):
        _private_dir(self.root)
        _private_file(self.db)
        con = sqlite3.connect(self.db, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=FULL")
        return con

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
            folder = self._directory(job_id)
            manifest = parse(row["manifest"].encode("ascii"))
            for item in manifest["files"]:
                dest = folder
                for part in item["path"].split("/")[:-1]:
                    dest = dest / part
                    _private_dir(dest)
                self._verify_file(dest / item["path"].split("/")[-1], item)
            con.execute("UPDATE jobs SET state='VERIFIED',updated=? WHERE id=?", (now, job_id))

    def claim(self, job_id, digest, now=None):
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
            con.execute("UPDATE jobs SET state='RUNNING',updated=? WHERE id=?", (now, job_id))
            return parse(row["manifest"].encode("ascii"))

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
