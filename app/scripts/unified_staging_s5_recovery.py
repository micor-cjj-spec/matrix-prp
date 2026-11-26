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
