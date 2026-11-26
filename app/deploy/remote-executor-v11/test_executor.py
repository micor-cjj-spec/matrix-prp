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

    def test_203_mib_local_stream_without_whole_file_buffer(self):
        from bridge import transfer_job
        from unittest.mock import Mock
        import zipfile
        size=203*1024*1024
        block=b"Z"*(1024*1024)
        h=hashlib.sha256()
        archive=self.root/"synthetic.zip"
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED) as z:
            with z.open("image.tar","w") as out:
                for _ in range(203):
                    h.update(block)
                    out.write(block)
        outer=hashlib.sha256()
        with archive.open("rb") as stream:
            while chunk:=stream.read(1024*1024):
                outer.update(chunk)
        j=job()
        a=artifact("image.tar",size)
        a["sha256"]=h.hexdigest()
        a["source"]["archiveSize"]=archive.stat().st_size
        a["source"]["archiveSha256"]=outer.hexdigest()
        j["manifest"].update(operation="artifact.inspect",entrypoint=None,files=[a])
        j["manifestSha256"]=manifest_sha256(j["manifest"])
        p=self.provider(j,b"")
        p.artifact_zip.side_effect=lambda _:archive.open("rb")
        self.assertEqual(transfer_job(j,self.ledger,p,{("build.yml","b"*40)},NOW)["state"],"VERIFIED")
        self.assertEqual((self.root/"jobs"/j["jobId"]/"image.tar").stat().st_size,size)


