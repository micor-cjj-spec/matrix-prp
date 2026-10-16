#!/usr/bin/env python3
"""Read-only protocol evidence. Never authorizes or invokes a deployment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import verify_ssh_boundary as gate
import probe_sftp_init

STAGES = (
    "controller-attestation", "diagnose", "shell-denial", "sftp-command-denial",
    "argument-denial", "semicolon-denial", "newline-denial", "shell-request-denial",
    "sftp-subsystem-denial", "local-forwarding-denial", "remote-forwarding-denial",
    "ssh-policy-attestation",
    "sftp-exact-command-denial",
)


def metadata(result):
    """No remote bytes, command text, hostnames or exception messages escape."""
    stderr = result.stderr.lower()
    return {
        "exit_code": result.returncode,
        "stdout_empty": not result.stdout,
        "stdout_bytes": len(result.stdout),
        "stderr_bytes": len(result.stderr),
        "stderr_empty": not result.stderr,
        "stderr_category": probe_sftp_init.classify(result.stdout, result.stderr, result.returncode)["category"],
        "gateway_denial": gate.GATEWAY_DENIAL in result.stderr,
        "subsystem_request_failed": b"subsystem request failed on channel " in stderr,
        "administratively_prohibited": b"administratively prohibited" in stderr,
        "remote_forwarding_failed": b"remote port forwarding failed" in stderr,
    }


class Probe(gate.Verifier):
    def __init__(self, host, identity, manifest, runner=subprocess.run):
        super().__init__(host, identity, manifest, runner)
        self.observations = {}

    def sftp_exchange(self, command=None):
        result = super().sftp_exchange(command)
        stage = "sftp-exact-command-denial" if command else "sftp-subsystem-denial"
        self.observations[stage] = dict(result)
        return result

    def call(self, stage, args, payload=None):
        assert stage in STAGES
        original = self.runner

        def record(*a, **kw):
            result = original(*a, **kw)
            self.observations[stage] = {**metadata(result), "exception_category": None}
            return result

        self.runner = record
        try:
            return super().call(stage, args, payload=payload)
        except gate.BoundaryError as exc:
            self.observations.setdefault(stage, {})["exception_category"] = exc.code
            raise
        finally:
            self.runner = original

    def collect(self):
        failure = None
        try:
            self.verify()
        except gate.BoundaryError as exc:
            failure = exc
            self.observations.setdefault(exc.stage, {})
        # Only continue read-only forwarding probes after both identity and safe JSON
        # have passed. The production verifier itself remains strictly fail-fast.
        if failure and STAGES.index(failure.stage) > STAGES.index("diagnose"):
            for stage, args, marker in [
                ("local-forwarding-denial", ["-W", "127.0.0.1:1", self.destination], b"administratively prohibited"),
                ("remote-forwarding-denial", ["-N", "-o", "ExitOnForwardFailure=yes", "-R",
                                             "127.0.0.1:0:127.0.0.1:1", self.destination], b"remote port forwarding failed"),
            ]:
                if stage in self.observations:
                    continue
                try:
                    result = self.call(stage, args)
                    if result.returncode != 255 or result.stdout or marker not in result.stderr.lower():
                        raise gate.BoundaryError(stage, "EXPECTED_FORWARDING_DENIAL_MISSING")
                    self.observations[stage]["verification"] = "PASS"
                except gate.BoundaryError as exc:
                    self.observations.setdefault(stage, {})["verification"] = "FAIL"
                    self.observations[stage]["exception_category"] = exc.code
        result = []
        for stage in STAGES:
            entry = self.observations.get(stage)
            if entry is None:
                result.append({"stage": stage, "verification": "NOT_RUN"})
                continue
            entry = dict(entry)
            if "verification" not in entry:
                entry["verification"] = "FAIL" if failure and failure.stage == stage else "PASS"
            if failure and failure.stage == stage:
                entry["exception_category"] = failure.code
            result.append({"stage": stage, **entry})
        # The legacy test supplies DEVNULL and can make a started server exit on EOF.
        # INIT-only evidence holds stdin open, so VERSION cannot be missed for that reason.
        init_result = {"category": "NOT_RUN", "sftp_accessible": False}
        if failure is None or STAGES.index(failure.stage) > STAGES.index("diagnose"):
            init_result = probe_sftp_init.probe(self.base, self.destination)
        return {"schema_version": 1, "diagnostic_only": True,
                "production_gate_passed": failure is None and init_result["category"] in {
                    "GATEWAY_REJECTED", "SSH_PROTOCOL_REJECTED"},
                "checks": result, "sftp_init_probe": init_result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        report = Probe(args.host, args.identity, manifest).collect()
    except Exception:
        report = {"schema_version": 1, "diagnostic_only": True,
                  "production_gate_passed": False, "code": "PROBE_CONFIGURATION_ERROR"}
    # Report consists solely of fixed labels, boolean values and numeric metadata.
    encoded = json.dumps(report, sort_keys=True, indent=2)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["production_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
