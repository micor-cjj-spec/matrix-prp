import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import subprocess
from unittest.mock import patch
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
        attack["timestamp_utc"] = "2026-10-15T04:10:00Z"
        report = renderer.create_report(attack, {
            "release": "evil-release\n::error::leak",
            "service": "failed",
            "schema_version": "select * from secrets",
            "metadata": {"commit": "malicious", "credentials": "secret"},
        }, "a" * 40, "2026-10-15T04:09:59Z")
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
        # On failure this workflow may NOT call status, because a failed
        # status() can overwrite the original last-error.log traceback.
        failure_path = workflow.split("- name: Collect sanitized diagnosis on publish failure", 1)[1]
        failure_path = failure_path.split("- name: Upload sanitized deployment diagnosis", 1)[0]
        self.assertNotIn('"prp-deploy@$DEPLOY_HOST" status', failure_path)
        self.assertIn(': > "$status"', failure_path)
        self.assertIn("render_safe_diagnostic.py", workflow)
        self.assertIn('prp-publish-start-utc.txt', workflow)
        self.assertIn('--attempt-start', workflow)
        self.assertIn("prp-safe-deployment-diagnosis", workflow)
        self.assertNotIn("cat /var/lib/matrix-prp-deploy", workflow)

    def test_admin_installer_is_reviewable_and_does_not_replace_controller(self):
        import subprocess
        script = ROOT / "admin_install_diagnostic.sh"
        subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True)
        source = script.read_text()
        self.assertIn('--check', source)
        self.assertIn('--apply', source)
        self.assertIn("STOP: unapproved controller hash", source)
        self.assertIn('controller=/usr/local/sbin/prp-release', source)
        self.assertIn('cp -a "$gateway" "$backup/gateway.original"', source)
        self.assertIn('visudo -cf "$sudoers"', source)
        self.assertNotIn('install "$here/server-release.py"', source)
        self.assertNotIn('NOPASSWD: ALL', source)
        self.assertNotIn('chmod 777', source)

    def test_gateway_allows_only_fixed_diagnostic_command(self):
        gateway = (ROOT / "ssh-gateway.sh").read_text()
        self.assertIn("diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;", gateway)
        self.assertNotIn('diagnose\\ *)', gateway)
        self.assertIn("controller-sha256)", gateway)


class DiagnosticBoundaryRegressionTests(unittest.TestCase):
    def test_unknown_table_identifier_is_not_a_table_allowlist(self):
        trace = "in assert_preserved\nAssertionError: ('Historical row changed or deleted', 'prp_secret_token_material', 'private-key')"
        result = host.classify(trace)
        self.assertIsNone(result['table'])
        self.assertNotIn('private-key', json.dumps(result))
        self.assertIsNone(renderer.safe_diagnostic({'state':'available','table':'prp_secret_token_material'})['table'])

    def test_current_new_object_assertion_has_distinct_safe_code(self):
        result = host.classify("in assert_preserved\nAssertionError: Unexpected new business table")
        self.assertEqual(result['code'],'UNEXPECTED_BUSINESS_TABLE')
        self.assertIsNone(result['table'])

    def test_log_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'private';target.write_text('secret')
            link = Path(tmp)/'last-error.log';link.symlink_to(target)
            self.assertEqual(host.report(link)['state'],'unavailable')

    def test_nonregular_log_is_refused_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo=Path(tmp)/'log';os.mkfifo(fifo,0o600)
            self.assertEqual(host.report(fifo)['state'],'unavailable')

    def test_group_writable_log_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';path.write_text('secret');path.chmod(0o660)
            self.assertEqual(host.report(path)['state'],'unavailable')

    def test_missing_or_invalid_correlation_cannot_be_available(self):
        valid={'state':'available','code':'UNEXPECTED_BUSINESS_TABLE','timestamp_utc':'2026-10-15T04:10:00Z'}
        for start in [None,'invalid','2026-99-99T04:09:00Z']:
            self.assertEqual(renderer.create_report(valid,{},'a'*40,start)['diagnostic']['state'],'unavailable')
        valid['timestamp_utc']=None
        self.assertEqual(renderer.create_report(valid,{},'a'*40,'2026-10-15T04:09:00Z')['diagnostic']['state'],'unavailable')

    def test_even_a_one_second_old_failure_cannot_be_current(self):
        data={'state':'available','code':'UNEXPECTED_BUSINESS_TABLE','timestamp_utc':'2026-10-15T04:10:00Z'}
        self.assertEqual(renderer.create_report(data,{},'a'*40,'2026-10-15T04:10:01Z')['diagnostic']['state'],'stale')

    def test_installer_supports_both_exact_reviewed_gateway_layouts(self):
        script=(ROOT/'admin_install_diagnostic.sh').read_text()
        embedded=script.split('python3 - "$gateway" "$work/gateway.after"',1)[1].split("\n",1)[1].split("\nPY",1)[0]
        for anchor in ['  controller-sha256) exec /usr/bin/sha256sum /usr/local/sbin/prp-release ;;',
                       '  controller-sha256)\n    exec /usr/bin/sha256sum /usr/local/sbin/prp-release\n    ;;']:
            with tempfile.TemporaryDirectory() as tmp:
                before=Path(tmp)/'before';after=Path(tmp)/'after'
                original='#!/bin/sh\ncase "$SSH_ORIGINAL_COMMAND" in\n'+anchor+'\n  *) exit 2 ;;\nesac\n'
                before.write_text(original)
                subprocess.run(['python3','-c',embedded,str(before),str(after)],check=True,capture_output=True)
                self.assertEqual(after.read_text().replace('\n  diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;',''),original)
        self.assertIn('/usr/local/sbin/prp-diagnose ""',script)

    def test_gateway_denies_shell_and_diagnostic_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sudo=root/'sudo'
            sudo.write_text('#!/bin/sh\nprintf "%s\n" "$@"\n');sudo.chmod(0o755)
            env={**os.environ,'PATH':str(root)+':'+os.environ['PATH']}
            for command in ['sh','bash','sftp','diagnose /etc/shadow','diagnose; id','diagnose\nstatus','rollback x y','rollback x;id','']:
                result=subprocess.run(['sh',str(ROOT/'ssh-gateway.sh')],env={**env,'SSH_ORIGINAL_COMMAND':command},capture_output=True,text=True)
                self.assertEqual(result.returncode,2,command);self.assertEqual(result.stdout,'',command)
            result=subprocess.run(['sh',str(ROOT/'ssh-gateway.sh')],env={**env,'SSH_ORIGINAL_COMMAND':'diagnose'},capture_output=True,text=True)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout.splitlines(),['-n','/usr/local/sbin/prp-diagnose'])

    def test_no_argument_diagnostic_and_no_root_bypass(self):
        with patch.object(host.os,'geteuid',return_value=1001),patch.object(host.sys,'argv',['helper']):
            self.assertEqual(host.main(),2)
        with patch.object(host.os,'geteuid',return_value=0),patch.object(host.sys,'argv',['helper','/etc/shadow']):
            self.assertEqual(host.main(),2)

    def test_installer_hash_allowlist_is_not_relaxed(self):
        manifest=json.loads((ROOT/'controller-manifest.json').read_text())
        self.assertEqual(manifest['approved_controller']['sha256'],'bafcd9d7d79d478cf0751db9c49d2456f92a82cf6c051a4876d38fedaa7c566b')
        self.assertEqual(host.KNOWN_TABLES,renderer.KNOWN_TABLES)


if __name__ == "__main__":
    unittest.main()