class CryptoTests(unittest.TestCase):
    """Real OpenSSL with ephemeral synthetic keys, never real credentials."""
    @classmethod
    def setUpClass(cls):
        import tempfile
        import subprocess
        from pathlib import Path
        tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.identities={}
        for name in ("server","reply","other"):
            cert=Path(tmp.name)/(name+".crt")
            key=Path(tmp.name)/(name+".key")
            subprocess.run(["/usr/bin/openssl","req","-new","-x509","-nodes","-newkey","rsa:2048",
                            "-days","1","-subj","/CN=synthetic-"+name,"-keyout",str(key),"-out",str(cert)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            cls.identities[name]=(cert.read_bytes(),key.read_bytes())

    def request(self, action="submit"):
        j=job()
        return {"version":11,"target":"prp-staging","action":action,"requestId":str(uuid.uuid4()),
                "jobId":j["jobId"],"manifestSha256":j["manifestSha256"],"nonce":j["nonce"],
                "issuedAt":NOW,"expiresAt":NOW+180,"replyCertificate":self.identities["reply"][0].decode("ascii"),
                "job":j if action=="submit" else None}

    def receipt(self,req,state="SUCCEEDED"):
        return {**{k:req[k] for k in ("version","target","action","requestId","jobId","manifestSha256","nonce")},
                "issuedAt":NOW,"state":state,"result":{"exitCode":0,"summary":"synthetic"} if req["action"]=="result" else None}

    def test_encrypted_request_roundtrip(self):
        from protocol import seal_request,open_request
        req=self.request()
        cert,key=self.identities["server"]
        cipher=seal_request(req,cert,NOW)
        self.assertNotIn(b"print('hello')",cipher)
        self.assertEqual(open_request(cipher,cert,key,NOW),req)
        other_cert,other_key=self.identities["other"]
        with self.assertRaises(InvalidJob): open_request(cipher,other_cert,other_key,NOW)
        with self.assertRaises(InvalidJob): open_request(cipher[:-1]+bytes([cipher[-1]^1]),cert,key,NOW)

    def test_request_binding_and_expiry(self):
        from protocol import validate_request
        req=self.request()
        for k,v in (("target","prp-production"),("manifestSha256","e"*64),("nonce","e"*32),
                    ("jobId",str(uuid.uuid4())),("action","status")):
            with self.assertRaises(InvalidJob): validate_request(dict(req,**{k:v}),NOW)
        with self.assertRaises(InvalidJob): validate_request(req,NOW+180)

    def test_signed_encrypted_result(self):
        from protocol import seal_receipt,open_receipt
        req=self.request("result")
        receipt=self.receipt(req)
        cert,key=self.identities["server"]
        reply_key=self.identities["reply"][1]
        sealed=seal_receipt(receipt,req,cert,key,NOW)
        self.assertEqual(open_receipt(sealed,req,reply_key,cert,NOW),receipt)
        with self.assertRaises(InvalidJob): open_receipt(sealed,req,reply_key,self.identities["other"][0],NOW)
        with self.assertRaises(InvalidJob): open_receipt(sealed,dict(req,requestId=str(uuid.uuid4())),reply_key,cert,NOW)
        with self.assertRaises(InvalidJob): open_receipt(sealed[:-1]+bytes([sealed[-1]^1]),req,reply_key,cert,NOW)

    def test_unsigned_or_wrong_signer_rejected(self):
        from protocol import cms_seal,open_receipt,seal_receipt
        req=self.request("result")
        receipt=self.receipt(req)
        cert,key=self.identities["server"]
        reply_cert,reply_key=self.identities["reply"]
        with self.assertRaises(InvalidJob): open_receipt(cms_seal(canonical(receipt),reply_cert),req,reply_key,cert,NOW)
        other_cert,other_key=self.identities["other"]
        with self.assertRaises(InvalidJob): open_receipt(seal_receipt(receipt,req,other_cert,other_key,NOW),req,reply_key,cert,NOW)

    def test_fresh_query_identity_and_scope(self):
        from protocol import validate_request,validate_receipt,seal_receipt,open_receipt
        req=self.request("status")
        receipt=self.receipt(req,"RUNNING")
        cert,key=self.identities["server"]
        self.assertEqual(validate_request(req,NOW),req)
        with self.assertRaises(InvalidJob): validate_receipt(dict(receipt,result={"exitCode":0,"summary":"unexpected"}),req,NOW)
        fresh=dict(req,requestId=str(uuid.uuid4()),nonce=uuid.uuid4().hex,
                   replyCertificate=self.identities["other"][0].decode("ascii"))
        fresh_receipt=self.receipt(fresh,"RUNNING")
        ciphertext=seal_receipt(fresh_receipt,fresh,cert,key,NOW)
        self.assertEqual(open_receipt(ciphertext,fresh,self.identities["other"][1],cert,NOW),fresh_receipt)
        with self.assertRaises(InvalidJob): open_receipt(ciphertext,req,self.identities["reply"][1],cert,NOW)

    def test_comment_binding(self):
        from bridge import decode_comment_request,OWNER
        from protocol import seal_request
        req=self.request()
        cert,key=self.identities["server"]
        encoded=base64.urlsafe_b64encode(seal_request(req,cert,NOW)).decode("ascii").rstrip("=")
        actor={"login":OWNER,"type":"User"}
        event={"action":"created","repository":{"full_name":REPOSITORY},"sender":actor,
               "issue":{"number":123,"state":"open"},"comment":{"id":1,"user":actor,
               "body":"/prp-remote-v11 "+req["jobId"]+" "+encoded}}
        self.assertEqual(decode_comment_request(event,REPOSITORY,"refs/heads/main",123,cert,key,NOW),req)
        event["comment"]["body"]="/prp-remote-v11 "+str(uuid.uuid4())+" "+encoded
        with self.assertRaises(InvalidJob): decode_comment_request(event,REPOSITORY,"refs/heads/main",123,cert,key,NOW)

class FrameTests(unittest.TestCase):
    def test_multiframe_and_empty(self):
        import io
        from bridge import pack_frame,file_frame_chunks
        j=job()
        jid,md=j["jobId"],j["manifestSha256"]
        item={"path":"run.py","size":6}
        a=pack_frame(jid,md,"run.py",0,b"abc",False)
        b=pack_frame(jid,md,"run.py",3,b"def",True)
        self.assertEqual(b"".join(file_frame_chunks(io.BytesIO(a+b),jid,md,item)),b"abcdef")
        empty=pack_frame(jid,md,"empty",0,b"",True)
        self.assertEqual(list(file_frame_chunks(io.BytesIO(empty),jid,md,{"path":"empty","size":0})),[])

    def test_corruption_truncation_and_sequence(self):
        import io
        from bridge import pack_frame,file_frame_chunks
        j=job()
        jid,md=j["jobId"],j["manifestSha256"]
        item={"path":"run.py","size":6}
        a=pack_frame(jid,md,"run.py",0,b"abc",False)
        b=pack_frame(jid,md,"run.py",3,b"def",True)
        wrong=pack_frame(jid,md,"run.py",2,b"def",True)
        path=pack_frame(jid,md,"other.py",3,b"def",True)
        for raw in (a+b[:-1],a+b[:-1]+b"x",a+wrong,a+path,a+b+b"x",a,a+a+b,
                    pack_frame(jid,"f"*64,"run.py",0,b"abcdef",True)):
            with self.assertRaises(InvalidJob):
                list(file_frame_chunks(io.BytesIO(raw),jid,md,item))

    def test_frame_header_bounds(self):
        import io
        import struct
        from bridge import read_frame,FRAME_MAGIC,MAX_FRAME_HEADER,pack_frame
        with self.assertRaises(InvalidJob):
            read_frame(io.BytesIO(FRAME_MAGIC+struct.pack(">I",MAX_FRAME_HEADER+1)))
        j=job()
        with self.assertRaises(InvalidJob): pack_frame(j["jobId"],j["manifestSha256"],"../x",0,b"x",True)

    def test_ledger_does_not_publish_trailing_frame(self):
        import io
        import tempfile
        from pathlib import Path
        from executor import Ledger
        from bridge import pack_frame,file_frame_chunks
        j=job()
        jid,md=j["jobId"],j["manifestSha256"]
        item=j["manifest"]["files"][0]
        raw=pack_frame(jid,md,item["path"],0,b"print('hello')",True)+b"trailing"
        with tempfile.TemporaryDirectory() as root:
            ledger=Ledger(Path(root))
            ledger.accept(j,NOW)
            with self.assertRaises(InvalidJob):
                ledger.receive_file(jid,md,item["path"],file_frame_chunks(io.BytesIO(raw),jid,md,item),NOW)
            self.assertFalse((Path(root)/"jobs"/jid/item["path"]).exists())


class ProviderTests(unittest.TestCase):
    @staticmethod
    def response(status, data=b"", headers=None):
        import io
        from unittest.mock import Mock
        response=Mock(status=status)
        response.read=io.BytesIO(data).read
        response.getheader.side_effect=lambda name:(headers or {}).get(name)
        return response

    def test_fixed_metadata_and_repository_routes(self):
        from unittest.mock import patch
        from bridge import GitHubProvider
        provider=GitHubProvider("synthetic-test-token")
        with patch("bridge.http.client.HTTPSConnection") as connect:
            conn=connect.return_value
            conn.getresponse.side_effect=[self.response(200,b'{"id":12}'),self.response(200,b"{}")]
            self.assertEqual(provider.run_metadata(12),{"id":12})
            with provider.repository_file("b"*40,"fixtures/config.json") as stream:
                self.assertEqual(stream.read(8),b"{}")
            calls=conn.request.call_args_list
            self.assertEqual(calls[0].args[:2],("GET","/repos/"+REPOSITORY+"/actions/runs/12"))
            self.assertEqual(calls[1].args[1],"/repos/"+REPOSITORY+"/contents/fixtures/config.json?ref="+"b"*40)
            self.assertEqual(calls[0].kwargs["headers"]["Authorization"],"Bearer synthetic-test-token")
            self.assertEqual(connect.call_args.args[0],"api.github.com")
        with self.assertRaises(InvalidJob): provider.run_metadata(True)
        with self.assertRaises(InvalidJob):
            with provider.repository_file("dev","fixtures/config.json"): pass

    def test_redirect_credentials_not_forwarded(self):
        from unittest.mock import patch, Mock
        from bridge import GitHubProvider
        provider=GitHubProvider("synthetic-test-token",["storage.example.invalid"])
        api=Mock()
        storage=Mock()
        api.getresponse.return_value=self.response(302,headers={"Location":"https://storage.example.invalid/archive?sig=synthetic"})
        storage.getresponse.return_value=self.response(200,b"archive")
        with patch("bridge.http.client.HTTPSConnection",side_effect=[api,storage]) as connect:
            with provider.artifact_zip(12) as stream:
                self.assertEqual(stream.read(16),b"archive")
            self.assertEqual([c.args[0] for c in connect.call_args_list],["api.github.com","storage.example.invalid"])
            self.assertIn("Authorization",api.request.call_args.kwargs["headers"])
            self.assertNotIn("Authorization",storage.request.call_args.kwargs["headers"])
            self.assertEqual(storage.request.call_args.args[1],"/archive?sig=synthetic")

    def test_redirect_denial_and_no_second_redirect(self):
        from unittest.mock import patch, Mock
        from bridge import GitHubProvider
        provider=GitHubProvider("synthetic-test-token",["storage.example.invalid"])
        for location in ("http://storage.example.invalid/x","https://other.example.invalid/x",
                         "https://storage.example.invalid@other.example.invalid/x",
                         "https://storage.example.invalid:443/x","https://storage.example.invalid//x"):
            with patch("bridge.http.client.HTTPSConnection") as connect:
                connect.return_value.getresponse.return_value=self.response(302,headers={"Location":location})
                with self.assertRaises(InvalidJob):
                    with provider.artifact_zip(12): pass
                connect.assert_called_once()
        api=Mock()
        store=Mock()
        api.getresponse.return_value=self.response(302,headers={"Location":"https://storage.example.invalid/archive"})
        store.getresponse.return_value=self.response(302,headers={"Location":"https://other.example.invalid/x"})
        with patch("bridge.http.client.HTTPSConnection",side_effect=[api,store]) as connect:
            with self.assertRaises(InvalidJob):
                with provider.artifact_zip(12): pass
            self.assertEqual(connect.call_count,2)

    def test_stream_limits_and_deadline(self):
        import time
        from bridge import GitHubProvider,_DeadlineStream
        for headers in ({"Content-Length":"1000"},{"Content-Encoding":"gzip"}):
            with self.assertRaises(InvalidJob):
                GitHubProvider._stream(self.response(200,b"x",headers),10,time.monotonic()+10)
        stream=_DeadlineStream(self.response(200,b"1234"),time.monotonic()+10,3)
        self.assertEqual(stream.read(3),b"123")
        with self.assertRaises(InvalidJob): stream.read(1)
        stream=_DeadlineStream(self.response(200,b"x"),time.monotonic()-1,10)
        with self.assertRaises(InvalidJob): stream.read(1)

    def test_frame_sender_and_receiver(self):
        import io
        from bridge import encode_file_stream,file_frame_chunks
        j=job()
        item=j["manifest"]["files"][0]
        jid,md=j["jobId"],j["manifestSha256"]
        data=b"print('hello')"
        frames=b"".join(encode_file_stream(io.BytesIO(data),jid,md,item))
        self.assertEqual(b"".join(file_frame_chunks(io.BytesIO(frames),jid,md,item)),data)
        for corrupt in (data[:-1],data+b"x",b"x"*len(data)):
            with self.assertRaises(InvalidJob):
                list(encode_file_stream(io.BytesIO(corrupt),jid,md,item))

    def test_ssh_fixed_target_and_no_command_injection(self):
        from bridge import ssh_receive_argv
        argv=ssh_receive_argv("staging.example.invalid","/tmp/key","/tmp/hosts")
        self.assertEqual(argv[-2:],["prp-remote-v11@staging.example.invalid","receive-v11"])
        self.assertIn("StrictHostKeyChecking=yes",argv)
        self.assertIn("ClearAllForwardings=yes",argv)
        for host in ("-oProxyCommand=x","staging.example.invalid;id","user@staging.example.invalid"):
            with self.assertRaises(InvalidJob): ssh_receive_argv(host,"/tmp/key","/tmp/hosts")
        with self.assertRaises(InvalidJob): ssh_receive_argv("staging.example.invalid","relative","/tmp/hosts")


class DispatchTests(unittest.TestCase):
    # Reuse only ephemeral test identity setup, not inherited test methods.
    setUpClass=classmethod(CryptoTests.setUpClass.__func__)
    request=CryptoTests.request

    def setUp(self):
        import tempfile
        from pathlib import Path
        from executor import Ledger
        from unittest.mock import Mock
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger=Ledger(Path(self.tmp.name))
        self.provider=Mock()

    def event(self,req,comment_id):
        from bridge import OWNER
        from protocol import seal_request
        cipher=seal_request(req,self.identities["server"][0],NOW)
        encoded=base64.urlsafe_b64encode(cipher).decode("ascii").rstrip("=")
        actor={"login":OWNER,"type":"User"}
        return {"action":"created","repository":{"full_name":REPOSITORY},
                "sender":actor,"issue":{"number":123,"state":"open"},
                "comment":{"id":comment_id,"user":actor,
                "body":"/prp-remote-v11 "+req["jobId"]+" "+encoded}}

    def dispatch(self,event,issue=123):
        from bridge import dispatch_event
        cert,key=self.identities["server"]
        return dispatch_event(event,REPOSITORY,"refs/heads/main",issue,self.ledger,
                              self.provider,cert,key,cert,key,now=NOW)

    def decode(self,body,req,key=None):
        from protocol import open_receipt
        prefix,rid,encoded=body.split(" ")
        self.assertEqual((prefix,rid),("/prp-remote-result-v11",req["requestId"]))
        cipher=base64.urlsafe_b64decode(encoded+"="*(-len(encoded)%4))
        return open_receipt(cipher,req,key or self.identities["reply"][1],
                            self.identities["server"][0],NOW)

    def query(self,req,action):
        return dict(req,action=action,job=None,requestId=str(uuid.uuid4()),
                    nonce=uuid.uuid4().hex)

    def test_submit_and_cross_identity_query(self):
        from executor import Ledger
        req=self.request()
        event=self.event(req,1)
        receipt=self.decode(self.dispatch(event),req)
        self.assertEqual(receipt["state"],"VERIFIED")
        self.assertIsNone(receipt["result"])
        self.assertNotIn("print",event["comment"]["body"])
        jid,md=req["jobId"],req["manifestSha256"]
        # Synthetic worker completion only. Dispatch cannot execute scripts.
        self.ledger.claim(jid,md,NOW)
        self.ledger.finish(jid,md,"SUCCEEDED",{"exitCode":0,"summary":"synthetic"},NOW)
        self.ledger=Ledger(self.ledger.root)
        status=self.query(req,"status")
        self.assertIsNone(self.decode(self.dispatch(self.event(status,2)),status)["result"])
        query=self.query(req,"result")
        query["replyCertificate"]=self.identities["other"][0].decode("ascii")
        result=self.decode(self.dispatch(self.event(query,3)),query,self.identities["other"][1])
        self.assertEqual(result["result"],{"exitCode":0,"summary":"synthetic"})
        self.assertEqual(self.ledger.status(jid,md)["state"],"SUCCEEDED")

    def test_replay_across_restart_and_comment_reuse(self):
        from executor import Ledger
        req=self.request()
        event=self.event(req,1)
        self.dispatch(event)
        self.ledger=Ledger(self.ledger.root)
        with self.assertRaises(InvalidJob): self.dispatch(event)
        query=self.query(req,"status")
        self.dispatch(self.event(query,2))
        with self.assertRaises(InvalidJob): self.dispatch(self.event(query,3))
        fresh=self.query(req,"status")
        with self.assertRaises(InvalidJob): self.dispatch(self.event(fresh,2))
        fresh["nonce"]=query["nonce"]
        with self.assertRaises(InvalidJob): self.dispatch(self.event(fresh,4))

    def test_wrong_identity_digest_and_issue(self):
        req=self.request()
        event=self.event(req,1)
        bad=dict(event,sender={"login":"not-owner","type":"User"})
        with self.assertRaises(InvalidJob): self.dispatch(bad)
        with self.assertRaises(InvalidJob): self.dispatch(event,277)
        self.dispatch(event)
        q=self.query(req,"result")
        q["manifestSha256"]="f"*64
        with self.assertRaises(InvalidJob): self.dispatch(self.event(q,2))
        q=self.query(req,"result")
        q["jobId"]=str(uuid.uuid4())
        with self.assertRaises(InvalidJob): self.dispatch(self.event(q,3))

    def test_query_does_not_claim_or_transfer(self):
        from unittest.mock import patch
        req=self.request()
        self.dispatch(self.event(req,1))
        q=self.query(req,"result")
        with patch("bridge.transfer_job") as transfer, patch.object(self.ledger,"claim") as claim:
            result=self.decode(self.dispatch(self.event(q,2)),q)
            transfer.assert_not_called()
            claim.assert_not_called()
        self.assertEqual(result["state"],"VERIFIED")
        self.assertIsNone(result["result"])


class RelayTests(unittest.TestCase):
    setUpClass=classmethod(CryptoTests.setUpClass.__func__)
    request=CryptoTests.request
    event=DispatchTests.event
    decode=DispatchTests.decode
    query=DispatchTests.query
    setUp=DispatchTests.setUp

    def exchange(self,req,comment_id,provider,allowed=frozenset()):
        import socket
        from concurrent.futures import ThreadPoolExecutor
        from bridge import relay_receiver,relay_sender
        cert,key=self.identities["server"]
        client,server=socket.socketpair()
        client.settimeout(10)
        server.settimeout(10)
        event=self.event(req,comment_id)
        def receive():
            with server,server.makefile("rb",buffering=0) as incoming,server.makefile("wb",buffering=0) as outgoing:
                relay_receiver(incoming,outgoing,issue=123,ledger=self.ledger,
                               recipient_cert=cert,recipient_key=key,signer_cert=cert,signer_key=key,now=NOW)
                server.shutdown(socket.SHUT_WR)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(receive)
            try:
                with client,client.makefile("rb",buffering=0) as incoming,client.makefile("wb",buffering=0) as outgoing:
                    result=relay_sender(event,REPOSITORY,"refs/heads/main",123,incoming,outgoing,
                                        close_input=lambda:client.shutdown(socket.SHUT_WR),
                                        provider=provider,approved_producers=allowed,scratch=self.ledger.root)
                pending.result(timeout=15)
                return result
            finally:
                client.close()

    def test_duplex_submit_external_and_cross_chat(self):
        import io
        from unittest.mock import Mock
        from executor import Ledger
        req=self.request()
        item=inline("config.json",b"{}")
        item["source"]={"kind":"repository","repository":REPOSITORY,
                        "commit":"b"*40,"path":"fixtures/config.json"}
        req["job"]["manifest"]["files"].append(item)
        req["job"]["manifestSha256"]=manifest_sha256(req["job"]["manifest"])
        req["manifestSha256"]=req["job"]["manifestSha256"]
        provider=Mock()
        provider.repository_file.return_value=io.BytesIO(b"{}")
        receipt=self.decode(self.exchange(req,1,provider),req)
        self.assertEqual(receipt["state"],"VERIFIED")
        provider.repository_file.assert_called_once_with("b"*40,"fixtures/config.json")
        jid,md=req["jobId"],req["manifestSha256"]
        self.assertEqual((self.ledger.root/"jobs"/jid/"config.json").read_bytes(),b"{}")
        self.ledger.claim(jid,md,NOW)
        self.ledger.finish(jid,md,"SUCCEEDED",{"exitCode":0,"summary":"synthetic"},NOW)
        self.ledger=Ledger(self.ledger.root)
        query=self.query(req,"result")
        query["replyCertificate"]=self.identities["other"][0].decode("ascii")
        reply=self.decode(self.exchange(query,2,provider),query,self.identities["other"][1])
        self.assertEqual(reply["result"],{"exitCode":0,"summary":"synthetic"})
        provider.repository_file.assert_called_once()

    def test_duplex_ci_artifact(self):
        raw=BridgeTests.archive_bytes([("image.tar",b"image data")])
        j=BridgeTests.artifact_job(self,raw)
        req=self.request()
        req.update(job=j,jobId=j["jobId"],manifestSha256=j["manifestSha256"],nonce=j["nonce"])
        provider=BridgeTests.provider(j,raw)
        receipt=self.decode(self.exchange(req,1,provider,{("build.yml","b"*40)}),req)
        self.assertEqual(receipt["state"],"VERIFIED")
        provider.artifact_zip.assert_called_once_with(2)
        self.assertEqual((self.ledger.root/"jobs"/j["jobId"]/"image.tar").read_bytes(),b"image data")

    def test_control_and_plan_rejection(self):
        import io
        import struct
        from bridge import read_control,write_control,CONTROL_MAGIC,MAX_CONTROL,_validate_plan
        stream=io.BytesIO()
        write_control(stream,{"done":True})
        stream.seek(0)
        self.assertEqual(read_control(stream),{"done":True})
        with self.assertRaises(InvalidJob):
            read_control(io.BytesIO(CONTROL_MAGIC+struct.pack(">I",MAX_CONTROL+1)))
        j=job()
        plan={"version":11,"jobId":j["jobId"],"manifestSha256":j["manifestSha256"],
              "files":[inline()]}
        with self.assertRaises(InvalidJob): _validate_plan(plan,j["jobId"])


    def test_ssh_default_denial_and_pipe_deadline(self):
        import os
        import time
        from unittest.mock import patch
        from bridge import relay_over_ssh,_Pipe
        req=self.request()
        event=self.event(req,1)
        with patch("bridge.subprocess.Popen") as launch:
            with self.assertRaises(InvalidJob):
                relay_over_ssh(event,REPOSITORY,"refs/heads/main",123)
            launch.assert_not_called()
        read_fd,write_fd=os.pipe()
        with os.fdopen(read_fd,"rb",buffering=0) as source,os.fdopen(write_fd,"wb",buffering=0) as sink:
            incoming=_Pipe(source,time.monotonic()+1)
            outgoing=_Pipe(sink,time.monotonic()+1)
            self.assertEqual(outgoing.write(b"abc"),3)
            self.assertEqual(incoming.read(3),b"abc")
            incoming.deadline=time.monotonic()-1
            with self.assertRaises(InvalidJob): incoming.read(1)

    def test_credential_mode_and_final_lf(self):
        import stat
        from bridge import _credential
        path=self.ledger.root/"synthetic-identity"
        _credential(path,"synthetic")
        self.assertEqual(path.read_bytes(),b"synthetic\n")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        with self.assertRaises(OSError): _credential(path,"do not overwrite")
        with self.assertRaises(InvalidJob): _credential(self.ledger.root/"bad","")


class FixedOperationTests(unittest.TestCase):
    setUp=DispatchTests.setUp

    def prepare(self,operation="artifact.inspect"):
        j=job()
        m=j["manifest"]
        m.update(operation=operation,entrypoint=None,files=[inline("artifact.txt",b"fixture")] if operation=="artifact.inspect" else [])
        j["manifestSha256"]=manifest_sha256(m)
        jid,md=j["jobId"],j["manifestSha256"]
        self.ledger.accept(j,NOW)
        if m["files"]:
            self.ledger.receive_file(jid,md,"artifact.txt",[b"fixture"],NOW)
        self.ledger.verify(jid,md,NOW)
        return jid,md

    def test_fixed_inspect_receipt(self):
        from executor import dispatch_verified_job
        from unittest.mock import patch
        jid,md=self.prepare()
        with patch("executor.subprocess.Popen") as launch:
            result=dispatch_verified_job(self.ledger,jid,md,enabled=True,now=NOW)
            launch.assert_not_called()
        self.assertEqual(result["state"],"SUCCEEDED")
        receipt=parse(result["result"]["summary"].encode("ascii"))
        self.assertEqual(receipt["integrity"],"MATCH")
        self.assertEqual(receipt["bytes"],7)
        self.assertEqual(receipt["files"][0]["sha256"],hashlib.sha256(b"fixture").hexdigest())
        with self.assertRaises(InvalidJob): dispatch_verified_job(self.ledger,jid,md,enabled=True,now=NOW)

    def test_disabled_and_existing_stage_runner_boundary(self):
        from executor import dispatch_verified_job
        jid,md=self.prepare("stage.health")
        with self.assertRaises(InvalidJob): dispatch_verified_job(self.ledger,jid,md)
        with self.assertRaises(InvalidJob): dispatch_verified_job(self.ledger,jid,md,enabled=True,now=NOW)
        self.assertEqual(self.ledger.status(jid,md)["state"],"VERIFIED")

    def test_tamper_denied_before_fixed_operation(self):
        from executor import dispatch_verified_job
        jid,md=self.prepare()
        (self.ledger.root/"jobs"/jid/"artifact.txt").write_bytes(b"changed")
        with self.assertRaises(InvalidJob): dispatch_verified_job(self.ledger,jid,md,enabled=True,now=NOW)
        self.assertEqual(self.ledger.status(jid,md)["state"],"VERIFIED")

if __name__ == "__main__":
    unittest.main()
