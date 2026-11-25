#!/usr/bin/env python3
"""Offline candidate evidence inventory, not a trusted collector or release gate."""
import argparse
import json
import re
from pathlib import Path

from release_status import evaluate

REPO = "micor-cjj-spec/matrix-prp"
GATES = {
    "ci": ("github_actions", "review", "CI maintainer"),
    "risk": ("risk_report", "review", "Technical reviewer"),
    "artifact": ("build_manifest", "review", "Build maintainer"),
    "staging": ("staging_receipt", "staging", "Staging owner (#396)"),
    "migration": ("migration_receipt", "staging", "Database reviewer"),
    "backup_restore": ("restore_receipt", "staging", "Database reviewer"),
    "approval": ("owner_decision", "production", "Repository owner"),
    "publish": ("controller_receipt", "production", "Authorized release operator"),
    "production_smoke": ("smoke_receipt", "production", "Authorized release operator"),
}
ARTIFACT_GATES = {"artifact", "staging", "migration", "backup_restore",
                  "approval", "publish", "production_smoke"}
PRE_PUBLISH = tuple(g for g in GATES if g not in {"publish", "production_smoke"})
STATES = {"pass", "fail", "pending", "skipped"}
RISK = {"NO_RUNTIME_CHANGE", "FEATURE_REVIEW", "SHARED_REVIEW", "HIGH_REVIEW",
        "UNCLASSIFIED"}


def exact(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise ValueError("Invalid fields: " + label)


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def ref(value):
    # Opaque sanitized IDs only. No external URLs, credentials, user data or free text.
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}", value) is not None


def schema(value):
    return type(value) is int and 1 <= value <= 1000000


