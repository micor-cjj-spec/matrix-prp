import datetime as dt
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from release_artifact_review import review, REPO, REPO_ID

A = "a" * 40
B = "b" * 40
W = "c" * 64
NOW = dt.datetime(2026, 11, 25, tzinfo=dt.timezone.utc)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ArtifactReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "artifact.zip"
        self.expected = {"commit": A, "schema": 30, "backend_source": B, "web_source": W}
        self.run = {"id": 123, "run_attempt": 1, "name": "Deploy PRP",
                    "path": ".github/workflows/deploy-prp.yml", "event": "workflow_run",
                    "head_branch": "main", "head_sha": A, "status": "completed",
                    "conclusion": "success", "repository": {"full_name": REPO},
                    "head_repository": {"full_name": REPO}}
        self.jobs = [{"id": i, "name": name, "run_id": 123, "run_attempt": 1,
                      "head_sha": A, "status": "completed", "conclusion": result}
                     for i, (name, result) in enumerate(
                        [("release_control", "success"), ("build", "success"),
                         ("publish", "skipped")], 1)]
        self.item = {"id": 456, "name": "prp-release", "expired": False,
                     "expires_at": "2026-11-26T00:00:00Z", "workflow_run": {
                       "id": 123, "head_sha": A, "head_branch": "main",
                       "repository_id": REPO_ID, "head_repository_id": REPO_ID}}
        self.snap = {"run": self.run, "jobs": {"total_count": 3, "jobs": self.jobs},
                     "artifacts": {"total_count": 1, "artifacts": [self.item]}}
        self.archive()

    def archive(self, manifest=None, extra=None, tamper=False, outer_extra=False, symlink=False):
        files = {"backend.jar": b"synthetic jar", "web/index.html": b"fixture",
                 "migration-policy.json": json.dumps({"commit": A}).encode()}
        meta = {"id": "r123-1", "commit": A, "schema_version": 30,
                "backend_source": B, "web_source": W, "files": {k: sha(v) for k,v in files.items()}}
        meta.update(manifest or {})
        if tamper:
            files["backend.jar"] = b"changed"
        files["release.json"] = json.dumps(meta).encode()
        if extra:
            files.update(extra)
        inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode="w:gz") as tar:
            for name, raw in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
            if symlink:
                info = tarfile.TarInfo("web/link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
        self.tar_digest = "sha256:" + sha(inner.getvalue())
        with zipfile.ZipFile(self.path, "w") as z:
            z.writestr("release.tar.gz", inner.getvalue())
            if outer_extra:
                z.writestr("unexpected", "no")
        self.item["digest"] = "sha256:" + sha(self.path.read_bytes())

    def check(self):
        return review(self.expected, self.snap, self.path, NOW)

    def rejected(self):
        with self.assertRaises(ValueError):
            self.check()

    def test_valid_held_build_is_only_local_review(self):
        r = self.check()
        self.assertEqual(r["release_tar_digest"], self.tar_digest)
        self.assertNotEqual(r["github_archive_digest"], r["release_tar_digest"])
        self.assertEqual(r["artifact_evidence"]["artifact_digest"], self.tar_digest)
        self.assertEqual(r["run_attempt"], 1)
        self.assertFalse(r["deployment_authorized"])
        self.assertFalse(r["release_eligible"])
        self.assertFalse(r["live_verified"])

    def test_non_main_or_manual_run_rejected(self):
        self.run["event"] = "workflow_dispatch"
        self.rejected()

    def test_skipped_build_rejected(self):
        self.jobs[1]["conclusion"] = "skipped"
        self.rejected()

    def test_partial_attempt_rejected(self):
        self.snap["jobs"]["total_count"] = 4
        self.rejected()

    def test_wrong_job_attempt_rejected(self):
        self.jobs[1]["run_attempt"] = 2
        self.rejected()

    def test_expired_artifact_rejected(self):
        self.item["expires_at"] = "2026-11-24T00:00:00Z"
        self.rejected()

    def test_archive_digest_mismatch(self):
        self.item["digest"] = "sha256:" + W
        self.rejected()

    def test_ambiguous_artifact_rejected(self):
        self.snap["artifacts"]["artifacts"].append(dict(self.item, id=457))
        self.snap["artifacts"]["total_count"] = 2
        self.rejected()

    def test_wrong_artifact_run_rejected(self):
        self.item["workflow_run"]["id"] = 124
        self.rejected()

    def test_wrong_manifest_bindings_rejected(self):
        for manifest in ({"commit": B}, {"schema_version": 31}, {"id": "r123-2"},
                         {"backend_source": A}, {"web_source": "d" * 64}):
            with self.subTest(manifest=manifest):
                self.archive(manifest=manifest)
                self.rejected()

    def test_manifest_checksums_rejected(self):
        self.archive(tamper=True)
        self.rejected()

    def test_tar_traversal_and_links_rejected(self):
        self.archive(extra={"web/../evil": b"x"})
        self.rejected()
        self.archive(symlink=True)
        self.rejected()

    def test_outer_extra_member_rejected(self):
        self.archive(outer_extra=True)
        self.rejected()


if __name__ == "__main__":
    unittest.main()
