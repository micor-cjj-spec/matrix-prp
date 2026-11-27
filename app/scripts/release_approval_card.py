#!/usr/bin/env python3
"""Offline card projection and owner-decision envelope. No UI host, RPC or executor."""
import copy

from release_approval_contract import binding, MODE, OWNER, REQUIRED, require
from release_approval_store import FLAGS
from release_evidence import exact, inventory

CARD_KIND = "SYNTHETIC_RELEASE_APPROVAL_CARD"
STATES = {"REQUESTED", "APPROVED", "REJECTED", "EXPIRED", "SIMULATED_CONSUMED"}
LABELS = {
    "REQUESTED": "Pending synthetic owner decision",
    "APPROVED": "Synthetic approval recorded; no execution",
    "REJECTED": "Synthetic request rejected",
    "EXPIRED": "Synthetic request expired",
    "SIMULATED_CONSUMED": "Simulation consumed; no real deployment",
}


def _prepare(snapshot):
    # Bind once to a defensive copy; render and apply the same reviewed fields.
    snapshot = copy.deepcopy(snapshot)
    checked = binding(snapshot)
    return snapshot, checked


def _project(record, snapshot, checked):
    digest, candidate, run, attempt = checked
    require(record["mode"] == MODE and record["binding_digest"] == digest
            and record["candidate"] == candidate and record["ci_run_id"] == run
            and record["ci_run_attempt"] == attempt and record["action"] == "promote"
            and record["state"] in STATES and all(record.get(k) is False for k in FLAGS),
            "CARD_RECORD_BINDING_MISMATCH")
    state = record["state"]
    report = inventory(snapshot["bundle"])
    evidence = snapshot["bundle"]["evidence"]
    return {
        "schema_version": 1, "kind": CARD_KIND, "mode": MODE,
        "notice": "OFFLINE SIMULATION ONLY; NOT A PRODUCTION APPROVAL",
        "approval_id": record["approval_id"], "binding_digest": digest,
        "state": state, "message": LABELS[state],
        "candidate": candidate, "artifact_id": snapshot["artifact_id"],
        "action": "promote", "ci_run_id": run, "ci_run_attempt": attempt,
        "risk": evidence["risk"]["risk"], "hold": report["hold_state"],
        "hold_ref": report["hold_binding"]["ref"],
        "gates": [{"gate": row["gate"], "status": row["status"], "ref": row["evidence_ref"]}
                  for row in report["gates"] if row["gate"] in REQUIRED],
        "specialist_review": copy.deepcopy(snapshot["specialist_review"]),
        "created_at": record["created_at"], "expires_at": record["expires_at"],
        "approved_at": record["approved_at"], "consumed_at": record["consumed_at"],
        "available_decisions": ["approve", "reject"] if state == "REQUESTED" else [],
        **{key: False for key in FLAGS},
    }


def render_card(store, approval_id, reviewed_digest, snapshot, now):
    snapshot, checked = _prepare(snapshot)
    require(reviewed_digest == checked[0], "STALE_OR_CHANGED_EVIDENCE")
    record = store.inspect(approval_id, reviewed_digest, now)
    return _project(record, snapshot, checked)


def submit_decision(store, envelope, snapshot, actor, now):
    """Only the synthetic harness supplies actor/time. No automatic consumption.

    Both card decisions are atomically restricted to REQUESTED by the ledger.
    A stale reject cannot revoke an approval from a competing click.
    """
    envelope = copy.deepcopy(envelope)
    exact(envelope, {"approval_id", "binding_digest", "decision"}, "card decision")
    require(actor == OWNER, "OWNER_DECISION_REQUIRED")
    require(type(envelope["decision"]) is str and envelope["decision"] in ("approve", "reject"),
            "UNSUPPORTED_CARD_DECISION")
    snapshot, checked = _prepare(snapshot)
    require(envelope["binding_digest"] == checked[0], "STALE_OR_CHANGED_EVIDENCE")
    operation = store.approve if envelope["decision"] == "approve" else store.reject_pending
    record = operation(envelope["approval_id"], envelope["binding_digest"], snapshot, actor, now)
    return _project(record, snapshot, checked)
