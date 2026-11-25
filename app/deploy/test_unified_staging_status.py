import copy
import json
import tempfile
import unittest
from pathlib import Path

import unified_staging_status as status


class UnifiedStagingStatusTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(status.DEFAULT.read_text(encoding="utf-8"))

    def rejects(self, mutate):
        data = copy.deepcopy(self.data)
        mutate(data)
        with self.assertRaises(ValueError):
            status.validate(data)

    def test_snapshot_is_only_blocked_review(self):
        result = status.validate(self.data)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["stage_deployment_authorized"])
        self.assertFalse(result["production_authorized"])

    def test_ci_cannot_promote(self):
        for target in ("provisioned", "running", "verified"):
            with self.subTest(target=target):
                self.rejects(lambda d: d.update(status=target))

    def test_no_forged_authorization(self):
        for key in ("stage_deployment_authorized", "production_authorized", "oauth_mcp_authorized"):
            self.rejects(lambda d: d["gates"].update({key: True}))

    def test_no_live_digest_or_schema_from_ci(self):
        self.rejects(lambda d: d["persistent_stage"].update(backend_digest="sha256:" + "a"*64))
        self.rejects(lambda d: d["persistent_stage"].update(flyway_version=31))

    def test_reject_extra_fields(self):
        self.rejects(lambda d: d["persistent_stage"].update(secret="synthetic-example"))

    def test_no_archive_as_runtime_digest(self):
        self.rejects(lambda d: d["persistent_stage"].update(web_digest=d["ci_archive"]["archive_digest"]))

    def test_wrong_archive_run(self):
        self.rejects(lambda d: d["ci_archive"].update(run_id=d["candidates"][0]["checks"][0]["run_id"]))

    def test_missing_browser_or_duplicate_run(self):
        self.rejects(lambda d: d["candidates"][2]["checks"].pop())
        self.rejects(lambda d: d["candidates"][2]["checks"][0].update(
            run_id=d["candidates"][0]["checks"][0]["run_id"]))

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text('{"status":"blocked","status":"verified"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                status.load(path)

    def test_wrong_expiry_and_future_observation(self):
        self.rejects(lambda d: d["ci_archive"].update(expired_at_observation=True))
        self.rejects(lambda d: d.update(observed_at="2099-01-01T00:00:00Z"))

    def test_missing_blocker_and_forged_gate(self):
        self.rejects(lambda d: d["blockers"].pop())
        self.rejects(lambda d: d["gates"].update(s0_host_inventory="pass"))


if __name__ == "__main__":
    unittest.main()
