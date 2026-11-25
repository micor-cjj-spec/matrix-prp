"""P3.7.2 offline signed receipt contract. No collector, key provisioning or release authority."""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from release_evidence import exact, sha, digest, schema, REPO
from staging_build_evidence import positive
from staging_database_evidence import assess_database
from staging_runtime_evidence import assess_runtime

ENV = "prp-unified-396"
DOMAIN = "PRP_P372_SIGNED_RECEIPT_V1"
MAX_RECEIPT_TTL = 900  # Provisional test contract; not an operational SLA.
MAX_PAYLOAD_BYTES = 262144
MAX_DEPTH = 12
MAX_ITEMS = 2000

RECEIPT_ROLES = {
    "runtime_observation": "stage_operator",
    "database_migration": "database_reviewer",
    "backup_restore": "backup_restore_reviewer",
    "risk_review": "security_reviewer",
    "health_v2_uat": "health_owner",
    "ui_v2_uat": "ui_owner",
}
HEALTH_CASES = {
    "meal_create_read_update_delete", "nutrition_analysis_consistency",
    "owner_isolation_read_denied", "owner_isolation_write_denied",
    "unknown_macros_preserved_null", "cleanup_verified",
}
UI_CASES = {
    "desktop_four_tab_navigation", "apps_center", "ordinary_user_permissions",
    "iphone_safari", "chat_input_keyboard", "pwa_install_launch",
}
# Deliberately empty. Real trust anchors require a separately reviewed,
# out-of-band provisioning decision; no private key or production key is stored here.
TRUSTED_SIGNERS = {}


def _json_shape(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Receipt JSON nesting exceeds limit")
    if value is None or type(value) in (bool, int):
        if type(value) is int and abs(value) > 2**53 - 1:
            raise ValueError("Receipt integer exceeds safe range")
        return
    if type(value) is str:
        if len(value) > 4096 or any(ord(ch) < 32 for ch in value):
            raise ValueError("Receipt string is oversized or contains control characters")
        return
    if type(value) is list:
        if len(value) > MAX_ITEMS:
            raise ValueError("Receipt list exceeds limit")
        for item in value:
            _json_shape(item, depth + 1)
        return
    if type(value) is dict:
        if len(value) > MAX_ITEMS:
            raise ValueError("Receipt object exceeds limit")
        for key, item in value.items():
            if type(key) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key) is None:
                raise ValueError("Receipt object has a noncanonical key")
            _json_shape(item, depth + 1)
        return
    raise ValueError("Receipt contains a non-JSON or unsupported value")


