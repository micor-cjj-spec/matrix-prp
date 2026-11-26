"""S6.2B S5 orchestration; offline default, explicit local operator entry."""
import argparse
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
import sys
import time
from decimal import Decimal
from pathlib import Path

from unified_staging_s5_local_preflight import (
    IMAGES, LOCK, PATHS, TARGET, credentials, load_helper, lock_identity, login, observe,
    private_fd, private_parent, require_disjoint, same_user, success, verify_stage,
)
from unified_staging_s5_recovery import (
    BASELINE_FILE, S5_SOURCE_SHA256, build_offline_receipt, capture_baseline, compare_baseline,
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
    """Explicit test seam, never accepted by the real operator entry."""

    def simulate(self, path, *, method, payload, token):
        raise NotImplementedError


APPROVAL = "EXECUTE S6.2B ONCE ON PRP-TEST"
REQUEST_LIMIT = 58
READ_ROUTES = frozenset((*PATHS.values(), "/api/users/me"))


def read_route(path):
    return (path in READ_ROUTES or
            re.fullmatch(r"/api/finance/summary/monthly\?month=[0-9]{4}-(?:0[1-9]|1[0-2])", path) is not None)


def business_route(path, method):
    if method == "GET":
        return (read_route(path) or
                re.fullmatch(r"/api/video/items\?folderId=[1-9][0-9]*", path) is not None or
                re.fullmatch(r"/api/practice/subjects/[1-9][0-9]*/banks", path) is not None)
    if method == "POST":
        return path in PATHS.values()
    if method in ("PUT", "DELETE"):
        return any(re.fullmatch(re.escape(base) + r"/[1-9][0-9]*", path) for base in PATHS.values())
    return False


class _LocalTransport:
    """Narrow adapter for a byte-verified, existing p420 module.

    No delegation of provisioning, arbitrary SQL, filesystem or deployment
    APIs. The orchestration's same-run guards remain the write boundary.
    """
    def __init__(self, helper):
        self._helper = helper
        self.CREDENTIAL_DIR = helper.CREDENTIAL_DIR
        self.CREDENTIAL_FILE = helper.CREDENTIAL_FILE
        self.BACKEND, self.GATEWAY, self.MYSQL = helper.BACKEND, helper.GATEWAY, helper.MYSQL
        self._active = False
        self._used = False
        self._outcomes = []

    def inspect_target(self):
        return self._helper.inspect_target()

    def validate_target(self, meta):
        return self._helper.validate_target(meta)

    def _run(self, command, *, input_text=None):
        # The only caller is the unchanged S6.2A fixed schema/image checker.
        return self._helper._run(command, input_text=input_text)

    def read_existing_credentials(self):
        old = self._helper.CREDENTIAL_DIR, self._helper.CREDENTIAL_FILE
        try:
            self._helper.CREDENTIAL_DIR = self.CREDENTIAL_DIR
            self._helper.CREDENTIAL_FILE = self.CREDENTIAL_FILE
            return self._helper.read_existing_credentials()
        finally:
            self._helper.CREDENTIAL_DIR, self._helper.CREDENTIAL_FILE = old

    def query_ordinary_identity_readonly(self, c):
        return self._helper.query_ordinary_identity_readonly(c)

    def valid_json_type(self, value):
        return self._helper.valid_json_type(value)

    def http_json(self, path, *, method="GET", payload=None, token=None):
        check(self._active, "OPERATOR_RUN_INACTIVE")
        check((method == "GET" and read_route(path) and payload is None and token)
              or (method == "POST" and path == "/api/auth/login" and token is None
                  and isinstance(payload, dict) and set(payload) == {"username", "password"}),
              "PREFLIGHT_ROUTE_BLOCKED")
        return self._helper.http_json(path, method=method, payload=payload, token=token)

    def _dispatch(self, path, *, method, payload, token):
        check(self._active and token and business_route(path, method), "LOCAL_ROUTE_BLOCKED")
        if method == "GET":
            check(payload is None, "GET_PAYLOAD_BLOCKED")
            return self._helper.http_json(path, method=method, token=token)
        check(len(self._outcomes) < REQUEST_LIMIT, "REQUEST_LIMIT")
        check((method == "DELETE" and payload is None) or
              (method in ("POST", "PUT") and isinstance(payload, dict)), "PAYLOAD_BLOCKED")
        # Count attempts before transport: a lost response is not zero writes.
        self._outcomes.append("UNKNOWN")
        response = self._helper.http_json(path, method=method, payload=payload, token=token)
        status = response[0]
        if type(status) is int and 100 <= status <= 599:
            self._outcomes[-1] = "HTTP_" + str(status)
        return response

    def _receipt(self, diagnostic):
        requests = len(self._outcomes)
        success_count = self._outcomes.count("HTTP_200")
        denials = sum(x in ("HTTP_403", "HTTP_404") for x in self._outcomes)
        unknown = self._outcomes.count("UNKNOWN")
        matched = diagnostic["baselineState"] == "BASELINE_DIGESTS_MATCH"
        passed = (diagnostic["state"] == "OFFLINE_REHEARSAL_PASS"
                  and requests == REQUEST_LIMIT and success_count == 38 and denials == 20)
        result = dict(diagnostic)
        result.update(schemaVersion=1, kind="S5_LOCAL_OPERATOR_REGRESSION",
                      state=("S5_LOCAL_REGRESSION_PASS" if passed else
                             "S5_LOCAL_REGRESSION_REVIEW_REQUIRED" if requests else
                             "S5_LOCAL_REGRESSION_BLOCKED"),
                      executionMode="OPERATOR_LIVE", businessMutationRequests=requests,
                      mutationResponses200=success_count, mutationResponsesDenied=denials,
                      mutationOutcomesUnknown=unknown,
                      mutationResponsesOther=requests-success_count-denials-unknown,
                      businessWrites="NOT_MEASURED" if requests else 0,
                      apiVisibleBaselineMatched=matched, liveExecutionPerformed=bool(requests),
                      liveVerified=False, baselineRestored=False, cleanupAuthorized=False)
        return result


def check(ok, label):
    if not ok:
        raise RuntimeError(label)


EVIDENCE_DOMAIN = "PRP_S63_S5_ADVISORY_V1"
CANDIDATE_KEYS = {"commit", "tree", "artifact_digest", "backend_image", "executor_commit"}


def _digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _candidate_claim(value):
    """Optional, unverified mapping; not a trust anchor or execution approval."""
    if value is None:
        return None
    check(type(value) is dict and set(value) == CANDIDATE_KEYS, "INVALID_CANDIDATE_CLAIM")
    for key in ("commit", "tree", "executor_commit"):
        check(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{40}", value[key]),
              "INVALID_CANDIDATE_CLAIM")
    for key in ("artifact_digest", "backend_image"):
        check(type(value[key]) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value[key]),
              "INVALID_CANDIDATE_CLAIM")
    check(value["backend_image"] == IMAGES["backend"], "CANDIDATE_IMAGE_PIN_MISMATCH")
    return dict(value)


