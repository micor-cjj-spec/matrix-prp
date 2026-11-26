"""S6.2B offline-only S5 orchestration; no real transport, CLI or activation."""
import ast
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from decimal import Decimal
from pathlib import Path

from unified_staging_s5_local_preflight import (
    IMAGES, LOCK, PATHS, TARGET, credentials, lock_identity, login, observe,
    private_fd, private_parent, require_disjoint, same_user, success, verify_stage,
)
from unified_staging_s5_recovery import (
    S5_SOURCE_SHA256, build_offline_receipt, capture_baseline, compare_baseline,
    persist_baseline_once, read_baseline,
)

SOURCE = Path(__file__).with_name("fixtures") / "unified_396_s5_operator.py.txt"
FUNCTIONS = frozenset(("require", "success", "items", "marker", "matches", "lookup",
                       "check_values", "create", "deny", "amount_summary", "check_summary",
                       "verify_absent", "exercise", "cleanup"))
MODULES = ("task", "finance", "record", "video", "practice")
JOURNAL = "local-private-journal.json"
LIMIT = 65536


class OfflineSimulation:
    """Explicit test seam. No implementation or live p420 adapter is supplied."""

    def simulate(self, path, *, method, payload, token):
        raise NotImplementedError


def check(ok, label):
    if not ok:
        raise RuntimeError(label)


def load_functions(g):
    # Only these exact, digest-pinned definitions; no historical imports,
    # helper loader, top-level runner, stale image constants or exit().
    raw = SOURCE.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == S5_SOURCE_SHA256, "S5_SOURCE_CHANGED")
    nodes = [n for n in ast.parse(raw).body
             if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    check(len(nodes) == len(FUNCTIONS) and {n.name for n in nodes} == FUNCTIONS,
          "S5_FUNCTIONS_CHANGED")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), g)
    return g


