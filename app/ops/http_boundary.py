"""Bounded HTTP request/response contract, not a socket server.

The trusted ingress must preserve header multiplicity and exact request target,
bound framing before allocation, and enforce TLS. No live listener here.
"""
import json
import math
import re
import threading
import time
import uuid
from dataclasses import dataclass
from collections import deque
from query_contract import ISSUER, RESOURCE, SCOPE, Policy
from rpc_adapter import dispatch_fixture, MAX_RPC, PROTOCOL
from snapshot_contract import strict_json, utc
from collector_runtime import live_collection_enabled

RESOURCE_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
METADATA_URL = "https://ops.invalid" + METADATA_PATH
ALLOWED_ORIGIN = "https://chatgpt.com"  # candidate; real host profile unverified
MAX_HEADERS = 32
MAX_HEADER_BYTES = 12288
MAX_RESPONSE = 32768
RATE = 60
WINDOW = 60
CONCURRENCY = 4
SECURITY_HEADERS = {"authorization","host","origin","content-length","content-type",
                    "accept","mcp-protocol-version","transfer-encoding","content-encoding",
                    "mcp-session-id"}

@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple
    body: bytes

def response(status, value=None, extra=()):
    body = b"" if value is None else json.dumps(value, sort_keys=True,
        separators=(",",":"), allow_nan=False).encode("ascii")
    if len(body) > MAX_RESPONSE:
        raise ValueError("response unavailable")
    headers = (("Cache-Control","no-store"),("X-Content-Type-Options","nosniff"),
               ("Content-Length",str(len(body))))
    if body:
        headers += (("Content-Type","application/json"),)
    return Response(status, headers + extra, body)

def unauthorized():
    return response(401, extra=(("WWW-Authenticate",
        'Bearer resource_metadata="' + METADATA_URL + '"'),))

def parse_headers(pairs):
    if type(pairs) not in (list,tuple) or len(pairs)>MAX_HEADERS:
        raise ValueError("invalid headers")
    result={}
    total=0
    for pair in pairs:
        if type(pair) not in (list,tuple) or len(pair)!=2:
            raise ValueError("invalid headers")
        key,value=pair
        if type(key) is not str or type(value) is not str:
            raise ValueError("invalid headers")
        total+=len(key)+len(value)
        if total>MAX_HEADER_BYTES or not 1<=len(key)<=64:
            raise ValueError("invalid headers")
        if (not re.fullmatch(r"[!#$%&'*+.^_\x60|~0-9A-Za-z-]{1,64}",key)
                or any(ord(c)<32 or ord(c)>126 for c in value)):
            raise ValueError("invalid headers")
        key=key.lower()
        if key in SECURITY_HEADERS and key in result:
            raise ValueError("duplicate security header")
        result[key]=value
    return result

class Budget:
    """One bounded process-wide rolling window, including unauthenticated attempts.

    A real ingress also needs independent connection/body/deadline limits.
    This deliberately has no unbounded per-caller state.
    """
    def __init__(self, clock=time.monotonic):
        self._clock=clock
        self._lock=threading.Lock()
        self._starts=deque()
        self._last=None
        self._active=0

    def acquire(self):
        with self._lock:
            now=self._clock()
            if (type(now) not in (int,float) or not math.isfinite(now)
                    or now<0 or (self._last is not None and now<self._last)):
                raise ValueError("budget unavailable")
            self._last=now
            while self._starts and now-self._starts[0]>=WINDOW:
                self._starts.popleft()
            if self._active>=CONCURRENCY or len(self._starts)>=RATE:
                return False
            self._starts.append(now)
            self._active+=1
            return True

    def release(self):
        with self._lock:
            if self._active<=0:
                raise ValueError("budget unavailable")
            self._active-=1

