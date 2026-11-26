"""Offline-only review of an interrupted historical S5 journal.

No file, network, credential or process access. No deletion instructions or
authorization. The legacy journal lacks an authenticated owner/runtime binding
and pre-write baseline, so even absent markers cannot prove baseline recovery.
"""
import re

OWNERS = ("A", "B")
KINDS = ("task", "finance", "record", "video", "practice", "category", "account")
PHASES = {"PREFLIGHT", "TEST", "CLEANUP", "FINISHED", *KINDS}


def _positive_id(value):
    return type(value) is int and value > 0


def _matches(row, marker, kind):
    if kind in ("task", "record"):
        return row.get("title") == marker
    if kind == "finance":
        return row.get("merchant") == marker
    return row.get("name") in (marker, marker + "-v2")


def _result(state, entries=None):
    return {
        "state": state,
        "entries": entries or {},
        "baselineRestored": False,
        "liveVerified": False,
        "cleanupAuthorized": False,
        "productionAuthorized": False,
    }


def assess_interrupted_journal(journal, snapshots):
    """Inspect supplied complete A/B list snapshots for each attempted kind.

    Results are redacted labels only; neither IDs nor markers are returned.
    Snapshots are caller assertions, not authenticated live evidence.
    """
    if not isinstance(journal, dict) or not isinstance(snapshots, dict):
        return _result("INVALID_INPUT")
    run = journal.get("run")
    phase = journal.get("phase")
    attempts = journal.get("attempted")
    if (not isinstance(run, str) or not re.fullmatch(r"UAT396-[0-9a-f]{16}", run)
            or not isinstance(phase, str) or phase not in PHASES
            or not isinstance(attempts, list) or len(attempts) > 14):
        return _result("INVALID_JOURNAL")

    indexed = {}
    for entry in attempts:
        if not isinstance(entry, dict):
            return _result("INVALID_JOURNAL")
        owner, kind, marker, rid = (entry.get(k) for k in ("owner", "kind", "marker", "id"))
        if (set(entry) != {"owner", "kind", "marker", "id"}
                or owner not in OWNERS or kind not in KINDS
                or marker != run + "-" + owner
                or (rid is not None and not _positive_id(rid))):
            return _result("INVALID_JOURNAL")
        key = owner + "_" + kind
        if key in indexed:
            return _result("INVALID_JOURNAL")
        indexed[key] = entry

    # No attempted writes is not a recovered or verified runtime.
    if not indexed:
        return _result("NO_ATTEMPTS_OBSERVED")

    lists = {}
    for kind in {e["kind"] for e in indexed.values()}:
        for owner in OWNERS:
            key = owner + "_" + kind
            rows = snapshots.get(key)
            if not isinstance(rows, list):
                return _result("INCOMPLETE_SNAPSHOTS")
            if any(not isinstance(r, dict) or not _positive_id(r.get("id")) for r in rows):
                return _result("INVALID_SNAPSHOT")
            by_id = {r["id"]: r for r in rows}
            if len(by_id) != len(rows):
                return _result("INVALID_SNAPSHOT")
            lists[key] = by_id

    states = {}
    for key, entry in indexed.items():
        owner, kind, marker, rid = (entry[k] for k in ("owner", "kind", "marker", "id"))
        other = "B" if owner == "A" else "A"
        own = lists[key]
        foreign = lists[other + "_" + kind]
        matches = [i for i, r in own.items() if _matches(r, marker, kind)]
        if (any(_matches(r, marker, kind) for r in foreign.values())
                or (rid is not None and rid in foreign)
                or any(i in foreign for i in matches)):
            state = "CROSS_OWNER_CONFLICT"
        elif len(matches) > 1:
            state = "AMBIGUOUS_MARKER"
        elif rid is not None and ((rid in own and matches != [rid])
                                  or (matches and matches != [rid])):
            state = "ID_MARKER_CONFLICT"
        elif matches:
            state = "KNOWN_ID_REMAINS" if rid is not None else "UNCONFIRMED_CREATE_REMAINS"
        else:
            state = "NO_MATCH_OBSERVED"
        states[key] = state
    return _result(
        "NO_MARKERS_OBSERVED" if all(s == "NO_MATCH_OBSERVED" for s in states.values())
        else "RECOVERY_REVIEW_REQUIRED", states
    )


