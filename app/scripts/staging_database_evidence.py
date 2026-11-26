"""Offline migration, restore and risk assertion review. Never executes SQL or releases."""
from release_evidence import exact, sha, digest, schema, REPO, RISK
from staging_build_evidence import positive

RISK_FLAGS = {"irreversible_migration", "oauth_scope_change", "credential_change",
              "permission_change"}
SPECIALISTS = {"database", "security"}
STATUS = {"pass", "fail", "pending", "skipped"}
# Provisional synthetic review window, not an approved operational retention policy.
MAX_AGE = 86400


def _versions(rows):
    if (type(rows) is not list or len(rows) > 1000 or
            any(type(row) is not dict for row in rows)):
        raise ValueError("Invalid migration list")
    for row in rows:
        exact(row, {"version", "sql_digest"}, "migration version")
        if not schema(row["version"]) or not digest(row["sql_digest"]):
            raise ValueError("Invalid migration version")
    return [row["version"] for row in rows]


def _binding(receipt):
    if (not sha(receipt["commit"]) or not digest(receipt["artifact_digest"]) or
            not schema(receipt["schema"])):
        raise ValueError("Invalid database evidence binding")
    return tuple(receipt[k] for k in ("commit", "artifact_digest", "schema"))


def assess_database(candidate, snapshot, now):
    exact(candidate, {"repository", "commit", "artifact_digest", "schema"}, "candidate")
    if candidate["repository"] != REPO or not positive(now):
        raise ValueError("Invalid database review context")
    binding = _binding(candidate)
    exact(snapshot, {"environment", "baseline_schema", "baseline_history", "baseline_data_digest",
                     "source_instance", "policy_digest", "expected_migrations",
                     "migration", "backup", "restore", "risk"}, "database snapshot")
    if (snapshot["environment"] != "prp-unified-396" or
            not schema(snapshot["baseline_schema"]) or
            not all(digest(snapshot[k]) for k in ("baseline_history", "baseline_data_digest",
                                                   "source_instance", "policy_digest"))):
        raise ValueError("Invalid database baseline")
    baseline = snapshot["baseline_schema"]
    target = candidate["schema"]
    expected = snapshot["expected_migrations"]
    versions = _versions(expected)
    groups = {"migration": [], "backup_restore": [], "risk": []}
    mg, br, rk = (groups[k] for k in ("migration", "backup_restore", "risk"))
    if target < baseline or versions != list(range(baseline + 1, target + 1)):
        mg.append("MIGRATION_PLAN_VERSION_GAP_OR_DOWNGRADE")
    m, b, r, risk = (snapshot[k] for k in ("migration", "backup", "restore", "risk"))
    def fresh(t):
        return positive(t) and 0 <= now - t <= MAX_AGE
    if m is None:
        mg.append("MIGRATION_RECEIPT_MISSING")
    else:
        exact(m, {"commit", "artifact_digest", "schema", "policy_digest", "source_instance",
                  "before_schema", "before_history", "after_history", "applied", "failed_count",
                  "started_at", "finished_at", "validation"}, "migration receipt")
        actual = _versions(m["applied"])
        if (not all(digest(m[k]) for k in ("policy_digest", "source_instance", "before_history",
                                           "after_history")) or not schema(m["before_schema"]) or
                type(m["failed_count"]) is not int or m["failed_count"] < 0 or
                not positive(m["started_at"]) or not positive(m["finished_at"]) or
                type(m["validation"]) is not str or m["validation"] not in STATUS):
            raise ValueError("Invalid migration receipt")
        if _binding(m) != binding or m["source_instance"] != snapshot["source_instance"]:
            mg.append("MIGRATION_CANDIDATE_OR_INSTANCE_MISMATCH")
        if (m["before_schema"], m["before_history"], m["policy_digest"]) != (
                baseline, snapshot["baseline_history"], snapshot["policy_digest"]):
            mg.append("MIGRATION_BASELINE_OR_POLICY_MISMATCH")
        if actual != versions or m["applied"] != expected:
            mg.append("MIGRATION_VERSION_OR_CHECKSUM_MISMATCH")
        if ((target == baseline) != (m["after_history"] == m["before_history"])):
            mg.append("MIGRATION_HISTORY_TRANSITION_MISMATCH")
        if m["failed_count"] or m["validation"] != "pass":
            mg.append("FLYWAY_VALIDATION_NOT_PASS")
        if not fresh(m["started_at"]) or not fresh(m["finished_at"]) or m["started_at"] > m["finished_at"]:
            mg.append("MIGRATION_TIME_INVALID")
    if b is None:
        br.append("BACKUP_RECEIPT_MISSING")
    else:
        exact(b, {"commit", "artifact_digest", "schema", "source_instance", "baseline_schema",
                  "history_digest", "data_digest", "backup_digest", "created_at",
                  "checksum_review"}, "backup receipt")
        if (not all(digest(b[k]) for k in ("source_instance", "history_digest", "data_digest",
                                           "backup_digest")) or not schema(b["baseline_schema"]) or
                not positive(b["created_at"]) or type(b["checksum_review"]) is not str or
                b["checksum_review"] not in STATUS):
            raise ValueError("Invalid backup receipt")
        if _binding(b) != binding or (b["source_instance"], b["baseline_schema"],
                b["history_digest"], b["data_digest"]) != (snapshot["source_instance"], baseline,
                snapshot["baseline_history"], snapshot["baseline_data_digest"]):
            br.append("BACKUP_BASELINE_OR_CANDIDATE_MISMATCH")
        if b["checksum_review"] != "pass":
            br.append("BACKUP_CHECKSUM_NOT_PASS")
        if not fresh(b["created_at"]) or (m is not None and b["created_at"] >= m["started_at"]):
            br.append("BACKUP_NOT_FRESH_PRE_MIGRATION")
    if r is None:
        br.append("RESTORE_RECEIPT_MISSING")
    else:
        exact(r, {"commit", "artifact_digest", "schema", "backup_digest", "target_instance",
                  "restored_schema", "history_digest", "data_digest", "started_at",
                  "finished_at", "validation", "isolated", "rehearsal"}, "restore receipt")
        if (not all(digest(r[k]) for k in ("backup_digest", "target_instance", "history_digest",
                                           "data_digest")) or not schema(r["restored_schema"]) or
                not positive(r["started_at"]) or not positive(r["finished_at"]) or
                type(r["validation"]) is not str or r["validation"] not in STATUS or
                type(r["isolated"]) is not bool):
            raise ValueError("Invalid restore receipt")
        if _binding(r) != binding or b is None or r["backup_digest"] != b["backup_digest"]:
            br.append("RESTORE_BACKUP_OR_CANDIDATE_MISMATCH")
        if not r["isolated"] or r["target_instance"] == snapshot["source_instance"]:
            br.append("RESTORE_TARGET_NOT_ISOLATED")
        if (r["restored_schema"], r["history_digest"], r["data_digest"]) != (
                baseline, snapshot["baseline_history"], snapshot["baseline_data_digest"]):
            br.append("RESTORE_BASELINE_INTEGRITY_MISMATCH")
        if r["validation"] != "pass":
            br.append("RESTORE_VALIDATION_NOT_PASS")
        if (not fresh(r["started_at"]) or not fresh(r["finished_at"]) or
                r["started_at"] > r["finished_at"] or b is None or r["started_at"] < b["created_at"]):
            br.append("RESTORE_TIME_INVALID")
        # The whole isolated rehearsal (restore, target migration and preservation
        # checks) must finish strictly before the candidate database migration.
        if m is None or r["finished_at"] >= m["started_at"]:
            br.append("RESTORE_REHEARSAL_NOT_BEFORE_MIGRATION")
        rehearsal = r["rehearsal"]
        if rehearsal is None:
            br.append("TARGET_MIGRATION_REHEARSAL_MISSING")
        else:
            exact(rehearsal, {"target_schema", "policy_digest", "applied", "failed_count",
                              "validation", "historical_rows", "historical_ddl",
                              "new_tables"}, "isolated migration rehearsal")
            _versions(rehearsal["applied"])
            if (not schema(rehearsal["target_schema"]) or not digest(rehearsal["policy_digest"]) or
                    type(rehearsal["failed_count"]) is not int or rehearsal["failed_count"] < 0 or
                    any(type(rehearsal[k]) is not str or rehearsal[k] not in STATUS
                        for k in ("validation", "historical_rows", "historical_ddl", "new_tables"))):
                raise ValueError("Invalid isolated migration rehearsal")
            if (rehearsal["target_schema"] != target or
                    rehearsal["policy_digest"] != snapshot["policy_digest"] or
                    rehearsal["applied"] != expected):
                br.append("REHEARSAL_TARGET_OR_POLICY_MISMATCH")
            if rehearsal["failed_count"] or any(rehearsal[k] != "pass" for k in
                    ("validation", "historical_rows", "historical_ddl", "new_tables")):
                br.append("REHEARSAL_PRESERVATION_NOT_PASS")
    classification = "UNCLASSIFIED"
    if risk is None:
        rk.append("RISK_RECEIPT_MISSING")
    else:
        exact(risk, {"commit", "artifact_digest", "schema", "classification", "flags",
                     "reviewed_at", "specialist_reviews"}, "risk receipt")
        flags, specialists = risk["flags"], risk["specialist_reviews"]
        exact(flags, RISK_FLAGS, "risk flags")
        exact(specialists, SPECIALISTS, "specialist reviews")
        classification = risk["classification"]
        if (type(classification) is not str or classification not in RISK or
                any(type(v) is not bool for v in flags.values()) or
                any(type(v) is not str or v not in STATUS for v in specialists.values()) or
                not positive(risk["reviewed_at"])):
            raise ValueError("Invalid risk receipt")
        if _binding(risk) != binding or not fresh(risk["reviewed_at"]):
            rk.append("RISK_CANDIDATE_OR_TIME_MISMATCH")
        high = baseline != target or any(flags.values())
        if classification == "UNCLASSIFIED" or (high and classification != "HIGH_REVIEW"):
            rk.append("RISK_UNCLASSIFIED_OR_UNDERRATED")
        if (high or classification == "HIGH_REVIEW") and any(v != "pass" for v in specialists.values()):
            rk.append("HIGH_RISK_SPECIALIST_REVIEW_INCOMPLETE")
    mandatory = {"migration": "INDEPENDENT_MIGRATION_PROOF_NOT_ESTABLISHED",
                 "backup_restore": "INDEPENDENT_RESTORE_PROOF_NOT_ESTABLISHED",
                 "risk": "INDEPENDENT_RISK_REVIEW_NOT_ESTABLISHED"}
    return {"state": "BLOCKED", "source": "unverified_caller_assertions",
            "baseline_schema_claimed": baseline, "target_schema_claimed": target,
            "migration_versions_claimed": versions, "risk_classification_claimed": classification,
            "migration_finished_at_claimed": m["finished_at"] if m is not None else None,
            "correlation_claimed": {k: not v for k, v in groups.items()},
            "findings": {k: sorted(set(v)) + [mandatory[k]] for k, v in groups.items()},
            "migration_verified": False, "restore_verified": False, "risk_verified": False,
            "deployment_authorized": False, "production_authorized": False, "live_verified": False}
