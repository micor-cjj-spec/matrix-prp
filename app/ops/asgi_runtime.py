"""Independent ASGI runtime candidate. No listener or live profile is created.

An approved external ASGI server must enforce TLS, connection and parser
limits before invoking this adapter. All live issuer/host settings are
still synthetic .invalid. The default factory is permanently disabled.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from http_boundary import (HttpBoundary, response, MAX_HEADERS, MAX_HEADER_BYTES,
                           RESOURCE_PATH, METADATA_PATH, CONCURRENCY)
from rpc_adapter import MAX_RPC

MAX_BODY_EVENTS=32
REQUEST_SECONDS=5
SEND_SECONDS=1

def extract_scope(scope):
    if (type(scope) is not dict or scope.get("type")!="http"
            or scope.get("http_version")!="1.1" or scope.get("scheme")!="https"
            or scope.get("root_path","")!="" or scope.get("query_string")!=b""):
        raise ValueError("invalid request")
    raw=scope.get("raw_path")
    if raw not in (RESOURCE_PATH.encode("ascii"),METADATA_PATH.encode("ascii")):
        raise ValueError("invalid target")
    target=raw.decode("ascii")
    if scope.get("path")!=target:
        raise ValueError("invalid target")
    method=scope.get("method")
    if type(method) is not str or len(method)>8:
        raise ValueError("invalid method")
    headers=scope.get("headers")
    if type(headers) not in (list,tuple) or len(headers)>MAX_HEADERS:
        raise ValueError("invalid headers")
    count=0
    output=[]
    for pair in headers:
        if type(pair) not in (list,tuple) or len(pair)!=2:
            raise ValueError("invalid headers")
        key,value=pair
        if type(key) is not bytes or type(value) is not bytes:
            raise ValueError("invalid headers")
        count+=len(key)+len(value)
        if count>MAX_HEADER_BYTES or not 1<=len(key)<=64:
            raise ValueError("invalid headers")
        output.append((key.decode("ascii"),value.decode("ascii")))
    return method,target,output

async def send_response(send, result):
    await asyncio.wait_for(send({"type":"http.response.start","status":result.status,
        "headers":[(k.lower().encode("ascii"),v.encode("ascii")) for k,v in result.headers]}),SEND_SECONDS)
    await asyncio.wait_for(send({"type":"http.response.body","body":result.body,
                                 "more_body":False}),SEND_SECONDS)

class OpsASGI:
    """Bounded single-process adapter; one admission slot includes body read.

    Both worker completion and request send/abort are required to release a
    slot after submission. Python cannot safely cancel a stuck sync worker.
    A real process watchdog and ingress limits remain mandatory.
    """
    def __init__(self,boundary,*,deadline=REQUEST_SECONDS):
        if type(boundary) is not HttpBoundary or type(deadline) not in (int,float) or not 0<deadline<=REQUEST_SECONDS:
            raise ValueError("invalid runtime")
        self._boundary=boundary
        self._deadline=deadline
        self._active=0
        self._closed=False
        self._pool=ThreadPoolExecutor(max_workers=CONCURRENCY,thread_name_prefix="ops-read")

    def close(self):
        self._closed=True
        self._pool.shutdown(wait=False,cancel_futures=True)

    def _release(self,_future=None):
        self._active-=1

    async def __call__(self,scope,receive,send):
        if scope.get("type")=="lifespan":
            while True:
                event=await receive()
                if event.get("type")=="lifespan.startup":
                    await send({"type":"lifespan.startup.complete"})
                elif event.get("type")=="lifespan.shutdown":
                    self.close()
                    await send({"type":"lifespan.shutdown.complete"})
                    return
                else:
                    return
        if scope.get("type")!="http":
            return
        if self._closed or self._active>=CONCURRENCY:
            await send_response(send,response(503 if self._closed else 429))
            return
        self._active+=1
        submitted=False
        worker_done=False
        request_done=False
        def finished(future):
            nonlocal worker_done
            # Observe a late exception even if the requester timed out.
            if not future.cancelled():
                future.exception()
            worker_done=True
            if request_done:
                self._release()
        loop=asyncio.get_running_loop()
        end=loop.time()+self._deadline
        try:
            try:
                method,target,headers=extract_scope(scope)
                body=bytearray()
                for _ in range(MAX_BODY_EVENTS):
                    remaining=end-loop.time()
                    if remaining<=0:
                        raise asyncio.TimeoutError
                    event=await asyncio.wait_for(receive(),remaining)
                    if event.get("type")=="http.disconnect":
                        return
                    chunk=event.get("body",b"")
                    more=event.get("more_body",False)
                    if event.get("type")!="http.request" or type(chunk) is not bytes or type(more) is not bool:
                        raise ValueError("invalid framing")
                    if len(body)+len(chunk)>MAX_RPC:
                        await send_response(send,response(413))
                        return
                    body.extend(chunk)
                    if not more:
                        break
                else:
                    raise ValueError("too many body events")
                remaining=end-loop.time()
                if remaining<=0:
                    raise asyncio.TimeoutError
                future=loop.run_in_executor(self._pool,self._boundary.handle,
                                            method,target,headers,bytes(body))
                submitted=True
                future.add_done_callback(finished)
                # Timeout/cancellation must not free a still-running worker.
                result=await asyncio.wait_for(asyncio.shield(future),remaining)
                if loop.time()>=end:
                    raise asyncio.TimeoutError
            except asyncio.TimeoutError:
                result=response(503)
            except (ValueError,TypeError,UnicodeError):
                result=response(400)
            except Exception:
                result=response(503)
            await send_response(send,result)
        finally:
            request_done=True
            if not submitted or worker_done:
                self._release()

def create_app():
    """Default ASGI factory is inert, including under an external runner.

    Real configuration composition is separately gated. No credentials,
    host reads, files, issuer access or listener on import or factory call.
    """
    async def disabled(scope,receive,send):
        if scope.get("type")=="lifespan":
            event=await receive()
            if event.get("type")=="lifespan.startup":
                await send({"type":"lifespan.startup.failed",
                            "message":"PRP ops live profile not authorized"})
        elif scope.get("type")=="http":
            await send_response(send,response(503))
    return disabled

if __name__=="__main__":
    # Never start a listener via direct invocation.
    raise SystemExit(78)