# Baseline sidecar: local/offline rehearsal only. Not an authenticated journal
# or a live executor. Persist digests, never raw business rows or credentials.
import hashlib
import json
import os
import stat
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASELINE_FILE = "s5-baseline.json"
MAX_BASELINE_BYTES = 16384
BASELINE_KEYS = {w + "_" + k for w in OWNERS for k in KINDS}
IMAGE_KEYS = {"backend", "gateway", "mysql"}
S5_SOURCE_SHA256 = "2c199c8b0fae7bdaaae2a10cc3d06f2bfd8fd33ee8c096b9399d4ccb1eb0d04c"


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _hex(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _binding(context):
    if not isinstance(context, dict) or set(context) != {
        "run", "month", "target", "schema", "images", "owners", "sourceSha256"
    }:
        raise ValueError("INVALID_CONTEXT")
    if (not isinstance(context["run"], str)
            or not re.fullmatch(r"UAT396-[0-9a-f]{16}", context["run"])
            or not isinstance(context["month"], str)
            or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", context["month"])
            or context["target"] != "https://prp-test.micor.top"
            or type(context["schema"]) is not int or context["schema"] != 31
            or context["sourceSha256"] != S5_SOURCE_SHA256):
        raise ValueError("INVALID_CONTEXT")
    images, owners = context["images"], context["owners"]
    if (not isinstance(images, dict) or set(images) != IMAGE_KEYS
            or any(not isinstance(v, str) or not v.startswith("sha256:")
                   or not _hex(v[7:]) for v in images.values())
            or not isinstance(owners, dict) or set(owners) != set(OWNERS)
            or any(not _positive_id(v) for v in owners.values())
            or owners["A"] == owners["B"]):
        raise ValueError("INVALID_CONTEXT")
    return _sha(context)


def _summary_digest(values):
    if not isinstance(values, dict) or set(values) != {"income", "expense", "balance"}:
        raise ValueError("INVALID_SUMMARY")
    normalized = {}
    for k, v in values.items():
        if not isinstance(v, (str, int, float, Decimal)) or isinstance(v, bool):
            raise ValueError("INVALID_SUMMARY")
        try:
            n = Decimal(str(v))
            if not n.is_finite() or len(n.as_tuple().digits) > 64 or abs(n.as_tuple().exponent) > 64:
                raise ValueError("INVALID_SUMMARY")
            # Decimal.normalize uses context precision; avoid rounding arbitrary
            # input by stripping trailing zeroes from exact fixed-point text.
            text = format(n, "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            normalized[k] = "0" if n == 0 else text
        except InvalidOperation as exc:
            raise ValueError("INVALID_SUMMARY") from exc
    return _sha(normalized)


def capture_baseline(context, snapshots, summaries):
    """Build an immutable digest-only observation for all 14 lists and 2 summaries."""
    binding = _binding(context)
    if not isinstance(snapshots, dict) or set(snapshots) != BASELINE_KEYS:
        raise ValueError("INCOMPLETE_BASELINE")
    if not isinstance(summaries, dict) or set(summaries) != set(OWNERS):
        raise ValueError("INCOMPLETE_BASELINE")
    digests = {}
    for key, rows in snapshots.items():
        if (not isinstance(rows, list) or any(not isinstance(r, dict)
                or not _positive_id(r.get("id")) for r in rows)
                or len({r["id"] for r in rows}) != len(rows)):
            raise ValueError("INVALID_BASELINE_LIST")
        digests[key] = _sha(sorted(rows, key=lambda r: r["id"]))
    payload = {
        "schemaVersion": 1, "contextDigest": binding,
        "lists": digests,
        "finance": {w: _summary_digest(summaries[w]) for w in OWNERS},
    }
    return {**payload, "contentDigest": _sha(payload)}


def _validate_baseline(value):
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "contextDigest", "lists", "finance", "contentDigest"
    }:
        raise ValueError("INVALID_BASELINE")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or not _hex(value["contextDigest"]) or not _hex(value["contentDigest"])):
        raise ValueError("INVALID_BASELINE")
    for name, keys in (("lists", BASELINE_KEYS), ("finance", set(OWNERS))):
        if (not isinstance(value[name], dict) or set(value[name]) != keys
                or not all(_hex(v) for v in value[name].values())):
            raise ValueError("INVALID_BASELINE")
    if _sha({k: v for k, v in value.items() if k != "contentDigest"}) != value["contentDigest"]:
        raise ValueError("BASELINE_DIGEST_MISMATCH")


def _private_dir(directory):
    p = Path(directory)
    if not p.is_absolute() or p.resolve() != p:
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    s = os.fstat(fd)
    if s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o700:
        os.close(fd)
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    return fd


