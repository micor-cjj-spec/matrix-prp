"""Strict client contract for a future, independently approved root policy proof.

No collector is installed by this module. Missing live proof always blocks.
"""
from datetime import datetime, timezone
import re

BASELINE_FIELDS = {
    "gateway_sha256", "authorized_keys_sha256", "effective_sshd_sha256",
    "policy_files_sha256", "attestor_sha256", "deployment_key_fingerprint",
    "subsystem_command", "forced_command", "behavior",
}
PROOF_FIELDS = {"schema_version", "challenge", "observed_utc", "baseline",
                "connection_bound", "loaded_policy_verified", "trusted_paths"}
SUBSYSTEM = "/usr/lib/openssh/sftp-server"
GATEWAY = "/usr/local/bin/prp-deploy-gateway"
BEHAVIOR = "openssh-10.0-subsystem-stderr-ignore"


class PolicyError(ValueError):
    pass


def baseline_from(manifest):
    baseline = manifest.get("approved_ssh_policy")
    if not isinstance(baseline, dict) or set(baseline) != BASELINE_FIELDS:
        raise PolicyError("SSH_POLICY_BASELINE_MISSING")
    for name, value in baseline.items():
        if name.endswith("_sha256") and (not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None):
            raise PolicyError("SSH_POLICY_BASELINE_INVALID")
    fingerprint = baseline["deployment_key_fingerprint"]
    if (not isinstance(fingerprint, str) or re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint) is None
            or baseline["subsystem_command"] != SUBSYSTEM or baseline["forced_command"] != GATEWAY
            or baseline["behavior"] != BEHAVIOR):
        raise PolicyError("SSH_POLICY_BASELINE_INVALID")
    return baseline


def verify_proof(manifest, proof, challenge, now=None):
    expected = baseline_from(manifest)
    if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS:
        raise PolicyError("SSH_POLICY_PROOF_UNAVAILABLE")
    if type(proof["schema_version"]) is not int or proof["schema_version"] != 1:
        raise PolicyError("SSH_POLICY_PROOF_INVALID")
    if proof["challenge"] != challenge.hex():
        raise PolicyError("SSH_POLICY_CHALLENGE_MISMATCH")
    if proof["baseline"] != expected:
        raise PolicyError("SSH_POLICY_DRIFT")
    if any(proof[k] is not True for k in ["connection_bound", "loaded_policy_verified", "trusted_paths"]):
        raise PolicyError("SSH_POLICY_RUNTIME_UNVERIFIED")
    try:
        stamp = proof["observed_utc"]
        if not isinstance(stamp, str) or not stamp.endswith("Z"):
            raise ValueError()
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds()
        if not -5 <= age <= 30:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise PolicyError("SSH_POLICY_PROOF_STALE") from None
    return expected


def checked_exchange(result):
    """A missing field, contradictory result or protocol output never passes."""
    if not isinstance(result, dict):
        raise PolicyError("SFTP_EVIDENCE_INCOMPLETE")
    if result.get("version_response") is True or result.get("sftp_accessible") is True:
        raise PolicyError("SFTP_ACCESSIBLE")
    if (result.get("version_response") is not False or result.get("sftp_accessible") is not False
            or result.get("sftp_version", "missing") is not None):
        raise PolicyError("SFTP_EVIDENCE_INCOMPLETE")
    if type(result.get("stdout_bytes")) is not int or result.get("stdout_bytes") != 0 or result.get("stdout_empty") is not True:
        raise PolicyError("SFTP_UNEXPECTED_OUTPUT")
    if (type(result.get("stderr_bytes")) is not int or not 0 <= result["stderr_bytes"] <= 65536
            or result.get("stderr_empty") is not (result["stderr_bytes"] == 0)):
        raise PolicyError("SFTP_EVIDENCE_INCOMPLETE")
    for field in ["authentication_error", "host_key_error", "network_error", "timed_out", "output_limited"]:
        if result.get(field) is not False:
            raise PolicyError("SFTP_" + field.upper())
    if (result.get("init_sent") is not True or result.get("stdin_held_open") is not True
            or result.get("authenticated_publickey") is not True
            or type(result.get("exit_code")) is not int):
        raise PolicyError("SFTP_EVIDENCE_INCOMPLETE")


def correlate(exec_result, subsystem_result):
    checked_exchange(exec_result)
    if (exec_result["exit_code"] != 2 or exec_result.get("gateway_denial") is not True
            or exec_result.get("category") != "GATEWAY_REJECTED"):
        raise PolicyError("SFTP_EXACT_COMMAND_NOT_DENIED")
    checked_exchange(subsystem_result)
    # Complete fresh server proof is checked separately BEFORE these probes.
    if (subsystem_result["exit_code"] != 2 or subsystem_result.get("subsystem_request_accepted") is not True
            or subsystem_result.get("category") not in {"GATEWAY_REJECTED", "SUBSYSTEM_EXITED_WITHOUT_VERSION"}
            or subsystem_result.get("subsystem_request_failed") is not False):
        raise PolicyError("SFTP_SUBSYSTEM_RESULT_UNRECOGNIZED")
    if ((subsystem_result["category"] == "GATEWAY_REJECTED") != (subsystem_result.get("gateway_denial") is True)):
        raise PolicyError("SFTP_SUBSYSTEM_RESULT_UNRECOGNIZED")
    return "SFTP_DENIED_BY_FORCED_GATEWAY"
