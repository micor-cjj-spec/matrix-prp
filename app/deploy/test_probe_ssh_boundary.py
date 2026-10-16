import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
import probe_ssh_boundary as probe
from test_ssh_boundary import MANIFEST, response
import test_ssh_boundary as fixtures


class ProtocolEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SSHBoundaryTests()
        self.fixture.setUp()

    def collect(self, sftp):
        def runner(args, **kwargs):
            if "-s" in args:
                if isinstance(sftp, Exception):
                    raise sftp
                return sftp
            return self.fixture.runner(args, **kwargs)
        return probe.Probe("example.invalid", Path("test"), MANIFEST, runner).collect()

    def test_protocol_rejection_collected_without_premature_acceptance(self):
        report = self.collect(response(255, err=b"subsystem request failed on channel 0\n"))
        self.assertFalse(report["production_gate_passed"])
        sftp = report["checks"][8]
        self.assertEqual(sftp["exit_code"], 255)
        self.assertTrue(sftp["stdout_empty"])
        self.assertEqual(sftp["stdout_bytes"], 0)
        self.assertFalse(sftp["gateway_denial"])
        self.assertTrue(sftp["subsystem_request_failed"])
        self.assertEqual(sftp["verification"], "FAIL")
        self.assertEqual([c["verification"] for c in report["checks"][-2:]], ["PASS", "PASS"])

    def test_explicit_gateway_rejection_passes_existing_rule(self):
        report = self.collect(response(2, err=probe.gate.GATEWAY_DENIAL))
        self.assertTrue(report["production_gate_passed"])

    def test_sftp_success_or_payload_never_passes(self):
        for result in [response(), response(2, out=b"SFTP", err=probe.gate.GATEWAY_DENIAL),
                       response(255, err=b"unrecognized error")]:
            with self.subTest(result=result.returncode):
                self.assertFalse(self.collect(result)["production_gate_passed"])

    def test_transport_failures_are_reported_not_accepted(self):
        for error, expected in [(b"Permission denied (publickey).", "AUTHENTICATION_FAILED"),
                                (b"Host key verification failed.", "HOST_KEY_FAILED"),
                                (b"Connection refused", "CONNECTION_FAILED")]:
            report = self.collect(response(255, err=error+b" subsystem request failed on channel 0"))
            self.assertFalse(report["production_gate_passed"])
            self.assertEqual(report["checks"][8]["exception_category"], expected)
        report = self.collect(subprocess.TimeoutExpired("ssh", 20, stderr=b"SECRET"))
        self.assertEqual(report["checks"][8]["exception_category"], "TIMEOUT")
        self.assertFalse(report["production_gate_passed"])

    def test_attestation_failure_never_runs_further_probes(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return response(255, err=b"Permission denied (publickey).")
        report = probe.Probe("example.invalid", Path("test"), MANIFEST, runner).collect()
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(c["verification"] == "NOT_RUN" for c in report["checks"][1:]))

    def test_no_remote_output_or_exceptions_leak_to_artifact_or_console(self):
        secret = b"PRIVATE_TOKEN_PERSONAL_ROW"
        def runner(args, **kwargs):
            if "-s" in args:
                return response(255, out=secret, err=secret+b" subsystem request failed on channel 0")
            return self.fixture.runner(args, **kwargs)
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/"safe.json"
            manifest = Path(d)/"manifest.json"
            manifest.write_text(json.dumps(MANIFEST))
            instance = probe.Probe("example.invalid", Path("test"), MANIFEST, runner)
            stdout = io.StringIO()
            with patch.object(probe, "Probe", return_value=instance), patch.object(sys, "argv", [
                "probe", "--host", "example.invalid", "--identity", "test", "--manifest", str(manifest),
                "--output", str(output)]), contextlib.redirect_stdout(stdout):
                self.assertEqual(probe.main(), 1)
            for text in [output.read_text(), stdout.getvalue()]:
                self.assertNotIn(secret.decode(), text)
                self.assertNotIn("example.invalid", text)
                self.assertNotIn("traceback", text.lower())
            self.assertEqual(json.loads(output.read_text())["checks"][8]["stdout_bytes"], len(secret))

    def test_readonly_workflow_has_no_production_operation_and_main_ci_cannot_publish(self):
        root = Path(__file__).resolve().parents[2]
        wf = yaml.safe_load((root/".github/workflows/ssh-readonly-acceptance.yml").read_text())
        job = wf["jobs"]["probe"]
        self.assertEqual(job["environment"], "production")
        self.assertIn("refs/heads/main", job["if"])
        self.assertEqual(wf["permissions"], {"contents": "read"})
        script = "\n".join(s.get("run", "") for s in job["steps"])
        for denied in ["prp-release", " sudo ", "deploy-prp.yml", "workflow run", "database", "baseline", "migrate"]:
            self.assertNotIn(denied, script.replace("This action cannot run backups, migrations, application switches or deployments.", ""))
        self.assertIn("probe_ssh_boundary.py", script)
        publish = yaml.safe_load((root/".github/workflows/deploy-prp.yml").read_text())["jobs"]["publish"]
        self.assertIn("github.event_name == 'workflow_dispatch'", publish["if"])
        self.assertNotIn("workflow_run", publish["if"])


if __name__ == "__main__":
    unittest.main()
