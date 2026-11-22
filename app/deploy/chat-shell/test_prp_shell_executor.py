"""Offline contract tests. No production SSH, GitHub secrets, or shell execution."""
import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from uuid import uuid4

SCRIPT = Path(__file__).with_name("prp_shell_executor.py")
spec = importlib.util.spec_from_file_location("prp_shell_executor", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
KEY = b"K" * 32
NOW = 1795344000


def ticket(overrides=None, raw=None):
    payload = dict(
        jobId=str(uuid4()), ownerId=1, target="prp-production",
        command="printf '%s\\n' 'hello'; id -u",
        issuedAt=NOW, expiresAt=NOW + 60,
        runSeconds=15, nonce="a" * 32)
    payload.update(overrides or {})
    payload_raw = raw if raw is not None else json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode()
    return {
        "ticket": base64.urlsafe_b64encode(payload_raw).decode().rstrip("="),
        "mac": hmac.new(KEY, payload_raw, hashlib.sha256).hexdigest()
    }


class SignedJobContract(unittest.TestCase):
    def verify(self, env):
        return module.verify_envelope(env, KEY, now=NOW)

    def denied(self, env, reason):
        with self.assertRaises(module.Denied) as failure:
            self.verify(env)
        self.assertEqual(str(failure.exception), reason)

    def test_bash_syntax_is_not_a_whitelist(self):
        command = "echo 开始\nfind /tmp -name '*.log' | wc -l\ntrue && echo ok"
        self.assertEqual(self.verify(ticket({"command": command}))["command"], command)

    def test_any_command_only_with_exact_signed_bytes(self):
        env = ticket()
        self.assertEqual(self.verify(env)["target"], "prp-production")
        raw = base64.urlsafe_b64decode(env["ticket"] + "===")
        changed = raw.replace(b"hello", b"world")
        env["ticket"] = base64.urlsafe_b64encode(changed).decode().rstrip("=")
        self.denied(env, "SIGNATURE_MISMATCH")

    def test_no_model_controlled_approval_or_principal(self):
        self.denied({**ticket(), "approved": True}, "INVALID_ENVELOPE")
        self.denied(ticket({"approved": True}), "INVALID_JOB_FIELDS")
        self.denied(ticket({"ownerId": 0}), "INVALID_OWNER")
        self.denied(ticket({"ownerId": True}), "INVALID_OWNER")

    def test_no_retargeting(self):
        self.denied(ticket({"target": "other-host"}), "INVALID_TARGET")
        self.denied(ticket({"target": "/"}), "INVALID_TARGET")

    def test_expires_fast_and_has_short_issuance_window(self):
        self.denied(ticket({"expiresAt": NOW}), "EXPIRED_OR_LONG_LIVED")
        self.denied(ticket({"expiresAt": NOW + 301}), "EXPIRED_OR_LONG_LIVED")
        self.denied(ticket({"issuedAt": NOW - 61}), "STALE_ISSUANCE")
        self.denied(ticket({"issuedAt": NOW + 16}), "STALE_ISSUANCE")

    def test_bounded_command_and_timeout(self):
        self.denied(ticket({"command": ""}), "EMPTY_COMMAND")
        self.denied(ticket({"command": "a" * 8193}), "INVALID_COMMAND_SIZE")
        self.denied(ticket({"command": "echo ok\x00"}), "INVALID_COMMAND_SIZE")
        self.denied(ticket({"runSeconds": 31}), "INVALID_TIMEOUT")
        self.denied(ticket({"runSeconds": 0}), "INVALID_TIMEOUT")
        self.denied(ticket({"runSeconds": "30"}), "INVALID_TIMEOUT")

    def test_rejects_noncanonical_and_duplicate_json(self):
        env = ticket()
        env["ticket"] += "="
        self.denied(env, "INVALID_TICKET")
        duplicate = (b'{"jobId":"one","jobId":"two"}')
        self.denied(ticket(raw=duplicate), "DUPLICATE_FIELD")
        self.denied(ticket({"nonce": "123"}), "INVALID_NONCE")
        self.denied(ticket({"jobId": "nope"}), "INVALID_JOB_ID")

    def test_wrong_key_cannot_authorize(self):
        env = ticket()
        with self.assertRaises(module.Denied) as failure:
            module.verify_envelope(env, b"X" * 32, now=NOW)
        self.assertEqual(str(failure.exception), "SIGNATURE_MISMATCH")
        with self.assertRaises(module.Denied):
            module.verify_envelope(env, b"short", now=NOW)

    def test_host_local_claim_is_exactly_once_and_nonce_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "used.sqlite3"
            with mock.patch.object(module, "STATE_DIR", Path(directory)), \
                 mock.patch.object(module, "STATE_DB", path), \
                 mock.patch.object(module, "_protected_dir"):
                job_id = str(uuid4())
                module.claim_once(job_id, "a" * 32)
                with self.assertRaisesRegex(module.Denied, "REPLAY_DENIED"):
                    module.claim_once(job_id, "b" * 32)
                with self.assertRaisesRegex(module.Denied, "REPLAY_DENIED"):
                    module.claim_once(str(uuid4()), "a" * 32)

    def test_no_unprivileged_invocation_or_argument_override(self):
        with mock.patch.object(module.os, "geteuid", return_value=1000), \
             mock.patch.object(module.sys, "argv", ["prp_shell_executor.py"]):
            with self.assertRaisesRegex(module.Denied, "ROOT_GATEWAY_REQUIRED"):
                module.main()
        with mock.patch.object(module.os, "geteuid", return_value=0), \
             mock.patch.object(module.sys, "argv", ["prp_shell_executor.py", "--command=whoami"]):
            with self.assertRaisesRegex(module.Denied, "ROOT_GATEWAY_REQUIRED"):
                module.main()


if __name__ == "__main__":
    unittest.main()
