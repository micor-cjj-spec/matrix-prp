"""Offline P1 contract tests; no real transport or execution."""
import base64
import copy
import hashlib
import unittest
import uuid

from protocol import (InvalidJob, REPOSITORY, MAX_INLINE, MAX_ARTIFACT,
                      parse, canonical, manifest_sha256, validate_job,
                      validate_manifest, verify_bytes)

NOW = 1800000000

def inline(path="run.py", data=b"print('hello')"):
    return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "source": {"kind": "inline", "data": base64.b64encode(data).decode()}}

def artifact(path="image.tar", size=203*1024*1024):
    return {"path": path, "size": size, "sha256": "a"*64,
            "source": {"kind":"ci_artifact", "repository":REPOSITORY,
                       "commit":"b"*40, "workflow":"build.yml", "runId":1,
                       "artifactId":2, "name":"image", "archiveSize":size,
                       "archiveSha256":"c"*64, "member":"image.tar"}}

def manifest():
    return {"target":"prp-staging", "operation":"sandbox.python", "files":[inline()],
            "entrypoint":"run.py", "args":[], "timeoutSeconds":30}

def job():
    m = manifest()
    return {"version":11, "jobId":str(uuid.uuid4()), "nonce":"a"*32,
            "issuedAt":NOW, "expiresAt":NOW+180, "manifest":m,
            "manifestSha256":manifest_sha256(m)}

