#!/usr/bin/env python3
"""Disposable SQLite persistence for the synthetic P3 contract only.

Not a production approval database, authentication mechanism or executor.
"""
import json
import os
import sqlite3
import stat
import tempfile
from pathlib import Path

from release_approval_contract import (OfflineApprovals, MODE, ACTIVE, MAX_TTL,
                                       MAX_CLOCK, positive, require)
from release_evidence import exact, sha, digest, schema, REPO

APP_ID = 0x50525033
MAX_RECORDS = 128
MAX_STATE_BYTES = 2 * 1024 * 1024
TERMINAL = {"REJECTED", "EXPIRED", "SIMULATED_CONSUMED"}
FLAGS = ("production_authorized", "deployment_authorized", "release_eligible", "live_verified")


def scratch_path(directory):
    root = Path(tempfile.gettempdir()).resolve()
    directory = Path(directory)
    require(not directory.is_symlink(), "NOT_PRIVATE_REHEARSAL_DIRECTORY")
    directory = directory.resolve(strict=True)
    require(directory.parent == root and directory.name.startswith("prp-p3-rehearsal-")
            and directory.is_dir(), "NOT_PRIVATE_REHEARSAL_DIRECTORY")
    info = directory.stat()
    require(stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_uid == os.getuid(),
            "NOT_PRIVATE_REHEARSAL_DIRECTORY")
    path = directory / "prp-p3-rehearsal.sqlite3"
    require(not path.is_symlink() and (not path.exists() or
            (path.is_file() and path.stat().st_nlink == 1)), "INVALID_REHEARSAL_FILE")
    return path


def decode(raw):
    def unique(pairs):
        obj = {}
        for k,v in pairs:
            require(k not in obj, "DUPLICATE_LEDGER_KEY")
            obj[k] = v
        return obj
    return json.loads(raw, object_pairs_hook=unique)


def load_state(raw):
    state = decode(raw)
    exact(state, {"schema_version", "mode", "last_time", "records"}, "ledger")
    require(type(state["schema_version"]) is int and state["schema_version"] == 1
            and state["mode"] == MODE and type(state["last_time"]) is int
            and 0 <= state["last_time"] <= MAX_CLOCK and type(state["records"]) is dict
            and len(state["records"]) <= MAX_RECORDS, "INVALID_LEDGER")
    ledger = OfflineApprovals()
    ledger._last_time = state["last_time"]
    for aid, record in state["records"].items():
        require(type(record) is dict and record.get("approval_id") == aid and
                record.get("mode") == MODE and record.get("action") == "promote" and
                record.get("schema_version") == 1 and
                record.get("state") in ACTIVE | TERMINAL and digest(record.get("binding_digest")) and
                all(record.get(k) is False for k in FLAGS), "INVALID_LEDGER_RECORD")
        candidate = record.get("candidate")
        exact(candidate, {"repository", "commit", "artifact_digest", "schema"}, "stored candidate")
        require(candidate["repository"] == REPO and sha(candidate["commit"])
                and digest(candidate["artifact_digest"]) and schema(candidate["schema"]),
                "INVALID_STORED_CANDIDATE")
        require(positive(record.get("created_at")) and positive(record.get("expires_at"))
                and 0 < record["expires_at"] - record["created_at"] <= MAX_TTL
                and record["created_at"] <= ledger._last_time, "INVALID_STORED_TIME")
        audit = record.get("audit")
        require(type(audit) is list and 1 <= len(audit) <= 3 and
                all(type(e) is dict and e.get("sequence") == i and
                    e.get("binding_digest") == record["binding_digest"] and
                    positive(e.get("at")) and e["at"] <= ledger._last_time
                    for i,e in enumerate(audit,1)), "INVALID_STORED_AUDIT")
        require(audit[0].get("event") == "REQUESTED" and
                audit[-1].get("event") == record["state"], "INVALID_STORED_TRANSITION")
        key = (candidate["commit"], candidate["artifact_digest"], "promote")
        require(key not in ledger._candidate_keys, "DUPLICATE_STORED_CANDIDATE")
        ledger._candidate_keys.add(key)
        ledger._records[aid] = record
    return ledger


