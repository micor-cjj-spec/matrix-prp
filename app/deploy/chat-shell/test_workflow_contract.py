"""Static source checks for the dormant, owner-only GitHub shell workflow."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
WORKFLOW=ROOT/'.github/workflows/prp-chat-shell.yml'
BRIDGE=ROOT/'app/deploy/chat-shell/github_bridge.py'
GATEWAY=ROOT/'app/deploy/chat-shell/gateway.sh'

class WorkflowBoundary(unittest.TestCase):
    def test_workflow_requires_exact_owner_issue_and_main(self):
        s=WORKFLOW.read_text()
        for marker in ("issue_comment:", "types: [created]", "refs/heads/main",
                       "github.event.issue.number == 277",
                       "github.event.sender.login == 'micor-cjj-spec'",
                       "github.event.comment.user.login == 'micor-cjj-spec'",
                       "github.event.sender.type == 'User'",
                       "github.event.comment.user.type == 'User'",
                       "environment: production-shell",
                       "PRP_SHELL_SSH_KEY", "PRP_SHELL_KNOWN_HOSTS",
                       "startsWith(github.event.comment.body, '/prp-shell-v1 ')"):
            self.assertIn(marker,s)
        self.assertNotIn('pull_request_target:',s)
        self.assertNotIn('PRP_DEPLOY_SSH_KEY',s)
        self.assertNotIn("github.event.comment.body }}",s)
        self.assertNotIn('runs-on: self-hosted',s)
        self.assertIn('contents: read',s)
        self.assertIn('issues: write',s)
        self.assertNotIn('contents: write',s)
    def test_no_unsanitized_shell_result_in_github_logs(self):
        s=BRIDGE.read_text()
        self.assertIn('GITHUB_EVENT_PATH',s)
        self.assertIn('PRP_CHAT_SHELL_ENCRYPTED_RESULT_POSTED',s)
        self.assertNotIn('print(completed.stdout)',s)
        self.assertNotIn('print(completed.stderr)',s)
        self.assertNotIn('echo "$SSH_ORIGINAL_COMMAND"',GATEWAY.read_text())
    def test_not_sharing_existing_production_ssh_gateway(self):
        s=GATEWAY.read_text()
        self.assertIn('prp-chat-shell-executor',s)
        self.assertNotIn('prp-release',s)
        self.assertNotIn('prp-diagnose',s)
if __name__=='__main__':
    unittest.main()