class ContractTests(unittest.TestCase):
    def test_round_trip_and_binding(self):
        j = job()
        self.assertEqual(validate_job(parse(canonical(j)), NOW), j)
        self.assertEqual(manifest_sha256(j["manifest"]), manifest_sha256(dict(reversed(list(j["manifest"].items())))))
        for key, value in (("args",["changed"]), ("timeoutSeconds",31)):
            changed = copy.deepcopy(j)
            changed["manifest"][key] = value
            with self.assertRaises(InvalidJob): validate_job(changed,NOW)

    def test_multifile(self):
        m=manifest()
        m["files"].append(inline("inputs/config.json",b"{}"))
        self.assertEqual(validate_manifest(m),m)

    def test_large_ci_artifact_metadata_only(self):
        m=manifest()
        m.update(operation="artifact.inspect",entrypoint=None,files=[artifact()])
        self.assertEqual(validate_manifest(m),m)

    def test_repository_exact_commit(self):
        m=manifest()
        m["files"][0]["source"]={"kind":"repository","repository":REPOSITORY,
                                   "commit":"b"*40,"path":"scripts/run.py"}
        validate_manifest(m)
        m["files"][0]["source"]["commit"]="dev"
        with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_bad_digest_and_size(self):
        for key,value in (("sha256","a"*64),("size",999),("size",True)):
            m=manifest()
            m["files"][0][key]=value
            with self.assertRaises(InvalidJob): validate_manifest(m)
        with self.assertRaises(InvalidJob): verify_bytes(inline(),b"wrong")

    def test_traversal_and_collisions(self):
        for path in ("../x","/x","a/../b","a\\b","a//b","a/.",".hidden","run.py","RUN.PY","run.py/x"):
            with self.subTest(path=path):
                m=manifest()
                m["files"].append(inline(path))
                with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_inline_and_aggregate_bounds(self):
        m=manifest()
        m["files"]=[inline("run.py",b"x"*MAX_INLINE),inline("extra",b"x")]
        with self.assertRaises(InvalidJob): validate_manifest(m)
        m=manifest()
        m.update(operation="artifact.inspect",entrypoint=None,files=[artifact("a",MAX_ARTIFACT),artifact("b",1)])
        m["files"][1]["source"]["artifactId"]=3
        with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_no_arbitrary_url_or_external_repo(self):
        m=manifest()
        m["files"][0]["source"]={"kind":"url","url":"https://example.invalid/x"}
        with self.assertRaises(InvalidJob): validate_manifest(m)
        m["files"][0]["source"]={"kind":"repository","repository":"other/repo","commit":"a"*40,"path":"run.py"}
        with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_inconsistent_archive(self):
        m=manifest()
        m.update(operation="artifact.inspect",entrypoint=None,files=[artifact("a"),artifact("b")])
        m["files"][1]["source"]["archiveSha256"]="d"*64
        with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_fixed_operations_fail_closed(self):
        for op in ("production.deploy","stage.restart","shell","stage.health"):
            m=manifest()
            m["operation"]=op
            with self.assertRaises(InvalidJob): validate_manifest(m)
        m=manifest()
        m.update(operation="stage.health",entrypoint=None,files=[])
        validate_manifest(m)
        m["args"]=["--target=production"]
        with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_target_interpreter_and_entrypoint(self):
        for k,v in (("target","prp-production"),("entrypoint","missing.py"),("operation","sandbox.bash"),("timeoutSeconds",121)):
            m=manifest()
            m[k]=v
            with self.assertRaises(InvalidJob): validate_manifest(m)

    def test_expiry_nonce_version(self):
        for k,v in (("expiresAt",NOW),("issuedAt",NOW+60),("expiresAt",NOW+301),
                    ("nonce","bad"),("jobId","bad"),("version",1),("version",True)):
            j=job()
            j[k]=v
            with self.assertRaises(InvalidJob): validate_job(j,NOW)

    def test_strict_json(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'\xff',b' '*32769):
            with self.assertRaises(InvalidJob): parse(raw)

    def test_noncanonical_inline(self):
        m=manifest()
        m["files"][0]["source"]["data"] += "="
        with self.assertRaises(InvalidJob): validate_manifest(m)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from executor import Ledger
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.job = job()
        self.id = self.ledger.accept(self.job, NOW)
        self.digest = self.job["manifestSha256"]

    def transfer(self):
        self.ledger.receive_file(self.id, self.digest, "run.py", [b"print('hello')"], NOW)

    def ready(self):
        self.transfer()
        self.ledger.verify(self.id, self.digest, NOW)

    def test_persistence_and_single_claim(self):
        from executor import Ledger
        self.ready()
        reopened = Ledger(self.root)
        self.assertEqual(reopened.status(self.id,self.digest)["state"],"VERIFIED")
        self.assertEqual(reopened.claim(self.id,self.digest,NOW),self.job["manifest"])
        with self.assertRaises(InvalidJob): self.ledger.claim(self.id,self.digest,NOW)
        reopened.finish(self.id,self.digest,"SUCCEEDED",{"exitCode":0,"summary":"synthetic"},NOW)
        self.assertEqual(self.ledger.result(self.id,self.digest)["exitCode"],0)

    def test_replay_and_lookup_binding(self):
        with self.assertRaises(InvalidJob): self.ledger.accept(self.job,NOW)
        changed=copy.deepcopy(self.job)
        changed["jobId"]=str(uuid.uuid4())
        with self.assertRaises(InvalidJob): self.ledger.accept(changed,NOW)
        with self.assertRaises(InvalidJob): self.ledger.status(self.id,"b"*64)

    def test_bad_transfer_and_retry(self):
        with self.assertRaises(InvalidJob):
            self.ledger.receive_file(self.id,self.digest,"run.py",[b"bad"],NOW)
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"RECEIVED")
        self.assertFalse((self.root/"jobs"/self.id/"run.py").exists())
        self.ready()

    def test_transfer_interruption(self):
        def interrupted():
            yield b"print"
            raise RuntimeError("synthetic disconnect")
        with self.assertRaises(RuntimeError):
            self.ledger.receive_file(self.id,self.digest,"run.py",interrupted(),NOW)
        self.assertFalse((self.root/"jobs"/self.id/".run.py.partial").exists())
        self.ready()

    def test_expiry_and_cancel(self):
        with self.assertRaises(InvalidJob):
            self.ledger.receive_file(self.id,self.digest,"run.py",[b"print('hello')"],NOW+180)
        self.ready()
        self.ledger.cancel_pending(self.id,self.digest,NOW)
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"CANCELLED")
        with self.assertRaises(InvalidJob): self.ledger.claim(self.id,self.digest,NOW)

    def test_tamper_before_verification(self):
        self.transfer()
        (self.root/"jobs"/self.id/"run.py").write_bytes(b"bad")
        with self.assertRaises(InvalidJob): self.ledger.verify(self.id,self.digest,NOW)

    def test_symlink_rejected(self):
        folder=self.root/"jobs"/self.id
        folder.mkdir(mode=0o700)
        outside=self.root/"outside"
        outside.write_bytes(b"unchanged")
        (folder/"run.py").symlink_to(outside)
        with self.assertRaises(InvalidJob): self.transfer()
        self.assertEqual(outside.read_bytes(),b"unchanged")

    def test_active_and_uncertain_blocks_next(self):
        self.ready()
        self.ledger.claim(self.id,self.digest,NOW)
        second=job()
        second["nonce"]="b"*32
        sid=self.ledger.accept(second,NOW)
        sd=second["manifestSha256"]
        self.ledger.receive_file(sid,sd,"run.py",[b"print('hello')"],NOW)
        self.ledger.verify(sid,sd,NOW)
        with self.assertRaises(InvalidJob): self.ledger.claim(sid,sd,NOW)
        self.ledger.mark_uncertain(self.id,self.digest,NOW)
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"RECONCILE_REQUIRED")
        with self.assertRaises(InvalidJob): self.ledger.claim(sid,sd,NOW)
        with self.assertRaises(InvalidJob): self.ledger.claim(self.id,self.digest,NOW)

    def test_completion_validation(self):
        self.ready()
        with self.assertRaises(InvalidJob):
            self.ledger.finish(self.id,self.digest,"SUCCEEDED",{"exitCode":0,"summary":"premature"},NOW)
        self.ledger.claim(self.id,self.digest,NOW)
        with self.assertRaises(InvalidJob):
            self.ledger.finish(self.id,self.digest,"SUCCEEDED",{"exitCode":1,"summary":"mismatch"},NOW)
        with self.assertRaises(InvalidJob):
            self.ledger.finish(self.id,self.digest,"FAILED",{"exitCode":1,"summary":"x"*20000},NOW)
        self.ledger.finish(self.id,self.digest,"FAILED",{"exitCode":1,"summary":"synthetic"},NOW)
        self.assertEqual(self.ledger.result(self.id,self.digest)["exitCode"],1)

    def test_missing_and_late_tamper(self):
        with self.assertRaises(InvalidJob): self.ledger.verify(self.id,self.digest,NOW)
        self.ready()
        (self.root/"jobs"/self.id/"run.py").write_bytes(b"tampered")
        with self.assertRaises(InvalidJob): self.ledger.claim(self.id,self.digest,NOW)
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"VERIFIED")

    def test_concurrent_claim_exactly_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from executor import Ledger
        self.ready()
        gate=Barrier(2,timeout=5)
        def attempt():
            worker=Ledger(self.root)
            gate.wait()
            try:
                worker.claim(self.id,self.digest,NOW)
                return True
            except InvalidJob:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts=[pool.submit(attempt) for _ in range(2)]
            self.assertEqual(sorted(a.result(timeout=15) for a in attempts),[False,True])

if __name__ == "__main__":
    unittest.main()
