"""Regression gate: V2 remains offline-only until a separately approved pilot.

This is a static fail-closed guard, not a security sandbox, not a GitHub
authenticator, and not proof of end-user ChatGPT approval. Its goal is to
detect accidental connectivity or privileged GitHub workflow activation
inside the current explicitly unconnected V2 candidate.
"""
import ast
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNTIME_FILES = ("readonly_ops.py", "security_contract.py")
WORKFLOW = REPO / ".github" / "workflows" / "chat-readonly-v2-contract.yml"
BANNED_IMPORTS = (
    "subprocess", "socket", "requests", "httpx", "paramiko",
    "ftplib", "smtplib", "http.client", "urllib.request",
    "asyncio.subprocess", "fabric", "invoke",
)
BANNED_CALLS = (
    "eval", "exec", "compile", "__import__", "os.system", "os.popen",
    "os.spawnl", "os.spawnv", "os.execv", "os.execve",
)
BANNED_WORKFLOW_TRIGGERS = (
    "issue_comment", "workflow_dispatch", "repository_dispatch",
    "schedule", "workflow_run", "push",
)


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


class OfflineBoundaryTests(unittest.TestCase):
    def test_runtime_has_no_network_process_or_dynamic_execution(self):
        for relative in RUNTIME_FILES:
            with self.subTest(file=relative):
                tree = ast.parse((HERE / relative).read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for item in node.names:
                            name = item.name
                            self.assertFalse(any(name == b or name.startswith(b + ".")
                                                 for b in BANNED_IMPORTS),
                                             f"{relative}: forbidden import {name}")
                    if isinstance(node, ast.ImportFrom):
                        name = node.module or ""
                        self.assertFalse(any(name == b or name.startswith(b + ".")
                                             for b in BANNED_IMPORTS),
                                         f"{relative}: forbidden import {name}")
                    if isinstance(node, ast.Call):
                        name = _call_name(node.func)
                        self.assertNotIn(name, BANNED_CALLS,
                                         f"{relative}: forbidden call {name}")

    def test_v2_workflow_is_pr_only_and_has_no_live_credentials(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^on:\n  pull_request:\n")
        for name in BANNED_WORKFLOW_TRIGGERS:
            with self.subTest(trigger=name):
                self.assertNotRegex(source, r"(?m)^  " + re.escape(name) + r":")
        for forbidden in (
            "secrets.", "vars.PRP_CHAT_SHELL_ENABLED", "production-shell",
            "environment:", "ssh-agent", "ssh -", "GH_TOKEN", "GITHUB_TOKEN:",
            "issues: write", "workflow_dispatch", "issue_comment:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read\n")
        self.assertIn("persist-credentials: false", source)
        self.assertNotIn("continue-on-error:", source)


if __name__ == "__main__":
    unittest.main()
