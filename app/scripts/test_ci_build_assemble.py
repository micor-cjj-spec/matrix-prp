import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ci_build_assemble import inspect, restore, context
from ci_build_output import REPO

A="a"*40
B="b"*40
C="c"*40


class AssembleTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)
        self.root=self.base/"checkout"
        for path in ("app/backend","app/web"):
            (self.root/path).mkdir(parents=True)
        self.b=self.base/"backend"
        self.w=self.base/"web"
        self.expected={"schema_version":1,"repository":REPO,"pull_request":412,"tested_commit":A,
                       "run_id":123,"run_attempt":1,"scope":"CI_REHEARSAL_ONLY","production_authorized":False}
        self.make(self.b,"backend","backend-tests",B,"backend.jar",b"synthetic jar")
        self.make(self.w,"web","web-build",C,"web/index.html",b"synthetic web")
        patcher=patch("ci_build_assemble.git",side_effect=lambda _,*args:
                      B if args[-1]=="HEAD:app/backend" else C if args[-1]=="HEAD:app/web" else A)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self,d,kind,job,tree,name,raw):
        p=d/name
        p.parent.mkdir(parents=True)
        p.write_bytes(raw)
        m=dict(self.expected,kind=kind,job=job,source_tree=tree,
               files={name:{"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}})
        (d/"ci-output.json").write_text(json.dumps(m))

    def mutate(self,d,**kwargs):
        p=d/"ci-output.json"
        data=json.loads(p.read_text())
        data.update(kwargs)
        p.write_text(json.dumps(data))

    def test_same_attempt_restores_only_approved_paths(self):
        restore(self.root,self.b,self.w,self.expected)
        self.assertEqual((self.root/"app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar").read_bytes(),b"synthetic jar")
        self.assertEqual((self.root/"app/web/dist/index.html").read_bytes(),b"synthetic web")

    def test_attempt_mismatch_rejected_before_copy(self):
        self.mutate(self.w,run_attempt=2)
        with self.assertRaises(ValueError):
            restore(self.root,self.b,self.w,self.expected)
        self.assertFalse((self.root/"app/backend/target").exists())

    def test_stale_commit_and_forged_scope(self):
        for changes in ({"tested_commit":B},{"run_id":124},{"production_authorized":True},
                        {"scope":"production"},{"source_tree":C},{"job":"web-build"}):
            with self.subTest(changes=changes):
                self.mutate(self.b,**changes)
                with self.assertRaises(ValueError):
                    inspect(self.root,self.b,"backend",self.expected)
                self.mutate(self.b,**dict(self.expected,source_tree=B,job="backend-tests"))

    def test_hash_mismatch(self):
        (self.b/"backend.jar").write_bytes(b"x"*len(b"synthetic jar"))
        with self.assertRaises(ValueError):
            restore(self.root,self.b,self.w,self.expected)

    def test_extra_file_rejected(self):
        (self.w/"extra").write_text("no")
        with self.assertRaises(ValueError):
            restore(self.root,self.b,self.w,self.expected)

    def test_symlink_rejected(self):
        (self.w/"link").symlink_to(self.b/"backend.jar")
        with self.assertRaises(ValueError):
            restore(self.root,self.b,self.w,self.expected)

    def test_existing_checkout_output_rejected(self):
        (self.root/"app/web/dist").mkdir()
        with self.assertRaises(ValueError):
            restore(self.root,self.b,self.w,self.expected)

    def test_actual_checkout_and_pr_context(self):
        env={"GITHUB_REPOSITORY":REPO,"GITHUB_EVENT_NAME":"pull_request",
             "GITHUB_REF":"refs/pull/412/merge","GITHUB_WORKFLOW":"CI",
             "GITHUB_JOB":"ci-rehearsal-assemble","GITHUB_SHA":A,
             "GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"1"}
        self.assertEqual(context(self.root,env),self.expected)
        for key,value in (("GITHUB_REF","refs/heads/main"),("GITHUB_SHA",B),
                          ("GITHUB_EVENT_NAME","push"),("GITHUB_JOB","backend-tests")):
            with self.assertRaises(ValueError):
                context(self.root,dict(env,**{key:value}))


if __name__=="__main__":
    unittest.main()
