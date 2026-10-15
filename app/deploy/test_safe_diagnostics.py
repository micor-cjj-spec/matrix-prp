import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load("read_only_diagnostic")
renderer = load("render_safe_diagnostic")


class SafeDeploymentDiagnosticsTests(unittest.TestCase):
    TRACE = (
        'Traceback (most recent call last):\n'
        '  File "/usr/local/sbin/prp-release", line 467, in rehearse\n'
        '    assert_preserved(before,snapshot(db))\n'
        '  File "/usr/local/sbin/prp-release", line 237, in assert_preserved\n'
        '    assert current.get(pk)==digest\n'
        "AssertionError: ('Historical row changed or deleted', 'prp_ai_conversations', "
        "'PRIVATE_PRIMARY_KEY_123')\n"
        "password=private-token-DO-NOT-LEAK\n"
    )

    def test_classification_never_exposes_row_id_or_secret(self):
        result = host.classify(self.TRACE)
        self.assertEqual(result["code"], "PRESERVED_ROW_CHANGED")
        self.assertEqual(result["stage"], "preservation_check")
        self.assertEqual(result["table"], "prp_ai_conversations")
        output = json.dumps(result)
        self.assertNotIn("PRIVATE_PRIMARY_KEY", output)
        self.assertNotIn("private-token", output)
        self.assertNotIn("current.get", output)

    def test_live_and_stale_logs_are_disambiguated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last-error.log"
            path.write_text(self.TRACE, encoding="utf-8")
            t = time.time()
            os.utime(path, (t, t))
            fresh = host.report(path, datetime.fromtimestamp(t + 40, timezone.utc))
            self.assertEqual(fresh["state"], "available")
            self.assertEqual(fresh["code"], "PRESERVED_ROW_CHANGED")
            old = host.report(path, datetime.fromtimestamp(t + 9000, timezone.utc))
            self.assertEqual(old["state"], "stale")
            self.assertIsNone(old["table"])

    def test_missing_error_log_stays_private_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = host.report(Path(tmp) / "missing")
            self.assertEqual(report["state"], "no_log")
            self.assertEqual(report["code"], "NO_DIAGNOSTIC")

    def test_host_exception_text_is_never_returned(self):
        trace = ('  File "/usr/local/sbin/prp-release", line 240, in migrate\n'
                 'RuntimeError: MYSQL_PWD=top-secret openai-key=sk-SECRET\n')
        output = json.dumps(host.classify(trace))
        self.assertNotIn("top-secret", output)
        self.assertNotIn("sk-SECRET", output)
        self.assertIn("RuntimeError", output)

    def test_runner_fallback_without_approved_diagnose_command(self):
        report = renderer.create_report({}, {
            "release": "r123-1", "schema_version": 17, "service": "active",
            "metadata": {"commit": "a" * 40, "api_key": "private-secret"},
        }, "b" * 40)
        self.assertEqual(report["diagnostic"]["state"], "unavailable")
        self.assertEqual(report["production"]["schema_version"], 17)
        self.assertEqual(report["production"]["service"], "active")
        self.assertIsNotNone(report["limitations"])
        self.assertNotIn("private-secret", json.dumps(report))

    def test_workflow_output_cannot_include_arbitrary_remote_fields(self):
        attack = {
            "state": "available", "code": "PRESERVED_ROW_CHANGED",
            "stage": "preservation_check", "table": "prp_ai_conversations",
            "exception": "AssertionError",
            "row_id": "PRIVATE_PRIMARY_KEY_123",
            "traceback": "MYSQL_PWD=leak",
            "unknown_secret": "api-key",
        }
        report = renderer.create_report(attack, {
            "release": "evil-release\n::error::leak",
            "service": "failed",
            "schema_version": "select * from secrets",
            "metadata": {"commit": "malicious", "credentials": "secret"},
        }, "a" * 40)
        published = json.dumps(report) + "\n".join(renderer.summary_lines(report))
        for forbidden in ["PRIVATE_PRIMARY_KEY", "MYSQL_PWD", "api-key",
                          "evil-release", "::error::leak", "select *", "api-key"]:
            self.assertNotIn(forbidden, published)
        self.assertEqual(report["diagnostic"]["table"], "prp_ai_conversations")
        self.assertIsNone(report["production"]["release"])

    def test_does_not_attribute_prior_failure_to_current_deploy(self):
        diagnostic = {
            "state": "available", "code": "PRESERVED_ROW_CHANGED",
            "stage": "preservation_check", "table": "prp_ai_conversations",
            "exception": "AssertionError",
            "timestamp_utc": "2026-10-15T04:10:00Z",
        }
        old = renderer.create_report(diagnostic, {}, "a" * 40,
                                     "2026-10-15T05:40:00Z")
        self.assertEqual(old["diagnostic"]["state"], "stale")
        self.assertEqual(old["diagnostic"]["code"], "STALE_DIAGNOSTIC")
        self.assertIsNone(old["diagnostic"]["table"])
        current = renderer.create_report(diagnostic, {}, "a" * 40,
                                         "2026-10-15T04:09:59Z")
        self.assertEqual(current["diagnostic"]["code"], "PRESERVED_ROW_CHANGED")

    def test_malformed_input_types_and_invalid_table_fail_closed(self):
        malformed = {"state": ["available"], "code": {"secret": "x"},
                     "stage": ["unknown"], "table": "prp_users\nTOKEN=abc",
                     "exception": ["AssertionError"], "timestamp_utc": []}
        result = renderer.safe_diagnostic(malformed)
        self.assertEqual(result["code"], "DIAGNOSTIC_UNAVAILABLE")
        self.assertEqual(result["state"], "unavailable")
        self.assertIsNone(result["table"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.txt"
            path.write_text("a" * (renderer.MAX_INPUT + 1), encoding="utf-8")
            self.assertEqual(renderer.load_untrusted(path), {})

    def test_github_failure_reporting_only_uses_approved_diagnostic_and_status(self):
        workflow = (ROOT.parent.parent / ".github/workflows/deploy-prp.yml").read_text()
        self.assertIn("id: production_operation", workflow)
        self.assertIn("if: failure() && steps.production_operation.outcome == 'failure'", workflow)
        self.assertIn('"prp-deploy@$DEPLOY_HOST" diagnose', workflow)
        self.assertIn('"prp-deploy@$DEPLOY_HOST" status', workflow)
        self.assertIn("render_safe_diagnostic.py", workflow)
        self.assertIn('prp-publish-start-utc.txt', workflow)
        self.assertIn('--attempt-start', workflow)
        self.assertIn("prp-safe-deployment-diagnosis", workflow)
        self.assertNotIn("cat /var/lib/matrix-prp-deploy", workflow)

    def test_gateway_allows_only_fixed_diagnostic_command(self):
        gateway = (ROOT / "ssh-gateway.sh").read_text()
        self.assertIn("diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;", gateway)
        self.assertNotIn('diagnose\\ *)', gateway)
        self.assertIn("controller-sha256)", gateway)


if __name__ == "__main__":
    unittest.main()
