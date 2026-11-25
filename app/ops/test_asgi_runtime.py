import asyncio
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from asgi_runtime import OpsASGI, create_app, CONCURRENCY
from http_boundary import HttpBoundary, Budget, response, METADATA_PATH
from query_contract import Policy

def scope(target=METADATA_PATH,method="GET",headers=None,**extra):
    return dict({"type":"http","http_version":"1.1","scheme":"https","root_path":"",
                 "query_string":b"","raw_path":target.encode(),"path":target,
                 "method":method,"headers":headers if headers is not None else [(b"host",b"ops.invalid")]},**extra)

async def call(app,request=None,events=None):
    sent=[]
    events=iter(events if events is not None else [{"type":"http.request","body":b"","more_body":False}])
    async def receive():
        return next(events)
    async def send(event):
        sent.append(event)
    await app(request if request is not None else scope(),receive,send)
    return sent

class ASGITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.boundary=HttpBoundary(server={"policy":Policy()},audit_sink=lambda _:True,
                                  budget=Budget(lambda:100),disclosure_check=lambda:False)
        self.app=OpsASGI(self.boundary)
        self.addCleanup(self.app.close)

    async def test_metadata_real_boundary_over_asgi(self):
        sent=await call(self.app)
        self.assertEqual(sent[0]["status"],200)
        self.assertEqual(json.loads(sent[1]["body"])["resource"],"https://ops.invalid/mcp")

    async def test_duplicate_headers_preserved_and_rejected(self):
        sent=await call(self.app,scope(headers=[(b"host",b"ops.invalid"),(b"host",b"evil.invalid")]))
        self.assertEqual(sent[0]["status"],400)

    async def test_scheme_path_query_and_scope_rejected_before_dispatch(self):
        with patch.object(self.boundary,"handle") as handle:
            for req in (scope(scheme="http"),scope(query_string=b"x=1"),
                        scope(raw_path=b"/%6dcp"),scope(root_path="/proxy"),
                        scope(raw_path=None),scope(http_version="2")):
                self.assertEqual((await call(self.app,req))[0]["status"],400)
            handle.assert_not_called()

    async def test_body_over_limit_and_disconnect_no_dispatch(self):
        with patch.object(self.boundary,"handle") as handle:
            sent=await call(self.app,events=[{"type":"http.request","body":b"x"*4097}])
            self.assertEqual(sent[0]["status"],413)
            self.assertEqual(await call(self.app,events=[{"type":"http.disconnect"}]),[])
            sent=await call(self.app,events=[{"type":"http.request","body":b"","more_body":True}]*32)
            self.assertEqual(sent[0]["status"],400)
            handle.assert_not_called()

    async def test_oversize_send_timeout_never_starts_second_response(self):
        sent=[]
        async def receive():
            return {"type":"http.request","body":b"x"*4097}
        async def send(event):
            sent.append(event)
            if event["type"]=="http.response.body":
                await asyncio.sleep(1)
        with patch("asgi_runtime.SEND_SECONDS",0.02):
            with self.assertRaises(asyncio.TimeoutError):
                await self.app(scope(),receive,send)
        self.assertEqual([x["status"] for x in sent if x["type"]=="http.response.start"],[413])
        self.assertEqual(self.app._active,0)

    async def test_body_deadline_releases_slot(self):
        short=OpsASGI(self.boundary,deadline=0.03)
        self.addCleanup(short.close)
        sent=[]
        async def receive():
            await asyncio.sleep(1)
        async def send(event):
            sent.append(event)
        await short(scope(),receive,send)
        self.assertEqual(sent[0]["status"],503)
        self.assertEqual(short._active,0)

    async def test_timed_out_workers_hold_slots_until_real_completion(self):
        short=OpsASGI(self.boundary,deadline=0.1)
        self.addCleanup(short.close)
        unblock=threading.Event()
        self.addCleanup(unblock.set)
        def slow(*args):
            unblock.wait(3)
            return response(200,{"secret":"must not be returned"})
        with patch.object(self.boundary,"handle",side_effect=slow):
            replies=await asyncio.gather(*(call(short) for _ in range(CONCURRENCY)))
            self.assertTrue(all(x[0]["status"]==503 and x[1]["body"]==b"" for x in replies))
            self.assertEqual(short._active,CONCURRENCY)
            self.assertEqual((await call(short))[0]["status"],429)
            unblock.set()
            for _ in range(100):
                if short._active==0:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(short._active,0)

    async def test_slow_response_sends_also_hold_admission_slots(self):
        unblock=asyncio.Event()
        started=0
        async def receive():
            return {"type":"http.request","body":b"","more_body":False}
        async def send(event):
            nonlocal started
            if event["type"]=="http.response.start":
                started+=1
                await unblock.wait()
        tasks=[asyncio.create_task(self.app(scope(),receive,send)) for _ in range(CONCURRENCY)]
        try:
            for _ in range(100):
                if started==CONCURRENCY:
                    break
                await asyncio.sleep(0.005)
            self.assertEqual(started,CONCURRENCY)
            self.assertEqual(self.app._active,CONCURRENCY)
            self.assertEqual((await call(self.app))[0]["status"],429)
        finally:
            unblock.set()
            await asyncio.gather(*tasks)
        self.assertEqual(self.app._active,0)

    async def test_default_factory_denies_even_without_lifespan(self):
        self.assertEqual((await call(create_app()))[0]["status"],503)
        sent=await call(create_app(),{"type":"lifespan"},[{"type":"lifespan.startup"}])
        self.assertEqual(sent[0]["type"],"lifespan.startup.failed")

    async def test_explicit_close_prevents_new_work(self):
        self.app.close()
        self.assertEqual((await call(self.app))[0]["status"],503)

class ProcessTests(unittest.TestCase):
    def test_direct_execution_cannot_start_listener(self):
        script=Path(__file__).parent/"asgi_runtime.py"
        proc=subprocess.run([sys.executable,str(script)],capture_output=True,timeout=3)
        self.assertEqual(proc.returncode,78)
        self.assertEqual(proc.stdout,b"")
        self.assertEqual(proc.stderr,b"")
