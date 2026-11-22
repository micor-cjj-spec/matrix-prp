"""Synthetic-only V2 event, replay and minimized reply tests."""
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readonly_ops import RejectedRequest
from security_contract import (parse_event_fixture, ReplayLedger, encode_result,
                               parse_result)

NOW = 1795320000
ISSUE = 9001  # Synthetic placeholder, NOT a configured real issue.
CIPHER = "QUJDREVGR0hJSktMTU5PUA"


class V2SecurityContractTests(unittest.TestCase):
    def setUp(self):
        self.job = str(uuid.uuid4())
        self.runtime = {
            "event_name": "issue_comment", "ref": "refs/heads/main",
            "repository": "micor-cjj-spec/matrix-prp",
            "repository_id": 1261866723, "actor": "micor-cjj-spec",
            "actor_id": 123868412,
        }
        owner = {"login": "micor-cjj-spec", "type": "User", "id": 123868412}
        self.event = {
            "action": "created",
            "repository": {"full_name": self.runtime["repository"], "id": 1261866723},
            "issue": {"number": ISSUE},
            "sender": dict(owner),
            "comment": {"id": 5555, "user": dict(owner),
                        "body": f"/prp-readonly-v2 {self.job} {CIPHER}"},
        }

    def event_check(self):
        return parse_event_fixture(self.event, self.runtime, ISSUE)

    def test_valid_synthetic_event(self):
        parsed = self.event_check()
        self.assertEqual(parsed["jobId"], self.job)
        self.assertEqual(parsed["ciphertextB64"], CIPHER)

    def test_event_missing_pinned_issue_fails(self):
        for pinned in (None, 0, -1, True):
            with self.subTest(pinned=pinned), self.assertRaises(RejectedRequest):
                parse_event_fixture(self.event, self.runtime, pinned)

    def test_wrong_issue_and_pull_request_fail(self):
        self.event["issue"]["number"] = ISSUE + 1
        with self.assertRaises(RejectedRequest):
            self.event_check()
        self.event["issue"]["number"] = ISSUE
        self.event["issue"]["pull_request"] = {"url": "x"}
        with self.assertRaises(RejectedRequest):
            self.event_check()

    def test_edited_or_deleted_event_fail(self):
        for action in ("edited", "deleted", "reopened"):
            with self.subTest(action=action), self.assertRaises(RejectedRequest):
                self.event["action"] = action
                self.event_check()

    def test_untrusted_runtime_mismatch_fails(self):
        for key, val in (("actor", "attacker"), ("ref", "refs/heads/dev"),
                         ("event_name", "workflow_dispatch"),
                         ("repository_id", 999), ("actor_id", 777)):
            with self.subTest(key=key):
                copy = dict(self.runtime, **{key: val})
                with self.assertRaises(RejectedRequest):
                    parse_event_fixture(self.event, copy, ISSUE)

    def test_wrong_repository_or_sender_or_comment_author_fail(self):
        self.event["repository"]["id"] = 0
        with self.assertRaises(RejectedRequest):
            self.event_check()
        self.event["repository"]["id"] = 1261866723
        for key in ("sender", "comment"):
            if key == "sender":
                self.event["sender"]["type"] = "Bot"
                with self.assertRaises(RejectedRequest):
                    self.event_check()
                self.event["sender"]["type"] = "User"
            else:
                self.event["comment"]["user"]["login"] = "attacker"
                with self.assertRaises(RejectedRequest):
                    self.event_check()

    def test_plaintext_commands_or_wrong_prefix_rejected(self):
        for body in ("id", "/prp-shell-v1 " + self.job + " " + CIPHER,
                     f"/prp-readonly-v2 {self.job} id", "hello",
                     f"/prp-readonly-v2 {self.job} {CIPHER} extra"):
            with self.subTest(body=body), self.assertRaises(RejectedRequest):
                self.event["comment"]["body"] = body
                self.event_check()

    def test_claim_one_use_across_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            self.assertTrue(ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW))
            with self.assertRaisesRegex(RejectedRequest, "already claimed"):
                ReplayLedger(path).claim(self.job, "b" * 32, NOW + 100, NOW)
            with self.assertRaisesRegex(RejectedRequest, "already claimed"):
                ReplayLedger(path).claim(str(uuid.uuid4()), "a" * 32, NOW + 100, NOW)

    def test_concurrent_same_claim_only_one_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            barrier = threading.Barrier(2)
            outcomes = []
            def worker():
                barrier.wait()
                try:
                    ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW)
                    outcomes.append("accepted")
                except RejectedRequest:
                    outcomes.append("rejected")
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=4)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertCountEqual(outcomes, ["accepted", "rejected"])

    def test_expired_and_long_expiry_rejected_before_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReplayLedger(Path(directory) / "ledger.sqlite")
            for expiry in (NOW, NOW - 1, NOW + 181, True):
                with self.subTest(expiry=expiry), self.assertRaises(RejectedRequest):
                    ledger.claim(self.job, "a" * 32, expiry, NOW)

    def test_unusable_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "already-a-directory"
            path.mkdir()
            with self.assertRaises(RejectedRequest):
                ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW)

    def test_replay_ledger_private_file_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            self.assertTrue(ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_replay_ledger_rejects_insecure_directory_and_database(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "ledger.sqlite"
            folder.chmod(0o755)
            with self.assertRaises(RejectedRequest):
                ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW)
            self.assertFalse(path.exists())
            folder.chmod(0o700)
            path.write_bytes(b"")
            path.chmod(0o644)
            with self.assertRaises(RejectedRequest):
                ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW)

    def test_replay_ledger_rejects_symlinks_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            file = folder / "ledger.sqlite"
            target = folder / "target.sqlite"
            target.write_bytes(b"")
            target.chmod(0o600)
            file.symlink_to(target)
            with self.assertRaises(RejectedRequest):
                ReplayLedger(file).claim(self.job, "a" * 32, NOW + 100, NOW)
            file.unlink()
            os.link(target, file)
            with self.assertRaises(RejectedRequest):
                ReplayLedger(file).claim(self.job, "a" * 32, NOW + 100, NOW)

    def test_replay_ledger_rejects_symlink_ancestor_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            actual = folder / "actual"
            private = actual / "private"
            private.mkdir(parents=True)
            private.chmod(0o700)
            alias = folder / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            path_via_alias = alias / "private" / "ledger.sqlite"
            with self.assertRaisesRegex(RejectedRequest, "state unavailable"):
                ReplayLedger(path_via_alias).claim(
                    self.job, "a" * 32, NOW + 100, NOW)
            self.assertFalse((private / "ledger.sqlite").exists())
            self.assertTrue(ReplayLedger(private / "ledger.sqlite").claim(
                self.job, "a" * 32, NOW + 100, NOW))

    def test_sqlite_open_does_not_recreate_disappearing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            ledger = ReplayLedger(path)
            prepare = ledger._prepare_private_file

            def unlink_after_check():
                prepare()
                path.unlink()

            with patch.object(ledger, "_prepare_private_file", side_effect=unlink_after_check):
                with self.assertRaises(RejectedRequest):
                    ledger.claim(self.job, "a" * 32, NOW + 100, NOW)
            self.assertFalse(path.exists())

    def test_sqlite_path_with_uri_delimiters_is_not_reinterpreted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger?mode=ro#x.sqlite"
            self.assertTrue(ReplayLedger(path).claim(self.job, "a" * 32, NOW + 100, NOW))
            self.assertTrue(path.exists())
            with self.assertRaisesRegex(RejectedRequest, "already claimed"):
                ReplayLedger(path).claim(self.job, "b" * 32, NOW + 100, NOW)

    def test_response_disk_fields_and_job_binding(self):
        data = {"totalBytes": 102400, "usedBytes": 71680,
                "freeBytes": 20480, "usagePercent": 70.0}
        raw = encode_result(self.job, "host_root_fs_usage", NOW, data=data)
        result = parse_result(raw, self.job, "host_root_fs_usage")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], data)
        with self.assertRaises(RejectedRequest):
            parse_result(raw, str(uuid.uuid4()), "host_root_fs_usage")
        with self.assertRaises(RejectedRequest):
            parse_result(raw, self.job, "prp_app_health")

    def test_health_reply_never_includes_raw_json(self):
        raw = encode_result(
            self.job, "prp_app_health", NOW,
            data={"liveness": "reachable", "readiness": "unknown"},
        )
        self.assertEqual(parse_result(raw, self.job, "prp_app_health")["data"],
                         {"liveness": "reachable", "readiness": "unknown"})
        with self.assertRaises(RejectedRequest):
            encode_result(
                self.job, "prp_app_health", NOW,
                data={"liveness": "reachable", "readiness": "unknown",
                      "knowledgeRoot": "/internal/private"},
            )

    def test_result_failure_has_only_fixed_error_code(self):
        raw = encode_result(self.job, "prp_app_health", NOW,
                            error_code="PROBE_UNAVAILABLE")
        parsed = parse_result(raw, self.job, "prp_app_health")
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["data"], {})
        self.assertEqual(parsed["errorCode"], "PROBE_UNAVAILABLE")
        with self.assertRaises(RejectedRequest):
            encode_result(self.job, "prp_app_health", NOW, error_code="secret: XXX")

    def test_sensitive_arbitrary_disk_result_rejected(self):
        base = {"totalBytes": 102400, "usedBytes": 71680,
                "freeBytes": 20480, "usagePercent": 70.0}
        for bad in ({**base, "path": "/etc/shadow"},
                    {**base, "usedBytes": -1},
                    {**base, "usagePercent": 33},
                    {**base, "totalBytes": True},
                    {**base, "freeBytes": 40960},
                    {**base, "totalBytes": 1 << 63},
                    {**base, "usedBytes": 1 << 63},
                    {**base, "freeBytes": 1 << 63}):
            with self.subTest(bad=bad), self.assertRaises(RejectedRequest):
                encode_result(self.job, "host_root_fs_usage", NOW, data=bad)

    def test_unknown_or_duplicate_result_fields_rejected(self):
        raw = encode_result(
            self.job, "prp_app_health", NOW,
            data={"liveness": "unknown", "readiness": "unknown"},
        )
        parsed = json.loads(raw)
        parsed["stdout"] = "private"
        with self.assertRaises(RejectedRequest):
            parse_result(json.dumps(parsed).encode(), self.job, "prp_app_health")
        with self.assertRaises(RejectedRequest):
            parse_result(b'{"version":2,"version":2}', self.job, "prp_app_health")


if __name__ == "__main__":
    unittest.main()