class HttpBoundary:
    """Fixed in-process ingress for an independently configured ops resource.

    Disclosure marker checked on entry and immediately before response.
    audit_sink is a server-owned synchronous sink; exact True required.
    This does not guarantee durable audit or instantaneous revocation.
    """
    def __init__(self, *, server, audit_sink, budget, disclosure_check=live_collection_enabled):
        if type(server) is not dict or type(budget) is not Budget:
            raise ValueError("invalid service")
        self._server=dict(server)
        self._audit=audit_sink
        self._budget=budget
        self._disclosure=disclosure_check

    def handle(self, method, target, header_pairs, body):
        trace=str(uuid.uuid4())
        acquired=False
        route="unknown"
        outcome="denied"
        result=response(400)
        try:
            acquired=self._budget.acquire()
            if not acquired:
                result=response(429,extra=(("Retry-After","60"),))
                outcome="limited"
            else:
                if target==RESOURCE_PATH:
                    route="mcp"
                elif target==METADATA_PATH:
                    route="metadata"
                result=self._dispatch(method,target,header_pairs,body)
                outcome="handled" if 200<=result.status<300 else "denied"
                # Even an HTTP 200 tool error is not a successful query.
                if route=="mcp" and result.status==200:
                    parsed=strict_json(result.body,MAX_RESPONSE)
                    if "error" in parsed or parsed.get("result",{}).get("isError") is True:
                        outcome="denied"
        except Exception:
            result=response(503)
            outcome="unavailable"
        finally:
            try:
                # Unadmitted attempts must not bypass the disk/concurrency
                # budget via synchronous audit. The external ingress must
                # aggregate/drop-log rate-limit rejects independently.
                if acquired:
                    event={"version":1,"traceId":trace,"route":route,
                        "candidateStatus":result.status,"outcome":outcome}
                    # No user input, token, request ID, headers, payload, or metrics.
                    if self._audit(event) is not True:
                        result=response(503)
            except Exception:
                result=response(503)
            finally:
                try:
                    # Hold the admission slot through the final disclosure
                    # decision, including potentially slow audit callbacks.
                    # No atomic barrier with actual network delivery exists.
                    if route=="mcp" and 200<=result.status<300:
                        try:
                            if self._disclosure() is not True:
                                result=response(503)
                        except Exception:
                            result=response(503)
                finally:
                    if acquired:
                        self._budget.release()
        return result

    def _dispatch(self,method,target,pairs,body):
        if type(method) is not str or type(target) is not str or type(body) is not bytes:
            return response(400)
        if target not in (RESOURCE_PATH,METADATA_PATH):
            return response(404)
        try:
            headers=parse_headers(pairs)
        except ValueError:
            return response(400)
        if headers.get("host")!="ops.invalid":
            return response(400)
        if "origin" in headers and headers["origin"]!=ALLOWED_ORIGIN:
            return response(403)
        if "transfer-encoding" in headers or "content-encoding" in headers or "mcp-session-id" in headers:
            return response(400)
        if target==METADATA_PATH:
            if method!="GET":
                return response(405,extra=(("Allow","GET"),))
            if body or headers.get("content-length","0")!="0":
                return response(400)
            return response(200,{"resource":RESOURCE,"authorization_servers":[ISSUER],
                "scopes_supported":[SCOPE],"bearer_methods_supported":["header"]})
        if method!="POST":
            return response(405,extra=(("Allow","POST"),))
        if len(body)>MAX_RPC:
            return response(413)
        if not body or headers.get("content-length")!=str(len(body)):
            return response(400)
        if headers.get("content-type","").lower() not in ("application/json","application/json; charset=utf-8"):
            return response(415)
        # Narrow supported Streamable HTTP subset: JSON replies only, no SSE.
        accept={part.strip().lower() for part in headers.get("accept","").split(",")}
        if accept!={"application/json","text/event-stream"}:
            return response(406)
        if headers.get("mcp-protocol-version",PROTOCOL)!=PROTOCOL:
            return response(400)
        if type(self._server.get("policy")) is not Policy or self._server["policy"].enabled is not True:
            return unauthorized()
        if self._disclosure() is not True:
            return response(503)
        status,value=dispatch_fixture(body,headers.get("authorization"),**self._server)
        if status==401:
            return unauthorized()
        if status not in (200,202,400):
            return response(503)
        if self._disclosure() is not True:
            return response(503)
        return response(status,value)