def _source_digests():
    """Local file hashes, not proof of Git commit or executed bytes."""
    return {"regression": _digest(Path(__file__).read_bytes()),
            "preflight": _digest(Path(__file__).with_name("unified_staging_s5_local_preflight.py").read_bytes()),
            "recovery": _digest(Path(__file__).with_name("unified_staging_s5_recovery.py").read_bytes()),
            "fixture": _digest(SOURCE.read_bytes())}


def _baseline_bytes(journal, baseline):
    journal.verify_dir()
    fd = os.open(BASELINE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.fd)
    with os.fdopen(fd, "rb") as inp:
        info = os.fstat(inp.fileno())
        check(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
              and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
              and info.st_size <= LIMIT, "INVALID_BASELINE_EVIDENCE")
        raw = inp.read(LIMIT + 1)
    check(raw == Journal.encode(baseline), "BASELINE_EVIDENCE_BYTES_MISMATCH")
    return raw


def _advisory_evidence(*, live, claim, sources, before, after, window, journal_bytes,
                       baseline_bytes, diagnostic):
    check(len(window) == 4 and all(type(v) is int and v > 0 for v in window)
          and list(window) == sorted(window), "EVIDENCE_TIME_WINDOW_INVALID")
    check(before == after, "EVIDENCE_RUNTIME_MISMATCH")
    images = {k: row[1] for k, row in before[0].items()}
    check(images == IMAGES, "EVIDENCE_IMAGE_MISMATCH")
    j = json.loads(journal_bytes)
    mode = "OPERATOR_LIVE" if live else "OFFLINE_SIMULATION"
    check(j["phase"] == "FINISHED" and j["executionMode"] == mode
          and j["candidateClaim"] == claim and j["sourceDigests"] == sources
          and [j["runtimeBeforeAt"], j["startedAt"]] == window[:2]
          and j["runtimeDigest"] == hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
          "EVIDENCE_JOURNAL_BINDING_MISMATCH")
    baseline = json.loads(baseline_bytes)
    check(j["baselineDigest"] == baseline["contentDigest"]
          and j["contextDigest"] == baseline["contextDigest"], "EVIDENCE_BASELINE_BINDING_MISMATCH")
    modules = {k: ("pass" if j["results"].get(k) == "CRUD_AND_BIDIRECTIONAL_ISOLATION_PASS"
                   else "pending") for k in MODULES}
    cleanup = {w + "_" + k: ("pass" if j["cleanup"].get(w + "_" + k) == "API_ABSENT"
               else "pending") for w in ("A", "B") for k in PATHS}
    statuses = [o["outcome"] for o in j["mutationRequests"]]
    counts = {"recorded": len(statuses), "http_200": statuses.count("HTTP_200"),
              "http_denied": sum(x in ("HTTP_403", "HTTP_404") for x in statuses),
              "unknown_or_pending": sum(x in ("UNKNOWN", "PENDING") for x in statuses)}
    counts["other"] = len(statuses) - sum(counts[k] for k in ("http_200", "http_denied", "unknown_or_pending"))
    matched = diagnostic["baselineState"] == "BASELINE_DIGESTS_MATCH"
    complete = (diagnostic["state"] == "OFFLINE_REHEARSAL_PASS" and matched
                and counts == {"recorded": REQUEST_LIMIT, "http_200": 38, "http_denied": 20,
                               "unknown_or_pending": 0, "other": 0}
                and set(modules.values()) == {"pass"} and set(cleanup.values()) == {"pass"})
    findings = ["SOURCE_AUTHENTICITY_NOT_ESTABLISHED", "TRUSTED_CLOCK_NOT_ESTABLISHED",
                "INDEPENDENT_RUNTIME_AND_DATABASE_PROOF_NOT_ESTABLISHED",
                "INDEPENDENT_EVIDENCE_BYTES_NOT_ESTABLISHED", "INDEPENDENT_HUMAN_PROOF_NOT_ESTABLISHED"]
    if claim is None:
        findings.append("CANDIDATE_CLAIM_MISSING")
    if not live:
        findings.append("OFFLINE_SIMULATION_NOT_STAGE_BUSINESS_UAT")
    if not complete:
        findings.append("BUSINESS_REGRESSION_INCOMPLETE")
    value = {
        "schema_version": 1, "source": "operator_regression_claim" if live else "offline_simulation",
        "state": "BLOCKED", "repository": "micor-cjj-spec/matrix-prp",
        "environment": "prp-unified-396", "issue": 396, "execution_mode": mode,
        "candidate": None if claim is None else {"repository": "micor-cjj-spec/matrix-prp",
                         "commit": claim["commit"], "artifact_digest": claim["artifact_digest"], "schema": 31},
        "candidate_tree_claim": None if claim is None else claim["tree"],
        "executor_commit_claim": None if claim is None else claim["executor_commit"],
        "candidate_backend_image_claim": None if claim is None else claim["backend_image"],
        "candidate_source_verified": False, "source_digests": dict(sources),
        "observed_images": images, "schema": 31,
        "window": dict(zip(("runtime_before_at", "started_at", "finished_at", "runtime_after_at"), window)),
        "ordinary_two_owner_checks_claimed": True, "runtime_unchanged_claimed": True,
        "module_results": modules, "cleanup_results": cleanup,
        "journal_recorded_mutation_outcomes": counts,
        "api_visible_baseline_matched_claimed": matched, "regression_complete_claimed": complete,
        "journal_bytes_digest": _digest(journal_bytes), "baseline_bytes_digest": _digest(baseline_bytes),
        "baseline_content_digest": "sha256:" + j["baselineDigest"],
        "context_digest": "sha256:" + j["contextDigest"], "findings": sorted(findings),
        "source_authenticated": False, "artifact_bytes_verified": False, "runtime_verified": False,
        "business_uat_verified": False, "baseline_restored": False, "current_review_satisfied": False,
        "release_eligible": False, "approval_authorized": False, "deployment_authorized": False,
        "production_authorized": False, "live_verified": False,
    }
    return {**value, "binding_digest": _digest(Journal.encode({"domain": EVIDENCE_DOMAIN, "evidence": value}))}


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
            "deploymentAuthorized": False, "businessWrites": 0,
            "advisoryEvidence": None}


