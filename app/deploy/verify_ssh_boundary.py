#!/usr/bin/env python3
"""Read-only SSH acceptance gate. No remote output or credentials are logged."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import secrets

import probe_sftp_init
import sftp_policy

from render_safe_diagnostic import safe_diagnostic
from verify_controller import verify_response

GATEWAY_DENIAL = b"Allowed: deploy, status, check, rollback RELEASE_ID"
MAX_OUTPUT = 8192


class BoundaryError(Exception):
    def __init__(self, stage: str, code: str):
        self.stage, self.code = stage, code
        super().__init__(stage + ": " + code)


class Verifier:
    def __init__(self, host: str, identity: Path, manifest: dict, runner=subprocess.run):
        self.destination = "prp-deploy@" + host
        self.base = ["ssh", "-i", str(identity), "-T", "-o", "BatchMode=yes",
                     "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
                     "-o", "ConnectTimeout=15", "-o", "ConnectionAttempts=1"]
        self.manifest, self.runner = manifest, runner

    def call(self, stage: str, args: list[str], payload=None):
        try:
            input_options = {"stdin": subprocess.DEVNULL} if payload is None else {"input": payload}
            result = self.runner(self.base + args, **input_options,
                                 capture_output=True, timeout=20,
                                 env={**os.environ, "LC_ALL": "C"})
        except subprocess.TimeoutExpired:
            raise BoundaryError(stage, "TIMEOUT") from None
        except OSError:
            raise BoundaryError(stage, "SSH_CLIENT_ERROR") from None
        if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
            raise BoundaryError(stage, "OUTPUT_TOO_LARGE")
        stderr = result.stderr.lower()
        if any(s in stderr for s in [b"permission denied (", b"authentication failed",
                                     b"no supported authentication methods"]):
            raise BoundaryError(stage, "AUTHENTICATION_FAILED")
        if any(s in stderr for s in [b"host key verification failed",
                                     b"remote host identification has changed"]):
            raise BoundaryError(stage, "HOST_KEY_FAILED")
        if any(s in stderr for s in [b"connection timed out", b"connection refused",
                                     b"could not resolve hostname", b"no route to host",
                                     b"connection reset by peer", b"connection closed by",
                                     b"kex_exchange_identification"]):
            raise BoundaryError(stage, "CONNECTION_FAILED")
        return result

    def deny_command(self, stage: str, args: list[str]):
        result = self.call(stage, args)
        if result.returncode != 2 or result.stdout or GATEWAY_DENIAL not in result.stderr:
            raise BoundaryError(stage, "EXPECTED_GATEWAY_DENIAL_MISSING")

    def sftp_exchange(self, command=None):
        return probe_sftp_init.probe(self.base, self.destination, command=command)

    def verify_subsystem(self):
        # A one-off administrator audit or exec refusal is NOT a live policy proof.
        try:
            baseline = sftp_policy.baseline_from(self.manifest)
        except sftp_policy.PolicyError as exc:
            raise BoundaryError("ssh-policy-attestation", str(exc)) from None
        challenge = secrets.token_bytes(32)
        response = self.call("ssh-policy-attestation", [self.destination, "diagnose"], payload=challenge)
        try:
            def unique(pairs):
                d = {}
                for k, v in pairs:
                    if k in d:
                        raise ValueError()
                    d[k] = v
                return d
            data = json.loads(response.stdout, object_pairs_hook=unique)
            if (response.returncode != 0 or not isinstance(data, dict)
                    or set(data) != {"schema_version", "state", "code", "stage", "table", "exception", "timestamp_utc", "ssh_policy"}):
                raise sftp_policy.PolicyError("SSH_POLICY_PROOF_UNAVAILABLE")
            diagnostic = {k: v for k, v in data.items() if k != "ssh_policy"}
            if (type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["state"] not in {"available", "stale", "no_log"}
                    or safe_diagnostic(diagnostic) != {k: v for k, v in diagnostic.items() if k != "schema_version"}):
                raise sftp_policy.PolicyError("SSH_POLICY_PROOF_INVALID")
            sftp_policy.verify_proof(self.manifest, data["ssh_policy"], challenge)
        except sftp_policy.PolicyError as exc:
            raise BoundaryError("ssh-policy-attestation", str(exc)) from None
        except (ValueError, TypeError, RecursionError):
            raise BoundaryError("ssh-policy-attestation", "SSH_POLICY_PROOF_INVALID") from None
        try:
            # The fixed mapping comes from a validated, nonce-bound LIVE server proof.
            exact = self.sftp_exchange(command=baseline["subsystem_command"])
            sftp_policy.checked_exchange(exact)
            actual = self.sftp_exchange()
            self.sftp_verdict = sftp_policy.correlate(exact, actual)
            sftp_policy.verify_proof(self.manifest, data["ssh_policy"], challenge)
        except sftp_policy.PolicyError as exc:
            raise BoundaryError("sftp-subsystem-denial", str(exc)) from None

    def verify(self):
        stage = "controller-attestation"
        result = self.call(stage, [self.destination, "controller-sha256"])
        if result.returncode != 0:
            raise BoundaryError(stage, "COMMAND_FAILED")
        try:
            verify_response(self.manifest, result.stdout.decode("ascii"))
        except (ValueError, UnicodeError):
            raise BoundaryError(stage, "CONTROLLER_ATTESTATION_FAILED") from None

        stage = "diagnose"
        result = self.call(stage, [self.destination, "diagnose"])
        try:
            data = json.loads(result.stdout)
            keys = {"schema_version", "state", "code", "stage", "table", "exception", "timestamp_utc"}
            if result.returncode != 0 or not isinstance(data, dict) or set(data) != keys:
                raise ValueError()
            if type(data["schema_version"]) is not int or data["schema_version"] != 1:
                raise ValueError()
            if data["state"] not in {"available", "stale", "no_log"}:
                raise ValueError()
            if safe_diagnostic(data) != {k: v for k, v in data.items() if k != "schema_version"}:
                raise ValueError()
            if data["state"] == "available":
                if not data["timestamp_utc"]:
                    raise ValueError()
                observed = datetime.fromisoformat(data["timestamp_utc"].replace("Z", "+00:00"))
                age = datetime.now(timezone.utc).timestamp() - observed.timestamp()
                if age < -300 or age > 7200:
                    raise ValueError()
            elif data["code"] != {"stale": "STALE_DIAGNOSTIC", "no_log": "NO_DIAGNOSTIC"}[data["state"]]:
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            raise BoundaryError(stage, "INVALID_SAFE_JSON") from None

        for stage, command in [("shell-denial", "sh"), ("sftp-command-denial", "sftp"),
                               ("argument-denial", "diagnose unexpected"),
                               ("semicolon-denial", "diagnose; id"),
                               ("newline-denial", "diagnose\nstatus")]:
            self.deny_command(stage, [self.destination, command])
        self.deny_command("shell-request-denial", [self.destination])
        self.verify_subsystem()

        # -W requests the same direct-tcpip channel used by local (-L) forwarding.
        # Port 1 is a non-business loopback target; no application request is sent.
        stage = "local-forwarding-denial"
        result = self.call(stage, ["-W", "127.0.0.1:1", self.destination])
        if result.returncode != 255 or result.stdout or b"administratively prohibited" not in result.stderr.lower():
            raise BoundaryError(stage, "EXPECTED_FORWARDING_DENIAL_MISSING")
        # Port zero requests an ephemeral listener. A wrongly accepted request
        # times out and fails the gate; disconnect removes that listener.
        stage = "remote-forwarding-denial"
        result = self.call(stage, ["-N", "-o", "ExitOnForwardFailure=yes", "-R",
                                   "127.0.0.1:0:127.0.0.1:1", self.destination])
        if result.returncode != 255 or result.stdout or b"remote port forwarding failed" not in result.stderr.lower():
            raise BoundaryError(stage, "EXPECTED_FORWARDING_DENIAL_MISSING")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        Verifier(args.host, args.identity, manifest).verify()
    except BoundaryError as exc:
        print("Restricted SSH gate blocked production: " + exc.stage + " / " + exc.code)
        return 1
    except Exception:
        print("Restricted SSH gate blocked production: VERIFIER_CONFIGURATION_ERROR")
        return 1
    print("Restricted SSH gate PASS: controller, safe diagnose, shell/SFTP and forwarding boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