class Journal:
    """Private, durable journal snapshots; no resume or historical overwrite."""

    def __init__(self, directory, fd):
        self.directory, self.fd = directory, fd
        self.current = None
        self.failed = False

    def verify_dir(self):
        private_parent(self.directory / JOURNAL)
        a, b = os.fstat(self.fd), self.directory.lstat()
        check((a.st_dev, a.st_ino) == (b.st_dev, b.st_ino), "EVIDENCE_DIR_CHANGED")

    def read(self):
        self.verify_dir()
        f = os.open(JOURNAL, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        with os.fdopen(f, "rb") as inp:
            s = os.fstat(inp.fileno())
            check(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                  and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1
                  and s.st_size <= LIMIT, "INVALID_JOURNAL_FILE")
            raw = inp.read(LIMIT + 1)
        check(len(raw) <= LIMIT, "JOURNAL_TOO_LARGE")
        return raw

    def verify(self, payload):
        check(not self.failed and self.current is not None
              and self.read() == self.current == self.encode(payload),
              "JOURNAL_READBACK_MISMATCH")

    @staticmethod
    def encode(payload):
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode() + b"\n"

    def save(self, payload):
        tmp = None
        owns_tmp = False
        try:
            check(not self.failed, "JOURNAL_FAILED")
            self.verify_dir()
            if self.current is not None:
                check(self.read() == self.current, "JOURNAL_CHANGED")
            raw = self.encode(payload)
            check(len(raw) <= LIMIT, "JOURNAL_TOO_LARGE")
            tmp = ".journal-" + secrets.token_hex(16)
            f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=self.fd)
            owns_tmp = True
            with os.fdopen(f, "wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            if self.current is None:
                os.link(tmp, JOURNAL, src_dir_fd=self.fd, dst_dir_fd=self.fd,
                        follow_symlinks=False)
                os.unlink(tmp, dir_fd=self.fd)
            else:
                check(self.read() == self.current, "JOURNAL_CHANGED")
                os.replace(tmp, JOURNAL, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            tmp = None
            os.fsync(self.fd)
            self.current = raw
            self.verify(payload)
        except Exception:
            self.failed = True
            raise RuntimeError("JOURNAL_PERSIST_FAILED") from None
        finally:
            if tmp is not None and owns_tmp:
                try:
                    os.unlink(tmp, dir_fd=self.fd)
                except FileNotFoundError:
                    pass


def blocked_receipt():
    return {"kind": "S5_OFFLINE_REHEARSAL", "state": "OFFLINE_REVIEW_REQUIRED",
            "modulesPassed": 0, "cleanupObservedAbsent": 0,
            "baselineState": "NOT_VERIFIED", "recoveryState": "NOT_VERIFIED",
            "liveVerified": False, "baselineRestored": False, "cleanupAuthorized": False,
            "automatedRunnerEnabled": False, "productionAuthorized": False,
            "deploymentAuthorized": False, "businessWrites": 0}


def rehearse(sim, directory, b_file):
    """Run only an injected synthetic simulation under the original lock.

    The module does not load p420 or expose a live-write flag. Future real
    execution requires a separately reviewed adapter and operator approval.
    """
    check(isinstance(sim, OfflineSimulation), "OFFLINE_SIMULATION_REQUIRED")
    lock_fd = evidence_fd = None
    try:
        lock_path = sim.CREDENTIAL_DIR / LOCK
        lock_fd = private_fd(lock_path)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_identity(lock_fd, lock_path)
        directory = Path(directory)
        private_parent(directory / JOURNAL)
        evidence_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        journal = Journal(directory, evidence_fd)
        journal.verify_dir()
        check(not os.listdir(evidence_fd), "NEW_EMPTY_EVIDENCE_DIR_REQUIRED")
        return _rehearse_locked(sim, directory, b_file, lock_fd, lock_path, journal)
    except Exception:
        return blocked_receipt()
    finally:
        if evidence_fd is not None:
            os.close(evidence_fd)
        if lock_fd is not None:
            os.close(lock_fd)


def _rehearse_locked(sim, directory, b_file, lock_fd, lock_path, journal):
    g = load_functions({"Decimal": Decimal, "m": sim})
    first = verify_stage(sim)
    accounts = credentials(sim, b_file)
    tokens = {w: login(sim, c) for w, c in accounts.items()}
    check(tokens["A"] != tokens["B"], "DUPLICATE_TOKEN")
    date = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)).date().isoformat()
    month = date[:7]
    run = "UAT396-" + secrets.token_hex(8)
    context = {"run": run, "month": month, "target": TARGET, "schema": 31,
               "images": dict(IMAGES), "owners": {w: c["user_id"] for w, c in accounts.items()},
               "sourceSha256": S5_SOURCE_SHA256}
    runtime_digest = hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest()
    snapshots, summaries = observe(sim, tokens, month)
    baseline = capture_baseline(context, snapshots, summaries)
    require_disjoint(snapshots)
    g.update(PATHS=dict(PATHS), DATE=date, RUN=run,
             SUMMARY="/api/finance/summary/monthly?month=" + month,
             BASE={(w, k): {r["id"]: copy.deepcopy(r) for r in snapshots[w + "_" + k]}
                   for w in accounts for k in PATHS},
             FIN_BASE={w: tuple(Decimal(str(summaries[w][k])) for k in ("income", "expense", "balance"))
                       for w in accounts},
             ATTEMPTED={}, RESULT={}, CLEANUP={}, PHASE="PREFLIGHT")
    check(not any(g["matches"](row, who, kind)
                  for (_, kind), rows in g["BASE"].items()
                  for row in rows.values() for who in accounts), "BASELINE_MARKER_COLLISION")
    journal.verify_dir()
    persist_baseline_once(directory, baseline)
    check(read_baseline(directory) == baseline, "BASELINE_READBACK_MISMATCH")
    current, current_summaries = observe(sim, tokens, month)
    check(compare_baseline(baseline, context, current, current_summaries)["state"]
          == "BASELINE_DIGESTS_MATCH", "BASELINE_DRIFT")
    halted = False

    def payload():
        return {"run": run, "phase": g["PHASE"], "attempted": list(g["ATTEMPTED"].values()),
                "results": g["RESULT"], "cleanup": g["CLEANUP"],
                "runtimeDigest": runtime_digest, "baselineDigest": baseline["contentDigest"],
                "contextDigest": baseline["contextDigest"]}

    def save():
        journal.save(payload())

    def recheck():
        lock_identity(lock_fd, lock_path)
        journal.verify_dir()
        check(verify_stage(sim) == first, "RUNTIME_CHANGED")
        for who, c in accounts.items():
            sim.query_ordinary_identity_readonly(c)
            check(same_user(success(sim, "/api/users/me", tokens[who]), c), "IDENTITY_CHANGED")
        lock_identity(lock_fd, lock_path)

    def durable():
        nonlocal halted
        try:
            check(not halted and not journal.failed, "MUTATIONS_HALTED")
            recheck()
            check(read_baseline(directory) == baseline, "BASELINE_CHANGED")
            journal.verify(payload())
        except Exception:
            halted = True
            raise RuntimeError("DURABILITY_OR_RUNTIME_BLOCKED") from None

    def rows_for(kind):
        return {w: g["items"](w, kind) for w in accounts}

    def old_id(kind, rid):
        return any(rid in g["BASE"][w, kind] for w in accounts)

    def exact_owner(kind, rid):
        rows = rows_for(kind)
        check(not old_id(kind, rid), "BASELINE_ID_PROTECTED")
        candidates = []
        for w in accounts:
            rec = g["ATTEMPTED"].get((w, kind))
            if rec is None or rec["id"] not in (None, rid):
                continue
            other = "B" if w == "A" else "A"
            own = [i for i, row in rows[w].items() if g["matches"](row, w, kind)]
            foreign = [i for i, row in rows[other].items() if g["matches"](row, w, kind)]
            if own == [rid] and not foreign and rid not in rows[other]:
                candidates.append((w, rec))
        check(len(candidates) == 1, "SYNTHETIC_OWNER_UNPROVEN")
        return candidates[0]

    def raw(path, method="GET", payload=None, who=None):
        check(who in accounts, "ACTOR_BLOCKED")
        if method == "GET":
            check(payload is None and (path in PATHS.values() or path == g["SUMMARY"]
                  or re.fullmatch(r"/api/video/items\?folderId=[1-9][0-9]*", path)
                  or re.fullmatch(r"/api/practice/subjects/[1-9][0-9]*/banks", path)),
                  "GET_ROUTE_BLOCKED")
            return sim.simulate(path, method=method, payload=payload, token=tokens[who])
        check(method in ("POST", "PUT", "DELETE"), "METHOD_BLOCKED")
        durable()
        kind = next((k for k, p in PATHS.items() if path == p or
                     re.fullmatch(re.escape(p) + r"/[1-9][0-9]*", path)), None)
        check(kind is not None, "MUTATION_ROUTE_BLOCKED")
        phase = g["PHASE"]
        if method == "POST":
            check(path == PATHS[kind] and (phase == kind or
                  (phase == "finance" and kind in ("account", "category"))),
                  "CREATE_PHASE_BLOCKED")
            rec = g["ATTEMPTED"].get((who, kind))
            check(rec == {"owner": who, "kind": kind, "marker": g["marker"](who), "id": None}
                  and isinstance(payload, dict) and g["matches"](payload, who, kind),
                  "CREATE_ATTEMPT_UNPROVEN")
            check(not any(g["matches"](row, who, kind)
                          for rows in rows_for(kind).values() for row in rows.values()),
                  "CREATE_MARKER_COLLISION")
        else:
            check(path != PATHS[kind], "MUTATION_ID_REQUIRED")
            rid = int(path.rsplit("/", 1)[1])
            owner, rec = exact_owner(kind, rid)
            if phase == "CLEANUP":
                check(method == "DELETE" and who == owner and payload is None, "CLEANUP_BLOCKED")
                if kind in ("account", "category"):
                    # Do not delete a setup object while a transaction attempt
                    # is unresolved, or any visible transaction references it.
                    check((owner, "finance") not in g["ATTEMPTED"] or
                          g["CLEANUP"].get(owner + "_finance") == "API_ABSENT",
                          "FINANCE_CLEANUP_NOT_VERIFIED")
                    tag = g["marker"](owner)
                    check(not any(g["matches"](row, owner, "finance") or
                                  row.get(kind) in (tag, tag + "-v2")
                                  for rows in rows_for("finance").values() for row in rows.values()),
                          "FINANCE_DEPENDENCY_REMAINS")
            else:
                check(phase == kind and rec["id"] == rid, "TEST_ID_UNCONFIRMED")
                check((method == "PUT" and isinstance(payload, dict)
                       and g["matches"](payload, owner, kind))
                      or (method == "DELETE" and who != owner and payload is None),
                      "TEST_MUTATION_BLOCKED")
        durable()
        result = sim.simulate(path, method=method, payload=payload, token=tokens[who])
        if method == "POST" and result[0] == 200 and isinstance(result[2], dict):
            data = result[2].get("data")
            if isinstance(data, dict) and type(data.get("id")) is int:
                check(not old_id(kind, data["id"]), "CREATE_RETURNED_BASELINE_ID")
        return result

    g.update(raw=raw, save_local=save)
    failure = None
    final_rows, final_summaries, final_journal, final_baseline = {}, {}, None, None
    baseline_ok = False
    try:
        g["PHASE"] = "TEST"
        save()
        durable()
        for kind in MODULES:
            g["PHASE"] = kind
            save()
            g["exercise"](kind)
            save()
    except Exception:
        failure = "OFFLINE_EXERCISE_BLOCKED"
    finally:
        # No automatic resume; only exact same-run attempts may be cleaned.
        # A failed journal or changed runtime blocks further mutations.
        try:
            if g["ATTEMPTED"] and not halted and not journal.failed:
                g["PHASE"] = "CLEANUP"
                save()
                durable()
                g["cleanup"]()
            g["PHASE"] = "FINISHED"
            save()
            recheck()
            check(not halted and not journal.failed, "MUTATIONS_HALTED")
            final_rows, final_summaries = observe(sim, tokens, month)
            require_disjoint(final_rows)
            final_baseline = read_baseline(directory)
            check(final_baseline == baseline, "BASELINE_CHANGED")
            journal.verify(payload())
            final_journal = json.loads(journal.read())
            recheck()
            baseline_ok = compare_baseline(final_baseline, context, final_rows,
                                           final_summaries)["state"] == "BASELINE_DIGESTS_MATCH"
        except Exception:
            failure = "OFFLINE_FINAL_REVIEW_REQUIRED"
    passed = (failure is None and len(g["RESULT"]) == 5 and baseline_ok
              and len(g["CLEANUP"]) == 14 and all(x == "API_ABSENT" for x in g["CLEANUP"].values()))
    report = {"state": "CROSS_MODULE_UAT_PASS" if passed else "CROSS_MODULE_UAT_REVIEW_REQUIRED",
              "failure": failure, "moduleResults": g["RESULT"], "cleanup": g["CLEANUP"],
              "visibleBaselineRestored": baseline_ok, "createdAccounts": False,
              "healthTestsExecuted": False, "aiProviderCalled": False, "databaseWritesDirect": False,
              "automatedRunnerEnabled": False, "productionAuthorized": False, "liveVerified": False}
    result = build_offline_receipt(report, final_journal, final_baseline, context,
                                   final_rows, final_summaries)
    return {**result, "businessWrites": 0}
