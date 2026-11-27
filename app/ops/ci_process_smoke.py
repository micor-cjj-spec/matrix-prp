"""CI-only real TLS loopback process smoke. NEVER use this fixture as a service.

The child receives an already-bound loopback socket and an ephemeral directory.
All metrics, bearer and introspection claims are synthetic; no live issuer,
host metric source, production path, or credential is used. No CLI deployment.
"""
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from asgi_runtime import OpsASGI
from audit_store import AuditStoreFixture, AUDIT_NAME
from auth_adapter import GrantFile, parse_grant
from http_boundary import HttpBoundary, Budget, METADATA_PATH
from query_contract import ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE, TOOL, Policy
from snapshot_contract import SnapshotStore
from test_snapshot_contract import NOW, sample

TOKEN="synthetic-process-token"
BODY=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                 "params":{"name":TOOL,"arguments":{}}}).encode()
def check(condition,message):
    if not condition:
        raise AssertionError(message)

def child(fd, root):
    import uvicorn
    sock=socket.socket(fileno=fd)
    check(sock.family==socket.AF_INET and sock.getsockname()[0]=="127.0.0.1",
          "fixture socket not loopback")
    root=Path(root)
    def introspect(token):
        return json.dumps({"active":token==TOKEN,"iss":ISSUER,"sub":SUBJECT,
            "aud":[RESOURCE],"client_id":CLIENT,"scope":SCOPE,"token_type":"Bearer",
            "iat":NOW-10,"exp":NOW+300}).encode()
    # The file contents are real fixture bytes; UID separation is tested
    # elsewhere. This explicitly replaces the real GrantFile reader.
    grants=GrantFile(root,reader_gid=os.getegid(),owner_uid=os.geteuid())
    def current(_):
        return parse_grant((root/"synthetic-grant.json").read_bytes())
    boundary=HttpBoundary(server=dict(policy=Policy(True),introspect=introspect,
        grants=grants,trusted_clock=lambda:NOW,store=SnapshotStore(root/"snapshot")),
        audit_sink=AuditStoreFixture(root/"audit",owner_uid=os.geteuid(),clock=lambda:NOW),
        budget=Budget(),disclosure_check=lambda:True)
    with patch.object(GrantFile,"current",current):
        config=uvicorn.Config(OpsASGI(boundary),host="127.0.0.1",port=0,
            ssl_certfile=str(root/"cert.pem"),ssl_keyfile=str(root/"key.pem"),
            loop="asyncio",http="h11",ws="none",lifespan="on",proxy_headers=False,
            access_log=False,log_level="critical",server_header=False,date_header=False,
            limit_concurrency=16,timeout_keep_alive=1,timeout_graceful_shutdown=2)
        uvicorn.Server(config).run(sockets=[sock])

def parent():
    with tempfile.TemporaryDirectory(prefix="prp-ops-ci-") as tmp:
        root=Path(tmp)
        (root/"snapshot").mkdir(mode=0o700)
        (root/"audit").mkdir(mode=0o700)
        (root/"audit"/AUDIT_NAME).touch(mode=0o600)
        SnapshotStore(root/"snapshot").write(sample())
        grant={"version":1,"grantId":str(uuid.uuid4()),"issuer":ISSUER,
            "resource":RESOURCE,"client":CLIENT,"subject":SUBJECT,"environment":"staging",
            "scope":SCOPE,"issuedAt":NOW-20,"expiresAt":NOW+600,"active":True}
        path=root/"synthetic-grant.json"
        def write_grant(value):
            temp=root/"next-grant.json"
            temp.write_text(json.dumps(value))
            os.replace(temp,path)
        write_grant(grant)
        subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
            "-subj","/CN=127.0.0.1","-addext","subjectAltName=IP:127.0.0.1",
            "-keyout",str(root/"key.pem"),"-out",str(root/"cert.pem")],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        context=ssl.create_default_context(cafile=str(root/"cert.pem"))
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1",0))
            sock.listen(16)
            port=sock.getsockname()[1]
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--child",str(sock.fileno()),tmp],
                pass_fds=(sock.fileno(),),stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def request(method,target,body=None,token=None,duplicate=False):
                conn=http.client.HTTPSConnection("127.0.0.1",port,context=context,timeout=2)
                try:
                    conn.putrequest(method,target,skip_host=True,skip_accept_encoding=True)
                    conn.putheader("Host","ops.invalid")
                    if body is not None:
                        conn.putheader("Content-Type","application/json")
                        conn.putheader("Accept","application/json, text/event-stream")
                        conn.putheader("Content-Length",str(len(body)))
                    if token is not None:
                        conn.putheader("Authorization","Bearer "+token)
                    if duplicate:
                        conn.putheader("Authorization","Bearer other")
                    conn.endheaders(body)
                    resp=conn.getresponse()
                    raw=resp.read(32769)
                    check(len(raw)<=32768,"response bound")
                    return resp.status,raw
                finally:
                    conn.close()
            try:
                end=time.monotonic()+10
                while True:
                    check(process.poll() is None,"fixture process exited")
                    try:
                        status,raw=request("GET",METADATA_PATH)
                        check(status==200 and json.loads(raw)["resource"]==RESOURCE,"metadata mismatch")
                        break
                    except (OSError,http.client.HTTPException):
                        if time.monotonic()>=end:
                            raise
                        time.sleep(.05)
                check(request("POST","/mcp",BODY)==(401,b""),"missing bearer not denied")
                status,raw=request("POST","/mcp",BODY,TOKEN)
                check(status==200 and json.loads(raw)["result"]["structuredContent"]["status"]=="fresh",
                      "synthetic snapshot failed")
                check(request("POST","/mcp",BODY,TOKEN,duplicate=True)==(400,b""),"duplicate not denied")
                check(request("POST","/mcp",b"x"*4097,TOKEN)==(413,b""),"oversized body not denied")
                write_grant(dict(grant,active=False))
                check(request("POST","/mcp",BODY,TOKEN)==(401,b""),"revocation not denied")
                records=[json.loads(line) for line in (root/"audit"/AUDIT_NAME).read_bytes().splitlines()]
                check(any(row["route"]=="mcp" and row["outcome"]=="handled" for row in records),"audit missing")
                check(all(TOKEN not in json.dumps(row) for row in records),"audit secret leak")
                print("OPS_LOOPBACK_TLS_SMOKE=PASS")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

if __name__=="__main__":
    if len(sys.argv)==1:
        parent()
    elif len(sys.argv)==4 and sys.argv[1]=="--child":
        child(int(sys.argv[2]),sys.argv[3])
    else:
        raise SystemExit(78)