def rehearse(sim, directory, b_file, *, candidate_claim=None):
    """Run only an injected synthetic simulation under the original lock.

    The module does not load p420 or expose a live-write flag. Future real
    execution requires a separately reviewed adapter and operator approval.
    """
    check(isinstance(sim, OfflineSimulation), "OFFLINE_SIMULATION_REQUIRED")
    return _run_once(sim, directory, b_file, live=False, candidate_claim=candidate_claim)


def run_operator_once(helper_path, directory, b_file, *, confirmation, candidate_claim=None):
    """Explicit local operator call, never invoked by CI with real transport.

    The confirmation is an operator acknowledgement, not authenticated external
    approval. The operator must already have separate owner authorization.
    """
    check(confirmation == APPROVAL, "OPERATOR_CONFIRMATION_REQUIRED")
    candidate_claim = _candidate_claim(candidate_claim)
    helper = load_helper(Path(helper_path))
    transport = _LocalTransport(helper)
    return _run_once(transport, directory, b_file, live=True, candidate_claim=candidate_claim)


def _run_once(sim, directory, b_file, *, live, candidate_claim=None):
    candidate_claim = _candidate_claim(candidate_claim)
    if live:
        check(type(sim) is _LocalTransport and not sim._used, "OPERATOR_TRANSPORT_REQUIRED")
        sim._used, sim._active = True, True
    else:
        check(isinstance(sim, OfflineSimulation), "OFFLINE_SIMULATION_REQUIRED")
    lock_fd = evidence_fd = None
    diagnostic = blocked_receipt()
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
        diagnostic = _rehearse_locked(sim, directory, b_file, lock_fd, lock_path, journal,
                                      live=live, candidate_claim=candidate_claim)
    except (Exception, KeyboardInterrupt):
        diagnostic = blocked_receipt()
    finally:
        if live:
            sim._active = False
        if evidence_fd is not None:
            os.close(evidence_fd)
        if lock_fd is not None:
            os.close(lock_fd)
    return sim._receipt(diagnostic) if live else diagnostic