def encode(ledger):
    require(len(ledger._records) <= MAX_RECORDS, "REHEARSAL_LEDGER_FULL")
    raw = json.dumps({"schema_version": 1, "mode": MODE, "last_time": ledger._last_time,
                      "records": ledger._records}, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False)
    require(len(raw.encode("ascii")) <= MAX_STATE_BYTES, "REHEARSAL_LEDGER_SIZE_LIMIT")
    return raw


class PersistentOfflineApprovals:
    """Serialize the existing state machine under BEGIN IMMEDIATE.

    The private scratch file is shared only by synthetic rehearsal processes.
    A transaction commits before a result is returned. No execution follows.
    """
    def __init__(self, directory):
        self.path = scratch_path(directory)
        with self._transaction() as conn:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id == 0:
                require(not conn.execute("SELECT name FROM sqlite_master").fetchall()
                        and conn.execute("PRAGMA user_version").fetchone()[0] == 0,
                        "FOREIGN_DATABASE")
                conn.execute("PRAGMA application_id = " + str(APP_ID))
                conn.execute("PRAGMA user_version = 1")
                conn.execute("CREATE TABLE rehearsal_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
                conn.execute("INSERT INTO rehearsal_state VALUES (1, ?)", (encode(OfflineApprovals()),))
            else:
                self._load(conn)

    def _transaction(self):
        # Private, fixed scratch path only. No connection to app/production DB.
        return Transaction(self.path)

    def _load(self, conn):
        require(conn.execute("PRAGMA application_id").fetchone()[0] == APP_ID and
                conn.execute("PRAGMA user_version").fetchone()[0] == 1, "FOREIGN_DATABASE")
        rows = conn.execute("SELECT id, typeof(payload), length(CAST(payload AS BLOB)) FROM rehearsal_state").fetchall()
        require(len(rows) == 1 and rows[0][0] == 1 and rows[0][1] == "text"
                and 0 < rows[0][2] <= MAX_STATE_BYTES, "INVALID_LEDGER_SIZE")
        return load_state(conn.execute("SELECT payload FROM rehearsal_state WHERE id=1").fetchone()[0])

    def _save(self, conn, ledger):
        require(conn.execute("UPDATE rehearsal_state SET payload=? WHERE id=1",
                             (encode(ledger),)).rowcount == 1, "LEDGER_WRITE_FAILED")

    def _apply(self, method, *args):
        error = None
        result = None
        with self._transaction() as conn:
            ledger = self._load(conn)
            before = {k:v["state"] for k,v in ledger._records.items()}
            try:
                result = method(ledger, *args)
            except ValueError as exc:
                # A denied operation may discover genuine synthetic expiry.
                # Persist only that transition, never a rejected clock advance.
                expired = any(before.get(k) in ACTIVE and v["state"] == "EXPIRED"
                              for k,v in ledger._records.items())
                if not expired:
                    raise
                error = exc
            self._save(conn, ledger)
        if error is not None:
            raise error
        return result

    def request(self, snapshot, actor, now, ttl=MAX_TTL):
        return self._apply(OfflineApprovals.request, snapshot, actor, now, ttl)

    def approve(self, approval_id, reviewed_digest, snapshot, actor, now):
        return self._apply(OfflineApprovals.approve, approval_id, reviewed_digest, snapshot, actor, now)

    def reject(self, approval_id, reviewed_digest, actor, now):
        return self._apply(OfflineApprovals.reject, approval_id, reviewed_digest, actor, now)

    def consume(self, approval_id, reviewed_digest, snapshot, environment, actor, now):
        return self._apply(OfflineApprovals.consume, approval_id, reviewed_digest, snapshot, environment, actor, now)

    def inspect(self, approval_id, reviewed_digest, now):
        return self._apply(OfflineApprovals.inspect, approval_id, reviewed_digest, now)


class Transaction:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        require(scratch_path(self.path.parent) == self.path, "INVALID_REHEARSAL_FILE")
        self.conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            self.conn.execute("PRAGMA trusted_schema=OFF")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.execute("BEGIN IMMEDIATE")
            return self.conn
        except BaseException:
            self.conn.close()
            raise

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.conn.execute("COMMIT")
            else:
                self.conn.execute("ROLLBACK")
        finally:
            self.conn.close()