def persist_baseline_once(directory, baseline):
    """Rehearsal of durable exclusive sidecar creation in a private directory.

    fsync data, atomically link to the fixed name without replacing existing
    evidence, remove temp name, fsync directory. No automatic overwrite/retry.
    """
    _validate_baseline(baseline)
    raw = json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(raw) > MAX_BASELINE_BYTES:
        raise ValueError("BASELINE_TOO_LARGE")
    fd = _private_dir(directory)
    tmp = None
    try:
        # Use the opened directory descriptor for all filesystem mutations.
        tmp = ".baseline-" + os.urandom(16).hex()
        f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(f, "wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.link(tmp, BASELINE_FILE, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        finally:
            os.unlink(tmp, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)


def read_baseline(directory):
    fd = _private_dir(directory)
    try:
        f = os.open(BASELINE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(f, "rb") as inp:
            s = os.fstat(inp.fileno())
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                    or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1
                    or s.st_size > MAX_BASELINE_BYTES):
                raise ValueError("INVALID_BASELINE_FILE")
            raw = inp.read(MAX_BASELINE_BYTES + 1)
        if len(raw) > MAX_BASELINE_BYTES:
            raise ValueError("BASELINE_TOO_LARGE")
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise ValueError("DUPLICATE_BASELINE_KEY")
                result[k] = v
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        _validate_baseline(value)
        return value
    finally:
        os.close(fd)


def compare_baseline(baseline, context, snapshots, summaries):
    """Compare complete caller observations; never assert verified restoration."""
    try:
        _validate_baseline(baseline)
        current = capture_baseline(context, snapshots, summaries)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return _result("INVALID_BASELINE_OBSERVATION")
    if baseline["contextDigest"] != current["contextDigest"]:
        return _result("BASELINE_CONTEXT_MISMATCH")
    changes = {k: "CHANGED" for k in BASELINE_KEYS
               if baseline["lists"][k] != current["lists"][k]}
    changes.update({"finance_summary_" + w: "CHANGED" for w in OWNERS
                    if baseline["finance"][w] != current["finance"][w]})
    return _result("BASELINE_DIFFERENCE_OBSERVED" if changes else
                   "BASELINE_DIGESTS_MATCH", changes)


OFFLINE_MODULES = {"task", "finance", "record", "video", "practice"}
FALSE_REPORT_FLAGS = ("createdAccounts", "healthTestsExecuted", "aiProviderCalled",
                      "databaseWritesDirect", "automatedRunnerEnabled",
                      "productionAuthorized", "liveVerified")


def build_offline_receipt(report, journal, baseline, context, snapshots, summaries):
    """Compose diagnostic rehearsal evidence, never live or release authority."""
    diff = compare_baseline(baseline, context, snapshots, summaries)
    recovery = assess_interrupted_journal(journal, snapshots)
    modules = report.get("moduleResults") if isinstance(report, dict) else None
    cleanup = report.get("cleanup") if isinstance(report, dict) else None
    module_count = sum(modules.get(k) == "CRUD_AND_BIDIRECTIONAL_ISOLATION_PASS"
                       for k in OFFLINE_MODULES) if isinstance(modules, dict) else 0
    cleanup_count = sum(cleanup.get(k) == "API_ABSENT"
                        for k in BASELINE_KEYS) if isinstance(cleanup, dict) else 0
    complete = (
        isinstance(report, dict)
        and report.get("state") == "CROSS_MODULE_UAT_PASS"
        and "failure" in report and report["failure"] is None
        and report.get("visibleBaselineRestored") is True
        and all(report.get(k) is False for k in FALSE_REPORT_FLAGS)
        and isinstance(modules, dict) and set(modules) == OFFLINE_MODULES
        and module_count == 5
        and isinstance(cleanup, dict) and set(cleanup) == BASELINE_KEYS
        and cleanup_count == 14
        and isinstance(journal, dict) and isinstance(context, dict)
        and journal.get("run") == context.get("run")
        and journal.get("phase") == "FINISHED"
        and journal.get("results") == modules and journal.get("cleanup") == cleanup
        and recovery["state"] == "NO_MARKERS_OBSERVED"
        and set(recovery["entries"]) == BASELINE_KEYS
        and diff["state"] == "BASELINE_DIGESTS_MATCH"
    )
    return {
        "schemaVersion": 1, "kind": "S5_OFFLINE_REHEARSAL",
        "state": "OFFLINE_REHEARSAL_PASS" if complete else "OFFLINE_REVIEW_REQUIRED",
        "modulesPassed": module_count, "cleanupObservedAbsent": cleanup_count,
        "baselineState": diff["state"], "recoveryState": recovery["state"],
        "liveVerified": False, "baselineRestored": False,
        "cleanupAuthorized": False, "automatedRunnerEnabled": False,
        "productionAuthorized": False, "deploymentAuthorized": False,
    }