def inventory(data):
    exact(data, {"schema_version", "candidate", "hold", "evidence"}, "bundle")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported evidence schema")
    c = data["candidate"]
    exact(c, {"repository", "commit", "artifact_digest", "schema"}, "candidate")
    if c["repository"] != REPO or not sha(c["commit"]):
        raise ValueError("Invalid candidate repository or SHA")
    if c["artifact_digest"] is not None and not digest(c["artifact_digest"]):
        raise ValueError("Invalid artifact digest")
    if c["schema"] is not None and not schema(c["schema"]):
        raise ValueError("Invalid expected schema")
    hold = data["hold"]
    exact(hold, {"state", "commit", "ref"}, "hold")
    if hold["state"] not in ("active", "clear", "unknown"):
        raise ValueError("Invalid hold state")
    if not sha(hold["commit"]) or not ref(hold["ref"]):
        raise ValueError("Invalid hold reference")
    hold_state = hold["state"] if hold["commit"] == c["commit"] else "unknown"
    evidence = data["evidence"]
    if not isinstance(evidence, dict) or set(evidence) - set(GATES):
        raise ValueError("Unknown evidence gate")
    rows = []
    for gate, (source, env, owner) in GATES.items():
        e = evidence.get(gate)
        reason = "MISSING_EVIDENCE"
        state = "pending"
        receipt = None
        if gate in evidence:
            keys = {"source", "environment", "commit", "status", "ref"}
            if gate in ARTIFACT_GATES:
                keys |= {"artifact_digest", "schema"}
            if gate == "risk":
                keys.add("risk")
            if gate == "ci":
                keys |= {"run_id", "run_attempt", "tested_commit", "all_jobs_success"}
            exact(e, keys, gate)
            if e["source"] != source or e["environment"] != env or not sha(e["commit"]) or not ref(e["ref"]):
                raise ValueError("Invalid evidence provenance shape: " + gate)
            if type(e["status"]) is not str or e["status"] not in STATES:
                raise ValueError("Invalid evidence status: " + gate)
            if gate in ARTIFACT_GATES and (not digest(e["artifact_digest"]) or not schema(e["schema"])):
                raise ValueError("Invalid artifact/schema binding: " + gate)
            if gate == "risk" and (type(e["risk"]) is not str or e["risk"] not in RISK):
                raise ValueError("Invalid risk classification")
            if gate == "ci" and (type(e["run_id"]) is not int or e["run_id"] <= 0 or
                                 type(e["run_attempt"]) is not int or e["run_attempt"] <= 0 or
                                 not sha(e["tested_commit"]) or type(e["all_jobs_success"]) is not bool):
                raise ValueError("Invalid CI run binding")
            receipt = e["ref"]
            if e["commit"] != c["commit"]:
                reason = "STALE_CANDIDATE"
            elif gate in ARTIFACT_GATES and (e["artifact_digest"] != c["artifact_digest"] or e["schema"] != c["schema"]):
                reason = "ARTIFACT_OR_SCHEMA_MISMATCH"
            elif gate == "ci" and e["tested_commit"] != c["commit"]:
                reason = "TESTED_SHA_MISMATCH"
            elif gate == "ci" and e["status"] == "pass" and not e["all_jobs_success"]:
                reason = "INCOMPLETE_OR_FAILED_CI"
                state = "fail"
            elif gate == "risk" and e["risk"] == "UNCLASSIFIED":
                reason = "RISK_UNCLASSIFIED"
            else:
                state = e["status"]
                reason = "CLAIMED_PASS" if state == "pass" else "REPORTED_" + state.upper()
        rows.append({"gate": gate, "status": state, "reason": reason,
                     "source": source, "environment": env, "owner": owner,
                     "evidence_ref": receipt})
    by_gate = {row["gate"]: row for row in rows}
    blockers = [row["gate"] + ":" + row["reason"] for row in rows
                if row["gate"] in PRE_PUBLISH and row["status"] != "pass"]
    if hold_state != "clear":
        blockers.insert(0, "hold:" + ("ACTIVE" if hold_state == "active" else "UNKNOWN"))
    # Post-deploy evidence is separate from release prerequisites.
    for gate in ("publish", "production_smoke"):
        row = by_gate[gate]
        if row["status"] in ("fail", "skipped") or row["reason"] in (
                "STALE_CANDIDATE", "ARTIFACT_OR_SCHEMA_MISMATCH"):
            blockers.append(gate + ":" + row["reason"])
    claimed_publish = by_gate["publish"]["status"] == "pass"
    claimed_smoke = by_gate["production_smoke"]["status"] == "pass"
    if claimed_smoke and not claimed_publish:
        blockers.append("production_smoke:PUBLISH_EVIDENCE_MISSING")
    projected = evaluate({
        "commit": c["commit"],
        "publication_hold": hold_state == "active",
        "checks": {g: by_gate[g]["status"] for g in
                   ("ci", "staging", "migration", "backup_restore", "approval", "production_smoke")},
        "deployed_commit": c["commit"] if claimed_publish else None,
    })
    state = ("HELD" if hold_state == "active" else "BLOCKED" if blockers else
             "LIVE_CLAIMED_UNVERIFIED" if claimed_publish and claimed_smoke else
             "PUBLISH_CLAIMED_SMOKE_PENDING" if claimed_publish else
             "PRECONDITIONS_CLAIMED_PASS")
    return {
        "schema_version": 1, "candidate": c, "hold_state": hold_state,
        "state": state, "offline_status": projected["state"], "gates": rows,
        "blockers": blockers,
        "evidence_trust": "unverified_caller_assertions",
        "release_eligible": False, "deployment_authorized": False, "live_verified": False,
    }


def markdown(report):
    lines = ["# PRP candidate evidence inventory", "",
             "**Offline assertions only. No release approval or LIVE verification.**", "",
             "Candidate: " + report["candidate"]["commit"],
             "State: " + report["state"], "Hold: " + report["hold_state"], "",
             "| Gate | Claimed status | Finding | Owner | Reference |",
             "| --- | --- | --- | --- | --- |"]
    for row in report["gates"]:
        lines.append("| " + " | ".join([row["gate"], row["status"], row["reason"],
                         row["owner"], row["evidence_ref"] or "-"]) + " |")
    lines += ["", "## Blockers", ""] + (["- " + b for b in report["blockers"]] or
              ["- No logical blocker in supplied assertions; independent evidence still required."])
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--json", required=True, type=Path)
    p.add_argument("--markdown", required=True, type=Path)
    args = p.parse_args()
    if len({x.resolve() for x in (args.input, args.json, args.markdown)}) != 3:
        raise ValueError("Input and output paths must be distinct")
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    report = inventory(json.loads(args.input.read_text(encoding="utf-8"),
                                  object_pairs_hook=no_duplicates))
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