def canonical_bytes(value):
    _json_shape(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Receipt cannot be canonicalized") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("Canonical receipt exceeds size limit")
    return encoded


def sha256(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def envelope_digest(envelope):
    return sha256(canonical_bytes(envelope))


def _candidate(value):
    exact(value, {"repository", "commit", "artifact_digest", "schema"}, "candidate")
    if (value["repository"] != REPO or not sha(value["commit"]) or
            not digest(value["artifact_digest"]) or not schema(value["schema"])):
        raise ValueError("Invalid receipt candidate")
    return value


def database_context_digest(candidate, context):
    exact(context, {"baseline_schema", "baseline_history", "baseline_data_digest",
                    "source_instance", "policy_digest", "expected_migrations"}, "database context")
    if (not schema(context["baseline_schema"]) or
            not all(digest(context[k]) for k in
                    ("baseline_history", "baseline_data_digest", "source_instance", "policy_digest")) or
            type(context["expected_migrations"]) is not list or len(context["expected_migrations"]) > 1000):
        raise ValueError("Invalid database context")
    for row in context["expected_migrations"]:
        exact(row, {"version", "sql_digest"}, "expected migration")
        if not schema(row["version"]) or not digest(row["sql_digest"]):
            raise ValueError("Invalid expected migration")
    return sha256(canonical_bytes({"domain": "PRP_P372_DATABASE_CONTEXT_V1",
                                   "candidate": candidate, "context": context}))


def _public_key_der(pem):
    if (type(pem) is not str or len(pem) > 1024 or
            not pem.startswith("-----BEGIN PUBLIC KEY-----") or
            "PRIVATE KEY" in pem or not pem.rstrip().endswith("-----END PUBLIC KEY-----")):
        raise ValueError("Only bounded public-key PEM is accepted")
    body = pem.replace("-----BEGIN PUBLIC KEY-----", "").replace(
        "-----END PUBLIC KEY-----", "")
    try:
        der = base64.b64decode("".join(body.split()), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid public-key PEM encoding") from exc
    # SubjectPublicKeyInfo prefix for Ed25519; reject RSA/ECDSA and private keys.
    if len(der) != 44 or not der.startswith(bytes.fromhex("302a300506032b6570032100")):
        raise ValueError("Only Ed25519 SubjectPublicKeyInfo keys are accepted")
    return der


def _signing_message(envelope):
    unsigned = {key: envelope[key] for key in
                ("schema_version", "receipt_type", "environment", "key_id",
                 "issued_at", "expires_at", "nonce", "payload")}
    return canonical_bytes({"domain": DOMAIN, "receipt": unsigned})


def _verify_ed25519(public_key_pem, message, signature):
    try:
        _public_key_der(public_key_pem)
    except ValueError:
        return False, "INVALID_TRUSTED_PUBLIC_KEY"
    openssl = shutil.which("openssl")
    if not openssl:
        return False, "OPENSSL_UNAVAILABLE"
    try:
        with tempfile.TemporaryDirectory(prefix="prp-p372-") as directory:
            root = Path(directory)
            os.chmod(root, 0o700)
            key_file, message_file, signature_file = (
                root / "public.pem", root / "message.bin", root / "signature.bin")
            key_file.write_text(public_key_pem, encoding="ascii")
            message_file.write_bytes(message)
            signature_file.write_bytes(signature)
            for path in (key_file, message_file, signature_file):
                os.chmod(path, 0o600)
            result = subprocess.run(
                [openssl, "pkeyutl", "-verify", "-pubin", "-inkey", str(key_file),
                 "-rawin", "-in", str(message_file), "-sigfile", str(signature_file)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=5)
            return (result.returncode == 0,
                    "SIGNATURE_VALID" if result.returncode == 0 else "SIGNATURE_INVALID")
    except (OSError, subprocess.TimeoutExpired):
        return False, "SIGNATURE_VERIFIER_UNAVAILABLE"


def _verify_envelope(envelope, expected_type, expected_role, now, trust_store):
    exact(envelope, {"schema_version", "receipt_type", "environment", "key_id",
                     "issued_at", "expires_at", "nonce", "payload", "signature"}, "signed envelope")
    if (type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1 or
            envelope["receipt_type"] != expected_type or envelope["environment"] != ENV or
            type(envelope["key_id"]) is not str or
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", envelope["key_id"]) is None or
            type(envelope["issued_at"]) is not int or type(envelope["expires_at"]) is not int or
            not positive(envelope["issued_at"]) or not positive(envelope["expires_at"]) or
            type(now) is not int or not positive(now) or
            type(envelope["nonce"]) is not str or
            re.fullmatch(r"[A-Za-z0-9_-]{16,96}", envelope["nonce"]) is None or
            type(envelope["payload"]) is not dict or
            type(envelope["signature"]) is not str or len(envelope["signature"]) > 128):
        raise ValueError("Malformed signed receipt envelope")
    if (envelope["expires_at"] <= envelope["issued_at"] or
            envelope["expires_at"] - envelope["issued_at"] > MAX_RECEIPT_TTL or
            envelope["issued_at"] > now or envelope["expires_at"] < now):
        return False, "RECEIPT_EXPIRED_FUTURE_OR_TTL_INVALID"
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
    except (ValueError, base64.binascii.Error):
        return False, "SIGNATURE_ENCODING_INVALID"
    if len(signature) != 64:
        return False, "SIGNATURE_LENGTH_INVALID"
    if not trust_store:
        return False, "TRUST_STORE_EMPTY"
    signer = trust_store.get(envelope["key_id"])
    if signer is None:
        return False, "SIGNER_KEY_NOT_TRUSTED"
    exact(signer, {"role", "environment", "public_key_pem", "not_before", "not_after"},
          "trusted signer")
    if (signer["role"] != expected_role or signer["environment"] != ENV or
            type(signer["not_before"]) is not int or type(signer["not_after"]) is not int or
            not positive(signer["not_before"]) or signer["not_after"] <= signer["not_before"] or
            not signer["not_before"] <= envelope["issued_at"] <= envelope["expires_at"] <= signer["not_after"]):
        return False, "SIGNER_ROLE_ENVIRONMENT_OR_VALIDITY_MISMATCH"
    try:
        message = _signing_message(envelope)
    except ValueError:
        return False, "SIGNING_PAYLOAD_INVALID"
    return _verify_ed25519(signer["public_key_pem"], message, signature)


def _validate_module_uat(module, payload, candidate, runtime_hash, db_context_hash, now):
    exact(payload, {"module", "candidate", "environment", "started_at", "finished_at",
                    "runtime_receipt_digest", "database_context_digest", "cases",
                    "evidence_digests", "identity", "cleanup", "device_observations"},
          module + " UAT payload")
    _candidate(payload["candidate"])
    if (payload["module"] != module or payload["candidate"] != candidate or
            payload["environment"] != ENV or
            payload["runtime_receipt_digest"] != runtime_hash or
            payload["database_context_digest"] != db_context_hash):
        return False, ["UAT_CANDIDATE_RUNTIME_OR_DATABASE_BINDING_MISMATCH"]
    start, finish = payload["started_at"], payload["finished_at"]
    if (type(start) is not int or type(finish) is not int or not positive(start) or
            not positive(finish) or start > finish or finish > now):
        raise ValueError("Invalid module UAT time window")
    expected = HEALTH_CASES if module == "health_v2" else UI_CASES
    cases, evidence = payload["cases"], payload["evidence_digests"]
    exact(cases, expected, module + " cases")
    exact(evidence, expected, module + " evidence digests")
    if any(type(v) is not str or v not in ("pass", "fail", "pending", "skipped")
           for v in cases.values()) or not all(digest(v) for v in evidence.values()):
        raise ValueError("Invalid module UAT case or evidence digest")
    findings = []
    if any(value != "pass" for value in cases.values()):
        findings.append("MODULE_UAT_CASES_INCOMPLETE")
    if module == "health_v2":
        exact(payload["identity"], {"owner_a_subject_digest", "owner_b_subject_digest",
              "owner_a_enabled", "owner_b_enabled", "owner_a_admin", "owner_b_admin",
              "owner_a_mcp_grants", "owner_b_mcp_grants"}, "Health identities")
        identity = payload["identity"]
        if (not digest(identity["owner_a_subject_digest"]) or
                not digest(identity["owner_b_subject_digest"]) or
                identity["owner_a_subject_digest"] == identity["owner_b_subject_digest"] or
                identity["owner_a_enabled"] is not True or identity["owner_b_enabled"] is not True or
                identity["owner_a_admin"] is not False or identity["owner_b_admin"] is not False or
                type(identity["owner_a_mcp_grants"]) is not int or identity["owner_a_mcp_grants"] != 0 or
                type(identity["owner_b_mcp_grants"]) is not int or identity["owner_b_mcp_grants"] != 0):
            findings.append("HEALTH_TWO_OWNER_IDENTITY_OR_PRIVILEGE_CHECK_FAILED")
        exact(payload["cleanup"], {"scope", "created_count", "deleted_count",
              "remaining_count", "unsupported_resource_writes"}, "Health cleanup")
        cleanup = payload["cleanup"]
        if (cleanup["scope"] != "owner_created_meals_only" or
                any(type(cleanup[k]) is not int or cleanup[k] < 0 for k in
                    ("created_count", "deleted_count", "remaining_count", "unsupported_resource_writes")) or
                cleanup["created_count"] != cleanup["deleted_count"] or
                cleanup["remaining_count"] != 0 or cleanup["unsupported_resource_writes"] != 0):
            findings.append("HEALTH_CLEANUP_NOT_PROVEN")
        if payload["device_observations"] is not None:
            raise ValueError("Health UAT must not contain unrelated device observations")
    else:
        exact(payload["identity"], {"ordinary_user_subject_digest", "ordinary_user_enabled",
              "ordinary_user_admin", "mcp_grant_rows"}, "UI identity")
        identity = payload["identity"]
        if (not digest(identity["ordinary_user_subject_digest"]) or
                identity["ordinary_user_enabled"] is not True or
                identity["ordinary_user_admin"] is not False or
                type(identity["mcp_grant_rows"]) is not int or identity["mcp_grant_rows"] != 0):
            findings.append("UI_ORDINARY_IDENTITY_OR_PRIVILEGE_CHECK_FAILED")
        if payload["cleanup"] is not None:
            raise ValueError("UI UAT must not claim Health data cleanup")
        devices = payload["device_observations"]
        if type(devices) is not list or len(devices) != 2:
            raise ValueError("UI UAT requires desktop and iPhone device observations")
        found = set()
        for device in devices:
            exact(device, {"device", "os_version", "browser", "browser_version",
                           "viewport", "observed_at", "evidence_digest"}, "UI device observation")
            if (device["device"] not in ("desktop", "iphone") or
                    any(type(device[k]) is not str or not device[k] or len(device[k]) > 80
                        for k in ("os_version", "browser", "browser_version", "viewport")) or
                    type(device["observed_at"]) is not int or
                    not start <= device["observed_at"] <= finish or
                    not digest(device["evidence_digest"])):
                raise ValueError("Invalid UI device evidence")
            if device["device"] in found:
                raise ValueError("Duplicate UI device observation")
            found.add(device["device"])
            if device["device"] == "iphone" and device["browser"].lower() != "safari":
                findings.append("IPHONE_SAFARI_EVIDENCE_MISMATCH")
        if found != {"desktop", "iphone"}:
            raise ValueError("UI device inventory incomplete")
    # Digests are references only; no screenshot or raw business bytes are fetched here.
    findings.append("MODULE_UAT_EVIDENCE_BYTES_NOT_VERIFIED")
    return not any(f != "MODULE_UAT_EVIDENCE_BYTES_NOT_VERIFIED" for f in findings), findings


def _assess_bundle(candidate, projection, bundle, now, trust_store):
    _candidate(candidate)
    exact(projection, {"schemaVersion", "source", "state", "candidate", "bindingDigest",
                       "readSmoke", "apiPassed", "checksExecuted", "identityCorrelation",
                       "findings", "deploymentAuthorized", "productionAuthorized",
                       "releaseEligible", "liveVerified"}, "P3.7.1 projection")
    exact(bundle, {"runtime_observation", "database_migration", "backup_restore",
                   "risk_review", "module_uat"}, "P3.7.2 receipt bundle")
    if (projection["schemaVersion"] != 1 or projection["candidate"] != {
            "commit": candidate["commit"], "artifactDigest": candidate["artifact_digest"],
            "schema": candidate["schema"]} or not digest(projection["bindingDigest"]) or
            projection["source"] != "offline_unverified_staging_review" or
            projection["state"] != "BLOCKED" or
            projection["deploymentAuthorized"] is not False or
            projection["productionAuthorized"] is not False or
            projection["releaseEligible"] is not False or projection["liveVerified"] is not False):
        raise ValueError("Invalid P3.7.1 projection binding")
    module_envelopes = bundle["module_uat"]
    exact(module_envelopes, {"health_v2", "ui_v2"}, "module UAT receipts")
    envelopes = {
        "runtime_observation": bundle["runtime_observation"],
        "database_migration": bundle["database_migration"],
        "backup_restore": bundle["backup_restore"],
        "risk_review": bundle["risk_review"],
        "health_v2_uat": module_envelopes["health_v2"],
        "ui_v2_uat": module_envelopes["ui_v2"],
    }
    findings, signature_checks, nonces, key_ids = [], {}, [], []
    for receipt_type, envelope in envelopes.items():
        if envelope is None:
            signature_checks[receipt_type] = False
            findings.append(receipt_type.upper() + "_MISSING")
            continue
        valid, reason = _verify_envelope(
            envelope, receipt_type, RECEIPT_ROLES[receipt_type], now, trust_store)
        signature_checks[receipt_type] = valid
        if reason != "SIGNATURE_VALID":
            findings.append(receipt_type.upper() + ":" + reason)
        nonces.append(envelope["nonce"])
        key_ids.append(envelope["key_id"])
    if len(nonces) != len(set(nonces)):
        findings.append("RECEIPT_NONCE_REPLAY_WITHIN_BUNDLE")
    if len(key_ids) != len(set(key_ids)):
        findings.append("SIGNER_KEY_REUSED_ACROSS_ROLES")
    if not trust_store:
        findings.append("TRUST_ANCHOR_NOT_PROVISIONED")
    elif not all(signature_checks.values()):
        findings.append("ONE_OR_MORE_RECEIPT_SIGNATURES_INVALID")

    runtime_env = envelopes["runtime_observation"]
    db_env = envelopes["database_migration"]
    backup_env = envelopes["backup_restore"]
    risk_env = envelopes["risk_review"]
    if any(value is None for value in (runtime_env, db_env, backup_env, risk_env)):
        return _blocked_report(findings, signature_checks, None, None, {})
    for envelope in (runtime_env, db_env, backup_env, risk_env):
        if envelope["environment"] != ENV:
            raise ValueError("Receipt environment mismatch")
    rp = runtime_env["payload"]
    exact(rp, {"candidate", "environment", "projection_digest", "snapshot",
               "rollback_readiness"}, "runtime payload")
    if (_candidate(rp["candidate"]) != candidate or rp["environment"] != ENV or
            rp["projection_digest"] != sha256(canonical_bytes(projection))):
        findings.append("RUNTIME_CANDIDATE_OR_PROJECTION_MISMATCH")
    exact(rp["rollback_readiness"], {"status", "plan_digest"}, "rollback readiness")
    if rp["rollback_readiness"]["status"] != "pass" or not digest(rp["rollback_readiness"]["plan_digest"]):
        findings.append("ROLLBACK_READINESS_NOT_PASS")
    snapshot = rp["snapshot"]
    exact(snapshot, {"environment", "expected_images", "before", "after", "uat"}, "runtime snapshot")
    if snapshot["environment"] != ENV or snapshot["uat"] is not None:
        raise ValueError("Runtime receipt must be stage-only and leave module UAT separate")
    if snapshot["after"] is not None and runtime_env["issued_at"] < snapshot["after"]["observed_at"]:
        findings.append("RUNTIME_RECEIPT_SIGNED_BEFORE_OBSERVATION")

    mp = db_env["payload"]
    exact(mp, {"candidate", "environment", "context", "migration_mode", "migration"}, "database migration payload")
    bp = backup_env["payload"]
    exact(bp, {"candidate", "environment", "context_digest", "backup", "restore"}, "backup restore payload")
    kp = risk_env["payload"]
    exact(kp, {"candidate", "environment", "context_digest", "risk"}, "risk review payload")
    context = mp["context"]
    context_hash = database_context_digest(candidate, context)
    if (_candidate(mp["candidate"]) != candidate or mp["environment"] != ENV or
            _candidate(bp["candidate"]) != candidate or bp["environment"] != ENV or
            _candidate(kp["candidate"]) != candidate or kp["environment"] != ENV or
            bp["context_digest"] != context_hash or kp["context_digest"] != context_hash):
        findings.append("DATABASE_CONTEXT_OR_CANDIDATE_MISMATCH")
    if mp["migration_mode"] not in ("apply_migrations", "no_schema_change"):
        raise ValueError("Unsupported migration mode")
    expected = context["expected_migrations"]
    baseline, target = context["baseline_schema"], candidate["schema"]
    if mp["migration_mode"] == "no_schema_change":
        if (baseline != target or expected or mp["migration"] is None or
                mp["migration"].get("before_schema") != baseline or
                mp["migration"].get("after_history") != context["baseline_history"] or
                mp["migration"].get("applied") != []):
            findings.append("NO_MIGRATION_MODE_CONFLICT")
    elif baseline >= target or [row["version"] for row in expected] != list(range(baseline + 1, target + 1)):
        findings.append("MIGRATION_MODE_OR_VERSION_SEQUENCE_CONFLICT")
    db_snapshot = {
        "environment": ENV, **context, "migration": mp["migration"],
        "backup": bp["backup"], "restore": bp["restore"], "risk": kp["risk"],
    }
    db_report = assess_database(candidate, db_snapshot, now)
    migration = mp["migration"]
    backup = bp["backup"]
    restore = bp["restore"]
    risk = kp["risk"]
    if migration is not None and db_env["issued_at"] < migration["finished_at"]:
        findings.append("DATABASE_RECEIPT_SIGNED_BEFORE_MIGRATION_FINISHED")
    if restore is not None and backup_env["issued_at"] < restore["finished_at"]:
        findings.append("BACKUP_RESTORE_RECEIPT_SIGNED_BEFORE_RESTORE_FINISHED")
    if backup is not None and backup_env["issued_at"] < backup["created_at"]:
        findings.append("BACKUP_RESTORE_RECEIPT_SIGNED_BEFORE_BACKUP_CREATED")
    if risk is not None and risk_env["issued_at"] < risk["reviewed_at"]:
        findings.append("RISK_RECEIPT_SIGNED_BEFORE_REVIEW")

    health_env, ui_env = module_envelopes["health_v2"], module_envelopes["ui_v2"]
    module_reports = {}
    module_payloads = {}
    runtime_hash = envelope_digest(runtime_env)
    for module, envelope in (("health_v2", health_env), ("ui_v2", ui_env)):
        if envelope is None:
            module_reports[module] = {"claimed": False, "findings": ["MODULE_UAT_MISSING"]}
            continue
        expected_type = module + "_uat"
        if envelope["receipt_type"] != expected_type:
            raise ValueError("Wrong module UAT receipt type")
        payload = envelope["payload"]
        if type(payload) is not dict or type(payload.get("finished_at")) is not int or envelope["issued_at"] < payload["finished_at"]:
            findings.append(module.upper() + "_RECEIPT_SIGNED_BEFORE_UAT_FINISHED")
        valid, module_findings = _validate_module_uat(
            module, payload, candidate, runtime_hash, context_hash, now)
        module_reports[module] = {"claimed": valid, "findings": module_findings}
        module_payloads[module] = payload

    runtime_snapshot = dict(snapshot)
    if set(module_payloads) == {"health_v2", "ui_v2"}:
        h, u = module_payloads["health_v2"], module_payloads["ui_v2"]
        core_cases = {
            "api_read": h["cases"]["meal_create_read_update_delete"],
            "business_write": h["cases"]["meal_create_read_update_delete"],
            "owner_isolation": "pass" if (
                h["cases"]["owner_isolation_read_denied"] == "pass" and
                h["cases"]["owner_isolation_write_denied"] == "pass") else "fail",
            "browser_pwa": "pass" if (
                u["cases"]["iphone_safari"] == "pass" and
                u["cases"]["pwa_install_launch"] == "pass" and
                u["cases"]["desktop_four_tab_navigation"] == "pass") else "fail",
            "rollback_readiness": rp["rollback_readiness"]["status"],
        }
        runtime_snapshot["uat"] = {
            "kind": "stage_business", "commit": candidate["commit"],
            "artifact_digest": candidate["artifact_digest"], "schema": candidate["schema"],
            "started_at": min(h["started_at"], u["started_at"]),
            "finished_at": max(h["finished_at"], u["finished_at"]),
            "smoke_binding_digest": projection["bindingDigest"], "cases": core_cases,
        }
    runtime_report = assess_runtime(candidate, projection, runtime_snapshot, now)
    findings.extend(runtime_report["findings"])
    for group, rows in db_report["findings"].items():
        findings.extend(group.upper() + ":" + row for row in rows)
    for module, report in module_reports.items():
        findings.extend(module.upper() + ":" + item for item in report["findings"])
    return _blocked_report(findings, signature_checks, runtime_report, db_report, module_reports)


def _blocked_report(findings, signature_checks, runtime_report, database_report, module_reports):
    mandatory = [
        "TRUSTED_TRUST_ANCHOR_PROVENANCE_NOT_ESTABLISHED",
        "INDEPENDENT_HOST_ATTESTATION_NOT_ESTABLISHED",
        "TRUSTED_CLOCK_NOT_ESTABLISHED",
        "DURABLE_REPLAY_PROTECTION_NOT_ESTABLISHED",
        "UAT_ARTIFACT_BYTES_NOT_VERIFIED",
        "INDEPENDENT_HUMAN_AUTHORITY_NOT_ESTABLISHED",
    ]
    return {
        "schema_version": 1, "state": "BLOCKED",
        "findings": sorted(set(findings + mandatory)),
        "signature_checks": signature_checks,
        "cryptographic_signatures_valid_against_configured_keys":
            bool(signature_checks) and all(signature_checks.values()),
        "runtime_correlation_claimed": bool(runtime_report and runtime_report.get("runtime_correlation_claimed")),
        "database_correlation_claimed": bool(database_report and
            all(database_report.get("correlation_claimed", {}).values())),
        "module_uat_claimed": {key: value.get("claimed", False)
                               for key, value in module_reports.items()},
        "source_authenticated": False, "trusted_key_provenance_verified": False,
        "independent_host_attestation": False, "trusted_clock": False,
        "durable_replay_protection": False, "business_uat_verified": False,
        "migration_verified": False, "restore_verified": False, "risk_verified": False,
        "current_review_satisfied": False, "release_eligible": False,
        "deployment_authorized": False, "production_authorized": False, "live_verified": False,
    }


def assess_receipt_bundle(candidate, projection, bundle, now):
    """Public path uses only repository-pinned trust configuration, currently empty."""
    return _assess_bundle(candidate, projection, bundle, now, TRUSTED_SIGNERS)
