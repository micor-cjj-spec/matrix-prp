"""Offline OAuth profile tests: actual SDK and exact RFC7662 adapter.

HTTPS issuer transport is replaced by a synthetic response. No DNS/network,
real OAuth client, tokens, user or Tunnel are created.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
from urllib.parse import parse_qs
import uuid

from admin_grant import record, digest, plan
from auth_adapter import GrantFile
from audit_store import AuditStoreFixture
from profile_config import approved_profile
from query_contract import CLIENT, SCOPE
from owner_gateway import FixedGrafanaQueryAdapter, QUERIES
from profile_app import compose
from snapshot_contract import SnapshotStore
from starlette.testclient import TestClient

ISSUER = "https://issuer.example.net/realms/prp-ops-staging"
RESOURCE = "https://ops.example.net/mcp"
SUBJECT = "offline-owner-profile"
CLIENT_ID = "prp-ops-staging-resource"
TOKEN = "offline-fixture-token"
SECRET = "offline-fixture-secret"


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("OBS_P43B_CASE=" + label + ":PASS", flush=True)


def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted" or os.geteuid() == 0:
        raise SystemExit("disposable nonroot hosted CI only")
    with tempfile.TemporaryDirectory(prefix="p43b-") as t:
        root = Path(t)
        path = root / "approved"
        path.mkdir()
        path.chmod(0o755)
        now = int(time.time()) // 30 * 30
        raw = json.dumps(dict(version=1, environment="staging", issuer=ISSUER,
            resource=RESOURCE, subject=SUBJECT, introspectionClientId=CLIENT_ID)).encode()
        def install(name, data, mode="0644", gid=0):
            source = root / "source"
            source.write_bytes(data)
            subprocess.run(["sudo","-n","install","-o","0","-g",str(gid),"-m",mode,
                           str(source),str(path/name)],check=True)
        install("profile.json", raw)
        subprocess.run(["sudo","-n","chown","0:0",str(path)],check=True)
        read = lambda: approved_profile(path)
        check(read() is None, "missing-profile-approval")
        marker = ("profile-sha256="+digest(raw)+"\n").encode()
        install("ENABLE_MCP_PROFILE", marker)
        profile = read()
        check(profile is not None and profile.identity.resource == RESOURCE, "root-owned-profile-approved")
        gid = os.getegid()
        grant_raw = record(str(uuid.uuid4()),now-20,now+300,True,profile.identity)
        install("grant.json",grant_raw,"0640",gid)
        grants = GrantFile(path,reader_gid=gid,profile=profile.identity)
        check(grants.current().active and not os.access(path/"grant.json",os.W_OK), "actual-readonly-grant")
        audit = root/"audit"
        audit.mkdir(mode=0o700)
        (audit/"access.jsonl").touch(mode=0o600)
        snapshot = root/"snapshot"
        snapshot.mkdir(mode=0o700)
        clock = lambda: now
        claims = dict(active=True,iss=ISSUER,sub=SUBJECT,aud=[RESOURCE],
                      client_id=CLIENT,scope=SCOPE,token_type="Bearer",iat=now-10,exp=now+200)
        seen, calls = [], []
        class Response:
            status = 200
            def getheader(self,k,d=""):
                return "application/json" if k=="Content-Type" else d
            def read(self,n):
                return json.dumps(claims).encode()
        class Connection:
            def __init__(self,host,port,timeout,context):
                check(host=="issuer.example.net" and port==443 and timeout==2
                      and context.check_hostname and context.verify_mode==2, "pinned-tls-introspection-endpoint")
            def request(self,method,path,body,headers):
                assert method=="POST" and path=="/realms/prp-ops-staging/protocol/openid-connect/token/introspect"
                assert headers["Authorization"]=="Basic "+base64.b64encode((CLIENT_ID+":"+SECRET).encode()).decode()
                assert parse_qs(body.decode())=={"token":[TOKEN],"token_type_hint":["access_token"]}
                seen.append(True)
            def getresponse(self):
                return Response()
            def close(self):
                pass
        def rpc(method, params):
            calls.append(params)
            assert method=="tools/call" and params["name"]=="query_prometheus"
            assert params["arguments"]["expr"]==QUERIES["memory_available_bytes"]
            return {"jsonrpc":"2.0","result":{"structuredContent":{"data":[
                {"metric":{"instance":"fixture-node","environment":"synthetic"},"values":[[now,"1024"]]}]}}}
        args=dict(grants=grants,query_adapter=FixedGrafanaQueryAdapter(rpc,datasource_uid="prp-synthetic",clock=clock),
                  audit_sink=AuditStoreFixture(audit,owner_uid=os.geteuid(),clock=clock),
                  secret_reader=lambda:SECRET,clock=clock,store=SnapshotStore(snapshot),read_profile=read)
        with patch("auth_adapter.http.client.HTTPSConnection", Connection):
            app=compose(**args)
            with TestClient(app,base_url="https://ops.example.net") as client:
                headers={"Host":"ops.example.net","Authorization":"Bearer "+TOKEN,
                    "Accept":"application/json, text/event-stream","MCP-Protocol-Version":"2025-06-18"}
                meta=client.get("/.well-known/oauth-protected-resource/mcp")
                check(meta.status_code==200 and meta.json()["resource"]==RESOURCE
                      and meta.json()["authorization_servers"]==[ISSUER], "profile-bound-sdk-metadata")
                def call(h=None):
                    return client.post("/mcp",headers=headers if h is None else h,json={
                        "jsonrpc":"2.0","id":1,"method":"tools/call","params":{
                            "name":"prp_observability_query","arguments":{"metric":"memory_available_bytes","window":"5m"}}})
                unauthorized=call({k:v for k,v in headers.items() if k!="Authorization"})
                check(unauthorized.status_code==401 and RESOURCE.rsplit("/",1)[0] in unauthorized.headers.get("www-authenticate",""),
                      "profile-bound-401-challenge")
                valid=call()
                check(valid.status_code==200 and valid.json()["result"]["structuredContent"]["samples"]==[[now,1024.0]]
                      and len(calls)==1 and len(seen)>=3, "profile-introspection-fixed-query")
                for key,value in (("aud",["https://foreign.example.net/mcp"]),("iss","https://foreign.example.net"),
                                  ("sub","foreign"),("client_id","other"),("scope","other"),("active",False),
                                  ("exp",now-1),("iat",now-21)):
                    old=claims[key]
                    claims[key]=value
                    check(call().status_code==401 and len(calls)==1,"deny-"+key)
                    claims[key]=old
                check(call({**headers,"Host":"foreign.example.net"}).status_code==400 and len(calls)==1,"wrong-host-denied")
                check(call(list(headers.items())+[("Authorization","Bearer duplicate")]).status_code==400
                      and len(calls)==1,"duplicate-auth-denied")
                install("grant.json",plan(grant_raw,"revoke",now=now,approved=True,profile=profile.identity),"0640",gid)
                check(call().status_code==401 and len(calls)==1,"root-grant-revocation")
                install("ENABLE_MCP_PROFILE",b"invalid\n")
                check(call().status_code==503 and len(calls)==1,"profile-digest-change-denied")
        # Restore directory ownership only for disposable cleanup.
        subprocess.run(["sudo","-n","chown",str(os.geteuid())+":"+str(gid),str(path)],check=True)
        check(TOKEN not in (audit/"access.jsonl").read_text() and SECRET not in (audit/"access.jsonl").read_text(),
              "audit-no-credentials")
        print("OBS_P43B_PROFILE=PASS; LIVE_ISSUER_TUNNEL=NOT_ENABLED",flush=True)


if __name__=="__main__":
    main()
