#!/usr/bin/env python3
"""P3 synthetic approval contract. No production authorization, IO or execution."""
import copy
import hashlib
import json
import threading
import uuid

from release_evidence import exact, sha, digest, schema, inventory, REPO

MODE = "OFFLINE_REHEARSAL_ONLY"
CHAT = "synthetic:chat"
OWNER = "synthetic:owner"
CONTROLLER = "synthetic:controller"
ENVIRONMENT_REVIEWER = "synthetic:environment-reviewer"
MAX_TTL = 900
MAX_CLOCK = 2**53 - 1
REQUIRED = {"ci", "risk", "artifact", "staging", "migration", "backup_restore"}
ACTIVE = {"REQUESTED", "APPROVED"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def positive(value):
    return type(value) is int and 0 < value <= MAX_CLOCK


def synthetic_ref(value):
    return (type(value) is str and value.startswith("synthetic:") and
            10 < len(value) <= 120 and all(c.isascii() and
            (c.isalnum() or c in ":._-") for c in value))


def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                     allow_nan=False).encode("ascii")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def binding(snapshot):
    """Validate current *assertions*, not trusted evidence; return immutable digest."""
    s = copy.deepcopy(snapshot)
    exact(s, {"mode", "action", "main_sha", "artifact_id", "bundle",
              "specialist_review"}, "approval snapshot")
    require(s["mode"] == MODE and s["action"] == "promote", "OFFLINE_PROMOTE_ONLY")
    require(sha(s["main_sha"]) and positive(s["artifact_id"]), "INVALID_ARTIFACT_OR_MAIN")
    report = inventory(s["bundle"])
    candidate = report["candidate"]
    require(candidate["repository"] == REPO and candidate["commit"] == s["main_sha"]
            and digest(candidate["artifact_digest"]) and schema(candidate["schema"]),
            "CANDIDATE_NOT_BOUND_TO_MAIN")
    require(report["hold_state"] == "clear" and synthetic_ref(report["hold_binding"]["ref"]),
            "HOLD_ACTIVE_OR_UNKNOWN")
    evidence = s["bundle"]["evidence"]
    require(set(evidence) == REQUIRED and all(synthetic_ref(e["ref"]) for e in evidence.values()),
            "MISSING_OR_NON_SYNTHETIC_PRECONDITIONS")
    require(all(row["status"] == "pass" for row in report["gates"] if row["gate"] in REQUIRED),
            "PRECONDITIONS_NOT_PASS")
    require(evidence["artifact"]["ref"] == "synthetic:artifact:" + str(s["artifact_id"]),
            "ARTIFACT_ID_MISMATCH")
    risk = evidence["risk"]["risk"]
    review = s["specialist_review"]
    if risk == "HIGH_REVIEW":
        exact(review, {"commit", "artifact_digest", "schema", "status", "ref"}, "specialist review")
        require(review["commit"] == candidate["commit"] and
                review["artifact_digest"] == candidate["artifact_digest"] and
                type(review["schema"]) is int and review["schema"] == candidate["schema"] and
                review["status"] == "pass" and synthetic_ref(review["ref"]),
                "HIGH_RISK_REVIEW_REQUIRED")
    else:
        require(review is None, "UNEXPECTED_SPECIALIST_REVIEW")
    return fingerprint(s), candidate.copy(), evidence["ci"]["run_id"], evidence["ci"]["run_attempt"]


