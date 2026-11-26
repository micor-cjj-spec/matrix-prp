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


class SandboxTests(unittest.TestCase):
    """Synthetic launcher tests. No real process or host isolation claim."""
    setUp = LedgerTests.setUp
    transfer = LedgerTests.transfer
    ready = LedgerTests.ready

    def test_fixed_argv(self):
        from executor import sandbox_argv, SANDBOX_ROOT
        m=manifest()
        m["args"]=["; echo no-shell","--flag","$(echo no-shell)"]
        argv=sandbox_argv(m,self.root/"jobs"/self.id)
        self.assertEqual(argv[-3:],m["args"])
        self.assertEqual(argv[0],"/usr/bin/prlimit")
        self.assertIn("--unshare-net",argv)
        self.assertIn("--unshare-user",argv)
        self.assertIn("--disable-userns",argv)
        self.assertIn("--clearenv",argv)
        self.assertIn("--die-with-parent",argv)
        self.assertIn("--cap-drop",argv)
        self.assertNotIn("--bind",argv)
        self.assertNotIn("--share-net",argv)
        mounts=[tuple(argv[i+1:i+3]) for i,x in enumerate(argv) if x=="--ro-bind"]
        self.assertEqual(mounts,[(str(SANDBOX_ROOT),"/"),(str(self.root/"jobs"/self.id),"/input")])
        self.assertEqual(argv[-6:-3],["-I","-B","/input/run.py"])
        m.update(operation="sandbox.bash",entrypoint="run.sh",files=[inline("run.sh")],args=[])
        self.assertEqual(sandbox_argv(m,self.root)[-5:],["/bin/bash","--noprofile","--norc","--","/input/run.sh"])
        m.update(operation="stage.health",entrypoint=None,files=[])
        with self.assertRaises(InvalidJob): sandbox_argv(m,self.root)

    def test_preflight_denies_root(self):
        from unittest.mock import patch
        from executor import sandbox_preflight
        with patch("executor.os.geteuid",return_value=0):
            with self.assertRaises(InvalidJob): sandbox_preflight()

    def test_disabled_no_claim_or_launch(self):
        from unittest.mock import patch
        from executor import run_sandbox
        self.ready()
        with patch("executor.sandbox_preflight",side_effect=InvalidJob("disabled")), patch("executor.subprocess.Popen") as launch:
            with self.assertRaises(InvalidJob): run_sandbox(self.ledger,self.id,self.digest)
            launch.assert_not_called()
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"VERIFIED")

    def test_mock_execution_receipt(self):
        from unittest.mock import Mock, patch
        from executor import run_sandbox
        self.ready()
        proc=Mock()
        proc.wait.return_value=0
        def launch(argv,**kwargs):
            self.assertEqual(kwargs["cwd"],"/")
            self.assertTrue(kwargs["close_fds"])
            self.assertTrue(kwargs["start_new_session"])
            self.assertEqual(set(kwargs["env"]),{"PATH","LANG"})
            kwargs["stdout"].write(b"synthetic output"+b"x"*2000)
            return proc
        with patch("executor.sandbox_preflight"), patch("executor.time.time",return_value=NOW), patch("executor.subprocess.Popen",side_effect=launch) as called:
            status=run_sandbox(self.ledger,self.id,self.digest)
            called.assert_called_once()
        self.assertEqual(status["state"],"SUCCEEDED")
        receipt=self.ledger.result(self.id,self.digest)
        self.assertEqual(receipt["exitCode"],0)
        summary=parse(receipt["summary"].encode("ascii"))
        self.assertTrue(summary["truncated"])
        self.assertEqual(len(summary["stdout"]),1000)

    def test_timeout_uncertain_no_retry(self):
        from unittest.mock import Mock, patch
        import subprocess
        from executor import run_sandbox
        self.ready()
        proc=Mock(pid=12345)
        proc.wait.side_effect=[subprocess.TimeoutExpired("synthetic",30),-9]
        with patch("executor.sandbox_preflight"), patch("executor.time.time",return_value=NOW), patch("executor.subprocess.Popen",return_value=proc) as launch, patch("executor.os.killpg") as kill:
            self.assertEqual(run_sandbox(self.ledger,self.id,self.digest)["state"],"RECONCILE_REQUIRED")
            with self.assertRaises(InvalidJob): run_sandbox(self.ledger,self.id,self.digest)
            launch.assert_called_once()
            kill.assert_called_once()

    def test_launch_failure_uncertain(self):
        from unittest.mock import patch
        from executor import run_sandbox
        self.ready()
        with patch("executor.sandbox_preflight"), patch("executor.time.time",return_value=NOW), patch("executor.subprocess.Popen",side_effect=OSError("synthetic")):
            with self.assertRaises(InvalidJob): run_sandbox(self.ledger,self.id,self.digest)
        self.assertEqual(self.ledger.status(self.id,self.digest)["state"],"RECONCILE_REQUIRED")

    def test_no_fixed_stage_operation_claim(self):
        from unittest.mock import patch
        from executor import run_sandbox
        other=job()
        other["nonce"]="b"*32
        other["manifest"].update(operation="stage.health",entrypoint=None,files=[])
        other["manifestSha256"]=manifest_sha256(other["manifest"])
        sid=self.ledger.accept(other,NOW)
        sd=other["manifestSha256"]
        self.ledger.verify(sid,sd,NOW)
        with patch("executor.sandbox_preflight"), patch("executor.time.time",return_value=NOW), patch("executor.subprocess.Popen") as launch:
            with self.assertRaises(InvalidJob): run_sandbox(self.ledger,sid,sd)
            launch.assert_not_called()
        self.assertEqual(self.ledger.status(sid,sd)["state"],"VERIFIED")


class BridgeTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from executor import Ledger
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.ledger=Ledger(self.root)

    @staticmethod
    def archive_bytes(entries):
        import io
        import zipfile
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            for name,data in entries:
                z.writestr(name,data)
        return stream.getvalue()

    def artifact_job(self, raw, data=b"image data"):
        j=job()
        a=artifact("image.tar",len(data))
        a["sha256"]=hashlib.sha256(data).hexdigest()
        a["source"]["archiveSize"]=len(raw)
        a["source"]["archiveSha256"]=hashlib.sha256(raw).hexdigest()
        j["manifest"].update(operation="artifact.inspect",entrypoint=None,files=[a])
        j["manifestSha256"]=manifest_sha256(j["manifest"])
        return j

    @staticmethod
    def provider(j, raw):
        import io
        from unittest.mock import Mock
        src=j["manifest"]["files"][0]["source"]
        p=Mock()
        p.run_metadata.return_value={"id":src["runId"],"repository":{"full_name":REPOSITORY},
            "head_repository":{"full_name":REPOSITORY},"head_sha":src["commit"],
            "path":".github/workflows/"+src["workflow"],"status":"completed","conclusion":"success"}
        p.artifact_metadata.return_value={"id":src["artifactId"],"name":src["name"],
            "expired":False,"size_in_bytes":src["archiveSize"],"digest":"sha256:"+src["archiveSha256"],
            "workflow_run":{"id":src["runId"],"head_sha":src["commit"]}}
        p.artifact_zip.side_effect=lambda _:io.BytesIO(raw)
        return p

    def test_event_context(self):
        from bridge import verify_event, OWNER
        actor={"login":OWNER,"type":"User"}
        j=job()
        e={"action":"created","repository":{"full_name":REPOSITORY},
           "sender":actor,"issue":{"number":123,"state":"open"},
           "comment":{"id":1,"user":actor,"body":"/prp-remote-v11 "+j["jobId"]+" abcdefgh"}}
        self.assertEqual(verify_event(e,REPOSITORY,"refs/heads/main",123),(j["jobId"],"abcdefgh"))
        for changed in ({"action":"edited"},{"sender":{"login":"someone","type":"User"}},
                        {"issue":{"number":123,"state":"open","pull_request":{}}}):
            with self.assertRaises(InvalidJob):
                verify_event(dict(e,**changed),REPOSITORY,"refs/heads/main",123)
        with self.assertRaises(InvalidJob): verify_event(e,REPOSITORY,"refs/heads/dev",123)
        with self.assertRaises(InvalidJob): verify_event(e,REPOSITORY,"refs/heads/main",277)

    def test_inline_and_repository_stream(self):
        import io
        from unittest.mock import Mock
        from bridge import transfer_job
        j=job()
        f=inline("config.json",b"{}")
        f["source"]={"kind":"repository","repository":REPOSITORY,"commit":"b"*40,"path":"fixtures/config.json"}
        j["manifest"]["files"].append(f)
        j["manifestSha256"]=manifest_sha256(j["manifest"])
        p=Mock()
        p.repository_file.return_value=io.BytesIO(b"{}")
        self.assertEqual(transfer_job(j,self.ledger,p,now=NOW)["state"],"VERIFIED")
        p.repository_file.assert_called_once_with("b"*40,"fixtures/config.json")
        p.artifact_zip.assert_not_called()
        with self.assertRaises(InvalidJob): transfer_job(j,self.ledger,p,now=NOW)

    def test_ci_archive_stream(self):
        from bridge import transfer_job
        raw=self.archive_bytes([("image.tar",b"image data")])
        j=self.artifact_job(raw)
        p=self.provider(j,raw)
        self.assertEqual(transfer_job(j,self.ledger,p,{("build.yml","b"*40)},NOW)["state"],"VERIFIED")
        self.assertEqual((self.root/"jobs"/j["jobId"]/"image.tar").read_bytes(),b"image data")

    def test_unapproved_producer_no_download(self):
        from bridge import transfer_job
        raw=self.archive_bytes([("image.tar",b"image data")])
        j=self.artifact_job(raw)
        p=self.provider(j,raw)
        with self.assertRaises(InvalidJob): transfer_job(j,self.ledger,p,now=NOW)
        p.artifact_zip.assert_not_called()

    def test_wrong_run_or_artifact_metadata(self):
        from bridge import verify_producer
        raw=self.archive_bytes([("image.tar",b"image data")])
        j=self.artifact_job(raw)
        p=self.provider(j,raw)
        src=j["manifest"]["files"][0]["source"]
        run=p.run_metadata.return_value
        artifact_meta=p.artifact_metadata.return_value
        allow={("build.yml","b"*40)}
        for changed in ({"conclusion":"failure"},{"head_sha":"d"*40},{"path":".github/workflows/other.yml"},
                        {"head_repository":{"full_name":"fork/repo"}}):
            with self.assertRaises(InvalidJob): verify_producer(src,dict(run,**changed),artifact_meta,allow)
        for changed in ({"expired":True},{"id":3},{"digest":"sha256:"+"e"*64},{"workflow_run":{"id":99}}):
            with self.assertRaises(InvalidJob): verify_producer(src,run,dict(artifact_meta,**changed),allow)

    def test_bad_outer_bytes(self):
        from bridge import transfer_job
        raw=self.archive_bytes([("image.tar",b"image data")])
        j=self.artifact_job(raw)
        p=self.provider(j,raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaises(InvalidJob): transfer_job(j,self.ledger,p,{("build.yml","b"*40)},NOW)
        self.assertEqual(self.ledger.status(j["jobId"],j["manifestSha256"])["state"],"RECEIVED")

    def test_archive_traversal_symlink_duplicate(self):
        import zipfile
        import stat
        from bridge import transfer_job
        link=zipfile.ZipInfo("link")
        link.create_system=3
        link.external_attr=(stat.S_IFLNK|0o777)<<16
        for bad in [("../outside",b"x"),(link,b"image.tar"),("IMAGE.TAR",b"x")]:
            raw=self.archive_bytes([("image.tar",b"image data"),bad])
            j=self.artifact_job(raw)
            j["nonce"]=uuid.uuid4().hex
            p=self.provider(j,raw)
            with self.assertRaises(InvalidJob): transfer_job(j,self.ledger,p,{("build.yml","b"*40)},NOW)
            self.assertFalse((self.root/"jobs"/j["jobId"]/"image.tar").exists())

    def test_member_digest_mismatch(self):
        from bridge import transfer_job
        raw=self.archive_bytes([("image.tar",b"image data")])
        j=self.artifact_job(raw,b"wrong data")
        p=self.provider(j,raw)
        with self.assertRaises(InvalidJob): transfer_job(j,self.ledger,p,{("build.yml","b"*40)},NOW)
        self.assertFalse((self.root/"jobs"/j["jobId"]/"image.tar").exists())

if __name__ == "__main__":
    unittest.main()
