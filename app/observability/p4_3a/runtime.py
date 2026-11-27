"""P4.3A isolated runtime candidate; only disposable hosted CI, synthetic issuer.

Reuse #493 SDK gateway and #424 grant/admin/audit/raw scope contracts unchanged.
No live profile, Tunnel, production data, installer or public listener.
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import pwd
import sys
import time
from urllib.parse import urlsplit

from admin_grant import open_fixed_directory
from asgi_runtime import extract_scope, send_response, MAX_BODY_EVENTS, SEND_SECONDS
from auth_adapter import GrantFile
from audit_store import AuditStoreFixture
from http_boundary import Budget, parse_headers, response, MAX_RESPONSE, CONCURRENCY
from profile_config import read_fixed
from query_contract import CLIENT, FIXTURE_PROFILE, ISSUER, RESOURCE, SCOPE, Policy, require
from rpc_adapter import MAX_RPC
from snapshot_contract import SnapshotStore
from owner_gateway import FixedGrafanaQueryAdapter, OwnerBoundGrafanaGateway, build_app
from p4_1_ci import Client

ROOT = Path("/run/prp-p43a")
READER = "prp-p43a-reader"
OTHER = "prp-p43a-other"
PORT = 18444
DEADLINE = 8
MARKER = "ENABLE_SYNTHETIC_PROFILE"
CONFIG = "synthetic.json"


def clock():
    return int(time.time())


def hosted():
    return (os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted")


def load_config(gid):
    fd = open_fixed_directory(ROOT, 0, 0o755)
    try:
        raw = read_fixed(fd, CONFIG, owner=0, gid=gid, mode=0o640, limit=2048)
        marker = read_fixed(fd, MARKER, owner=0, gid=0, mode=0o644, limit=128)
        require(marker == ("profile-sha256=" + hashlib.sha256(raw).hexdigest() + "\n").encode())
        from snapshot_contract import strict_json
        cfg = strict_json(raw, 2048)
        require(type(cfg) is dict and set(cfg) == {"upstream", "caller", "viewer", "owner", "issued", "expires"})
        endpoint = urlsplit(cfg["upstream"])
        ip = ipaddress.IPv4Address(endpoint.hostname)
        # Docker's private CI bridge only, not a DNS name or public URL.
        require(endpoint.scheme == "http" and endpoint.port == 8000
                and str(ip) == endpoint.hostname and ip in ipaddress.IPv4Network("172.16.0.0/12")
                and not endpoint.username and not endpoint.password
                and not endpoint.path and not endpoint.query and not endpoint.fragment)
        for k in ("caller", "viewer", "owner"):
            require(type(cfg[k]) is str and 16 <= len(cfg[k]) <= 256
                    and cfg[k].isascii() and all(33 <= ord(c) <= 126 for c in cfg[k]))
        require(type(cfg["issued"]) is int and type(cfg["expires"]) is int
                and cfg["issued"] <= clock() < cfg["expires"] <= cfg["issued"] + 600)
        return cfg, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


class BoundedSDK:
    """Bound SDK ASGI request/response on HTTPS loopback.

    Existing #424 scope/header/parser reused. Buffer before disclosure; no
    streaming, chunked upload, arbitrary path or compressed body.
    SDK thread may finish after cancellation: existing gateway Budget retains
    its own slot until worker exits; no network data from a timed-out request.
    """
    def __init__(self, app, enabled):
        self.app, self.enabled = app, enabled
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            return
        if self.active >= CONCURRENCY:
            await send_response(send, response(429))
            return
        self.active += 1
        result = None
        try:
            try:
                async with asyncio.timeout(DEADLINE):
                    if not self.enabled():
                        await send_response(send, response(503))
                        return
                    method, target, pairs = extract_scope(scope)
                    headers = parse_headers(pairs)
                    if headers.get("host") != "ops.invalid" or headers.get("origin", "https://chatgpt.com") != "https://chatgpt.com":
                        raise ValueError("invalid host or origin")
                    if "transfer-encoding" in headers or "content-encoding" in headers:
                        raise ValueError("invalid framing")
                    if (target == "/mcp" and method != "POST") or (target != "/mcp" and method != "GET"):
                        await send_response(send, response(405))
                        return
                    size = headers.get("content-length", "0")
                    if not size.isascii() or not size.isdecimal() or len(size) > 8:
                        raise ValueError("invalid length")
                    if int(size) > MAX_RPC:
                        await send_response(send, response(413))
                        return
                    if target == "/mcp" and headers.get("content-type", "").split(";")[0] != "application/json":
                        await send_response(send, response(415))
                        return
                    data = bytearray()
                    for _ in range(MAX_BODY_EVENTS):
                        event = await receive()
                        if event["type"] == "http.disconnect":
                            return
                        require(event["type"] == "http.request")
                        data.extend(event.get("body", b""))
                        if len(data) > MAX_RPC:
                            await send_response(send, response(413))
                            return
                        if not event.get("more_body", False):
                            break
                    else:
                        raise ValueError("too many chunks")
                    require(len(data) == int(size))
                    sent = False
                    async def replay():
                        nonlocal sent
                        if not sent:
                            sent = True
                            return {"type": "http.request", "body": bytes(data), "more_body": False}
                        return await receive()
                    events = []
                    total = 0
                    async def capture(event):
                        nonlocal total
                        require(event["type"] in ("http.response.start", "http.response.body"))
                        require(len(events) < 32)
                        total += len(event.get("body", b""))
                        require(total <= MAX_RESPONSE)
                        events.append(dict(event))
                    await self.app(scope, replay, capture)
                    require(len(events) >= 2 and events[0]["type"] == "http.response.start"
                            and all(e["type"] == "http.response.body" for e in events[1:])
                            and not events[-1].get("more_body", False))
                    if not self.enabled():
                        result = response(503)
                    else:
                        start = events[0]
                        start["headers"] = [(k,v) for k,v in start.get("headers", [])
                                            if k.lower() not in (b"cache-control", b"x-content-type-options")]
                        start["headers"] += [(b"cache-control",b"no-store"),(b"x-content-type-options",b"nosniff")]
                        # No timeout response after sending any partial response.
                        for event in events:
                            await asyncio.wait_for(send(event), SEND_SECONDS)
                        return
            except asyncio.TimeoutError:
                result = response(503)
            except Exception:
                result = response(400)
            if result is not None:
                await send_response(send, result)
        finally:
            self.active -= 1


def main():
    if not hosted() or len(sys.argv) != 1 or os.geteuid() == 0:
        return 78
    try:
        reader, other = pwd.getpwnam(READER), pwd.getpwnam(OTHER)
        require(reader.pw_uid > 0 and other.pw_uid > 0 and reader.pw_uid != other.pw_uid
                and reader.pw_gid != other.pw_gid
                and os.geteuid() == reader.pw_uid and os.getegid() == reader.pw_gid
                and set(os.getgroups()) <= {reader.pw_gid})
        cfg, digest = load_config(reader.pw_gid)
        def enabled():
            try:
                return load_config(reader.pw_gid)[1] == digest
            except Exception:
                return False
        grant = GrantFile(ROOT / "grant", reader_gid=reader.pw_gid)
        grant.current()
        def introspect(token):
            # Synthetic test identity only; actual RFC7662 remains separate.
            active = hmac.compare_digest(token, cfg["owner"])
            return json.dumps({"active": active, "iss": ISSUER, "sub": FIXTURE_PROFILE.subject,
                "aud": [RESOURCE], "client_id": CLIENT, "scope": SCOPE, "token_type": "Bearer",
                "iat": cfg["issued"], "exp": cfg["expires"]}).encode()
        upstream = Client(cfg["upstream"], cfg["caller"], cfg["viewer"])
        upstream.init()
        server = dict(policy=Policy(True), introspect=introspect, grants=grant,
                      trusted_clock=clock, store=SnapshotStore(ROOT / "snapshot"))
        gateway = OwnerBoundGrafanaGateway(server=server,
                    query_adapter=FixedGrafanaQueryAdapter(upstream.rpc, datasource_uid="prp-synthetic", clock=clock),
                    audit_sink=AuditStoreFixture(ROOT / "audit", owner_uid=reader.pw_uid, clock=clock),
                    budget=Budget(), disclosure_check=enabled)
        app = BoundedSDK(build_app(gateway, server), enabled)
        import uvicorn
        config = uvicorn.Config(app, host="127.0.0.1", port=PORT,
            ssl_certfile=str(ROOT / "tls.crt"), ssl_keyfile=str(ROOT / "tls.key"),
            loop="asyncio", http="h11", ws="none", lifespan="on", proxy_headers=False,
            access_log=False, log_config=None, log_level="critical", server_header=False,
            date_header=False, limit_concurrency=16, timeout_keep_alive=1,
            timeout_graceful_shutdown=2, h11_max_incomplete_event_size=16384)
        if not enabled():
            return 78
        runner = uvicorn.Server(config)
        runner.run()
        return 0 if runner.started else 1
    except (Exception, SystemExit):
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