class OfflineApprovals:
    """In-process, synthetic state machine. No persistent or cross-process authority."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records = {}
        self._candidate_keys = set()
        self._last_time = 0

    def _clock(self, now):
        require(positive(now) and now >= self._last_time, "INVALID_OR_REWOUND_CLOCK")
        self._last_time = now

    def _event(self, record, event, actor, now):
        record["audit"].append({"sequence": len(record["audit"]) + 1,
                                "event": event, "actor": actor, "at": now,
                                "binding_digest": record["binding_digest"]})

    def _record(self, approval_id, reviewed_digest, now):
        require(type(approval_id) is str and approval_id in self._records, "UNKNOWN_APPROVAL")
        record = self._records[approval_id]
        require(digest(reviewed_digest) and reviewed_digest == record["binding_digest"],
                "APPROVAL_BINDING_MISMATCH")
        if record["state"] in ACTIVE and now >= record["expires_at"]:
            record["state"] = "EXPIRED"
            self._event(record, "EXPIRED", "synthetic:clock", now)
        return record

    def request(self, snapshot, actor, now, ttl=MAX_TTL):
        require(actor == CHAT and positive(ttl) and ttl <= MAX_TTL,
                "INVALID_REQUESTER_OR_TTL")
        binding_digest, candidate, run, attempt = binding(snapshot)
        key = (candidate["commit"], candidate["artifact_digest"], "promote")
        with self._lock:
            self._clock(now)
            require(now <= MAX_CLOCK - ttl, "INVALID_EXPIRY")
            # No second request for the same candidate/action in one rehearsal,
            # even after rejection, expiry or consumption.
            require(key not in self._candidate_keys, "DUPLICATE_CANDIDATE_REQUEST")
            approval_id = str(uuid.uuid4())
            require(approval_id not in self._records, "APPROVAL_ID_COLLISION")
            record = {"schema_version": 1, "mode": MODE, "approval_id": approval_id,
                      "binding_digest": binding_digest, "candidate": candidate,
                      "ci_run_id": run, "ci_run_attempt": attempt,
                      "action": "promote", "state": "REQUESTED",
                      "created_at": now, "expires_at": now + ttl,
                      "approved_at": None, "consumed_at": None, "audit": [],
                      "production_authorized": False, "deployment_authorized": False,
                      "release_eligible": False, "live_verified": False}
            self._event(record, "REQUESTED", actor, now)
            self._records[approval_id] = record
            self._candidate_keys.add(key)
            return copy.deepcopy(record)

    def approve(self, approval_id, reviewed_digest, snapshot, actor, now):
        require(actor == OWNER, "OWNER_DECISION_REQUIRED")
        fresh, _, _, _ = binding(snapshot)
        with self._lock:
            self._clock(now)
            record = self._record(approval_id, reviewed_digest, now)
            require(record["state"] == "REQUESTED", "NOT_REQUESTED_OR_EXPIRED")
            require(fresh == reviewed_digest, "STALE_OR_CHANGED_EVIDENCE")
            record["state"] = "APPROVED"
            record["approved_at"] = now
            self._event(record, "APPROVED", actor, now)
            return copy.deepcopy(record)

    def reject(self, approval_id, reviewed_digest, actor, now):
        require(actor == OWNER, "OWNER_DECISION_REQUIRED")
        with self._lock:
            self._clock(now)
            record = self._record(approval_id, reviewed_digest, now)
            require(record["state"] in ACTIVE, "NOT_ACTIVE")
            record["state"] = "REJECTED"
            self._event(record, "REJECTED", actor, now)
            return copy.deepcopy(record)

    def reject_pending(self, approval_id, reviewed_digest, snapshot, actor, now):
        """A pending-card decision, not revocation of an already approved record."""
        require(actor == OWNER, "OWNER_DECISION_REQUIRED")
        fresh, _, _, _ = binding(snapshot)
        with self._lock:
            self._clock(now)
            record = self._record(approval_id, reviewed_digest, now)
            require(record["state"] == "REQUESTED", "NOT_REQUESTED_OR_EXPIRED")
            require(fresh == reviewed_digest, "STALE_OR_CHANGED_EVIDENCE")
            record["state"] = "REJECTED"
            self._event(record, "REJECTED", actor, now)
            return copy.deepcopy(record)

    def consume(self, approval_id, reviewed_digest, snapshot, environment, actor, now):
        require(actor == CONTROLLER, "SYNTHETIC_CONTROLLER_REQUIRED")
        fresh, _, _, _ = binding(snapshot)
        env = copy.deepcopy(environment)
        exact(env, {"approval_id", "binding_digest", "actor", "status", "ref", "at"},
              "environment review")
        with self._lock:
            self._clock(now)
            record = self._record(approval_id, reviewed_digest, now)
            require(record["state"] == "APPROVED", "NOT_APPROVED_OR_ALREADY_CONSUMED")
            require(fresh == reviewed_digest, "STALE_OR_CHANGED_EVIDENCE")
            require(env["approval_id"] == approval_id and env["binding_digest"] == reviewed_digest
                    and env["actor"] == ENVIRONMENT_REVIEWER and env["status"] == "pass"
                    and synthetic_ref(env["ref"]) and positive(env["at"])
                    and record["approved_at"] <= env["at"] <= now < record["expires_at"],
                    "ENVIRONMENT_REVIEW_MISSING_OR_STALE")
            # Atomic within this process. No callback or side effect follows.
            record["state"] = "SIMULATED_CONSUMED"
            record["consumed_at"] = now
            record["environment_ref"] = env["ref"]
            self._event(record, "SIMULATED_CONSUMED", actor, now)
            return copy.deepcopy(record)

    def inspect(self, approval_id, reviewed_digest, now):
        with self._lock:
            self._clock(now)
            return copy.deepcopy(self._record(approval_id, reviewed_digest, now))