def _rehearse_locked(sim, directory, b_file, lock_fd, lock_path, journal, *, live, candidate_claim):
    dispatch = sim._dispatch if live else sim.simulate
    operations = []
    g = load_functions({"Decimal": Decimal, "m": sim})
    sources = _source_digests()
    first = verify_stage(sim)
    runtime_before_at = int(time.time())
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
    started_at = int(time.time())

    def payload():
        return {"run": run, "phase": g["PHASE"], "attempted": list(g["ATTEMPTED"].values()),
                "results": g["RESULT"], "cleanup": g["CLEANUP"],
                "runtimeDigest": runtime_digest, "baselineDigest": baseline["contentDigest"],
                "contextDigest": baseline["contextDigest"],
                "executionMode": "OPERATOR_LIVE" if live else "OFFLINE_SIMULATION",
                "mutationRequests": operations, "candidateClaim": candidate_claim,
                "sourceDigests": sources, "runtimeBeforeAt": runtime_before_at, "startedAt": started_at}

    def save():
        journal.save(payload())

    def recheck():
        lock_identity(lock_fd, lock_path)
        journal.verify_dir()
        observed = verify_stage(sim)
        check(observed == first, "RUNTIME_CHANGED")
        for who, c in accounts.items():
            sim.query_ordinary_identity_readonly(c)
            check(same_user(success(sim, "/api/users/me", tokens[who]), c), "IDENTITY_CHANGED")
        lock_identity(lock_fd, lock_path)
        return observed

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
            return dispatch(path, method=method, payload=payload, token=tokens[who])
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
        check(len(operations) < REQUEST_LIMIT, "REQUEST_LIMIT")
        operation = {"sequence": len(operations) + 1, "phase": phase, "method": method,
                     "owner": who, "kind": kind,
                     "id": None if method == "POST" else rid, "outcome": "PENDING"}
        operations.append(operation)
        save()
        durable()
        try:
            result = dispatch(path, method=method, payload=payload, token=tokens[who])
            status = result[0]
            operation["outcome"] = ("HTTP_" + str(status)
                                    if type(status) is int and 100 <= status <= 599 else "UNKNOWN")
        except Exception:
            operation["outcome"] = "UNKNOWN"
            save()
            raise
        save()
        if method == "POST" and result[0] == 200 and isinstance(result[2], dict):
            data = result[2].get("data")
            if isinstance(data, dict) and type(data.get("id")) is int:
                check(not old_id(kind, data["id"]), "CREATE_RETURNED_BASELINE_ID")
        return result

    g.update(raw=raw, save_local=save)
    failure = None
    final_rows, final_summaries, final_journal, final_baseline = {}, {}, None, None
    baseline_ok = False
    material = None
    try:
        g["PHASE"] = "TEST"
        save()
        durable()
        for kind in MODULES:
            g["PHASE"] = kind
            save()
            g["exercise"](kind)
            save()
    except KeyboardInterrupt:
        halted = True
        failure = "OPERATOR_INTERRUPTED"
    except Exception:
        failure = "EXERCISE_BLOCKED"
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
            finished_at = int(time.time())
            after = recheck()
            runtime_after_at = int(time.time())
            baseline_ok = compare_baseline(final_baseline, context, final_rows,
                                           final_summaries)["state"] == "BASELINE_DIGESTS_MATCH"
            # Output-only: a failed handoff never changes observed request counts.
            try:
                journal.verify(payload())
                raw = journal.read()
                check(raw == journal.current, "EVIDENCE_JOURNAL_CHANGED")
                base_raw = _baseline_bytes(journal, final_baseline)
                check(_source_digests() == sources, "EVIDENCE_SOURCE_CHANGED")
                material = dict(before=first, after=after,
                    window=[runtime_before_at, started_at, finished_at, runtime_after_at],
                    journal_bytes=raw, baseline_bytes=base_raw)
            except Exception:
                material = None
        except Exception:
            failure = "OFFLINE_FINAL_REVIEW_REQUIRED"
    passed = (failure is None and len(g["RESULT"]) == 5 and baseline_ok
              and len(g["CLEANUP"]) == 14 and all(x == "API_ABSENT" for x in g["CLEANUP"].values())
              and len(operations) == REQUEST_LIMIT
              and sum(op["outcome"] == "HTTP_200" for op in operations) == 38
              and sum(op["outcome"] in ("HTTP_403", "HTTP_404") for op in operations) == 20)
    report = {"state": "CROSS_MODULE_UAT_PASS" if passed else "CROSS_MODULE_UAT_REVIEW_REQUIRED",
              "failure": failure, "moduleResults": g["RESULT"], "cleanup": g["CLEANUP"],
              "visibleBaselineRestored": baseline_ok, "createdAccounts": False,
              "healthTestsExecuted": False, "aiProviderCalled": False, "databaseWritesDirect": False,
              "automatedRunnerEnabled": False, "productionAuthorized": False, "liveVerified": False}
    result = build_offline_receipt(report, final_journal, final_baseline, context,
                                   final_rows, final_summaries)
    evidence = None
    if material is not None:
        try:
            evidence = _advisory_evidence(live=live, claim=candidate_claim, sources=sources,
                                          diagnostic=result, **material)
        except Exception:
            evidence = None
    return {**result, "businessWrites": 0, "advisoryEvidence": evidence}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-once", action="store_true")
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--b-file", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--candidate-tree")
    parser.add_argument("--candidate-artifact-digest")
    parser.add_argument("--candidate-backend-image")
    parser.add_argument("--executor-commit")
    args = parser.parse_args()
    claim = {"commit": args.candidate_commit, "tree": args.candidate_tree,
             "artifact_digest": args.candidate_artifact_digest,
             "backend_image": args.candidate_backend_image, "executor_commit": args.executor_commit}
    if not any(v is not None for v in claim.values()):
        claim = None
    try:
        claim = _candidate_claim(claim)
    except RuntimeError:
        parser.error("candidate claim requires all five exact fields and current Backend pin")
    # No default live behavior, no non-interactive or environment bypass.
    if not args.execute_approved_once or not all((args.helper, args.b_file, args.evidence_dir)):
        parser.error("explicit operator flag and all three existing private paths required")
    if not sys.stdin.isatty():
        parser.error("interactive operator terminal required")
    try:
        confirmation = input("After separate owner approval and idle-window confirmation, type "
                             + APPROVAL + ": ")
        result = run_operator_once(args.helper, args.evidence_dir, args.b_file,
                                   confirmation=confirmation, candidate_claim=claim)
    except (Exception, KeyboardInterrupt):
        # Loading/confirmation errors occur before the adapter can send writes.
        result = {"kind": "S5_LOCAL_OPERATOR_REGRESSION", "state": "S5_LOCAL_REGRESSION_BLOCKED",
                  "businessMutationRequests": 0, "businessWrites": 0, "liveVerified": False,
                  "productionAuthorized": False, "deploymentAuthorized": False, "advisoryEvidence": None}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "S5_LOCAL_REGRESSION_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
