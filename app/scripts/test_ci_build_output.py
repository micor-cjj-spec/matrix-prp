import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci_build_output import context, stage, REPO


class BuildOutputTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.out = self.root / "output"
        self.jar = self.root / "app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar"
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b"fixture")
        self.web = self.root / "app/web/dist"
        self.web.mkdir(parents=True)
        (self.web / "index.html").write_bytes(b"index")
        self.meta = {"kind":"backend", "scope":"CI_REHEARSAL_ONLY", "production_authorized":False}

    def test_backend_only_allowlisted_jar(self):
        (self.jar.parent / "secret.txt").write_bytes(b"not copied")
        result = stage(self.root, self.out, "backend", self.meta)
        self.assertEqual(set(result["files"]), {"backend.jar"})
        self.assertEqual(result["files"]["backend.jar"]["sha256"], hashlib.sha256(b"fixture").hexdigest())
        self.assertFalse((self.out / "secret.txt").exists())

    def test_web_only_dist_and_manifest(self):
        (self.web / "assets").mkdir()
        (self.web / "assets/app.js").write_bytes(b"fixture")
        r = stage(self.root, self.out, "web", dict(self.meta, kind="web"))
        self.assertEqual(set(r["files"]), {"web/index.html", "web/assets/app.js"})

    def test_missing_web_index_fails(self):
        (self.web / "index.html").unlink()
        with self.assertRaises(ValueError):
            stage(self.root, self.out, "web", dict(self.meta, kind="web"))

    def test_symlink_rejected(self):
        (self.web / "link").symlink_to(self.jar)
        with self.assertRaises(ValueError):
            stage(self.root, self.out, "web", dict(self.meta, kind="web"))

    def test_existing_output_never_overwritten(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):
            stage(self.root, self.out, "backend", self.meta)

    def test_empty_jar_fails_and_removes_partial_output(self):
        self.jar.write_bytes(b"")
        with self.assertRaises(ValueError):
            stage(self.root, self.out, "backend", self.meta)
        self.assertFalse(self.out.exists())

    def test_context_exact_pr_and_checkout(self):
        a = "a" * 40
        env = {"GITHUB_REPOSITORY":REPO,"GITHUB_EVENT_NAME":"pull_request",
               "GITHUB_REF":"refs/pull/412/merge","GITHUB_WORKFLOW":"CI",
               "GITHUB_SHA":a,"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"2",
               "GITHUB_JOB":"backend-tests"}
        with patch("ci_build_output.git", return_value=a):
            result = context(self.root, "backend", env)
            self.assertEqual(result["tested_commit"], a)
            self.assertEqual(result["run_attempt"], 2)
            self.assertFalse(result["production_authorized"])
            for field, value in [("GITHUB_EVENT_NAME","push"),("GITHUB_REF","refs/pull/260/merge"),
                                 ("GITHUB_SHA","b"*40),("GITHUB_JOB","web-build"),
                                 ("GITHUB_RUN_ID","x"),("GITHUB_REPOSITORY","fork/repo")]:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    context(self.root, "backend", dict(env, **{field:value}))


if __name__ == "__main__":
    unittest.main()
