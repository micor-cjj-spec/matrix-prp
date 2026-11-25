"""Non-deployable SDK substitution spike, synthetic ASGI HTTP only.

Run in disposable CI; no host collectors, network issuer, real data, listener,
configuration, credential or service entry. Does not replace #424.
"""
import json
import os
import tempfile
import time
import uuid
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

from auth_adapter import GrantFile, authorize_request, parse_grant
from mcp_adapter import tools_list, tools_call
from query_contract import ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE, TOOL, Policy
from snapshot_contract import SnapshotStore
from test_snapshot_contract import sample

def check(condition,message):
    if not condition:
        raise AssertionError(message)

def mark(name):
    print("OPS_SDK_CASE="+name+":PASS",flush=True)

def main():
    check(version("mcp")=="2.3.0","unexpected SDK version")
    print("OPS_SDK_VERSION="+version("mcp"),flush=True)
    now=int(time.time())
    valid="synthetic-sdk-only"
    revoked=False
    with tempfile.TemporaryDirectory(prefix="ops-sdk-spike-") as tmp:
        root=Path(tmp)
        root.chmod(0o700)
        store=SnapshotStore(root)
        store.write(sample(now))
        grant_id=str(uuid.uuid4())
        def grant():
            return parse_grant(json.dumps({"version":1,"grantId":grant_id,
                "issuer":ISSUER,"resource":RESOURCE,"client":CLIENT,"subject":SUBJECT,
                "environment":"staging","scope":SCOPE,"issuedAt":now-20,
                "expiresAt":now+600,"active":not revoked}).encode())
        grants=GrantFile(root,reader_gid=os.getegid(),owner_uid=os.geteuid())
        def introspect(token):
            claims={"active":True,"iss":ISSUER,"sub":SUBJECT,"aud":[RESOURCE],
                    "client_id":CLIENT,"scope":SCOPE,"token_type":"Bearer",
                    "iat":now-10,"exp":now+300}
            if token=="wrong-scope":
                claims["scope"]="prp.tasks.read"
            elif token=="wrong-audience":
                claims["aud"]=["https://other.invalid/mcp"]
            elif token=="wrong-subject":
                claims["sub"]="other"
            elif token=="expired":
                claims["exp"]=now
            elif token!=valid:
                claims["active"]=False
            return json.dumps(claims).encode()
        config=dict(policy=Policy(True),introspect=introspect,grants=grants,
                    trusted_clock=lambda:now,store=store)
        def authorized(token):
            return authorize_request("Bearer "+token,**config)
        class Verifier(TokenVerifier):
            async def verify_token(self, token):
                try:
                    identity=authorized(token).identity_provider()
                    return AccessToken(token=token,client_id=identity.client,
                        scopes=list(identity.scopes),resource=identity.audience,
                        subject=identity.subject,expires_at=identity.expires_at,
                        claims={"iss":identity.issuer})
                except Exception:
                    return None
        descriptor=tools_list()["tools"][0]
        async def list_tools(ctx,params):
            return types.ListToolsResult(tools=[types.Tool.model_validate(descriptor)])
        async def call_tool(ctx,params):
            try:
                token=get_access_token()
                check(token is not None,"no verified token")
                server_context=authorized(token.token)
                # Existing strict contract rejects unknown tools and nonempty args.
                value=tools_call({"name":params.name,
                    "arguments":params.arguments},server_context)
                return types.CallToolResult.model_validate(value)
            except Exception:
                return types.CallToolResult(content=[types.TextContent(
                    type="text",text="Read-only status query denied.")],isError=True)
        server=Server("prp-ops-sdk-spike",on_list_tools=list_tools,on_call_tool=call_tool,
                      get_tool_input_schema=lambda name: descriptor["inputSchema"] if name==TOOL else None)
        app=server.streamable_http_app(stateless_http=True,json_response=True,
            max_request_body_size=4096,token_verifier=Verifier(),
            auth=AuthSettings(issuer_url=ISSUER,resource_server_url=RESOURCE,
                required_scopes=[SCOPE],validate_token_resource=True),
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                allowed_hosts=["ops.invalid"],allowed_origins=["https://chatgpt.com"]))
        headers=[("Accept","application/json, text/event-stream"),
                 ("Content-Type","application/json"),("MCP-Protocol-Version","2025-06-18")]
        with patch.object(grants,"current",side_effect=grant),TestClient(app,base_url="https://ops.invalid") as client:
            def post(method,params,token=valid,extra=()):
                hs=list(headers)
                if token is not None:
                    hs.append(("Authorization","Bearer "+token))
                hs.extend(extra)
                return client.post("/mcp",headers=hs,json={"jsonrpc":"2.0","id":1,
                    "method":method,"params":params})
            def deny(response):
                check(response.status_code>=400 or response.json().get("error") is not None or
                    response.json().get("result",{}).get("isError") is True,"request unexpectedly allowed")
                check("structuredContent" not in response.text or "fresh" not in response.text,
                      "denial exposed fresh data")
            meta=client.get("/.well-known/oauth-protected-resource/mcp")
            check(meta.status_code==200 and meta.json()["resource"]==RESOURCE and
                  ISSUER in meta.json()["authorization_servers"] and SCOPE in meta.json()["scopes_supported"],"metadata mismatch")
            mark("sdk-generated-resource-metadata")
            missing=post("tools/list",{},None)
            check(missing.status_code==401 and "resource_metadata" in missing.headers.get("www-authenticate",""),"challenge missing")
            mark("sdk-generated-bearer-challenge")
            for token in ("wrong-scope","wrong-audience","wrong-subject","expired","invalid"):
                deny(post("tools/list",{},token))
                mark(token)
            init=post("initialize",{"protocolVersion":"2025-06-18","capabilities":{},
                        "clientInfo":{"name":"sdk-spike","version":"1"}})
            check(init.status_code==200 and init.json().get("result",{}).get("protocolVersion")=="2025-06-18","legacy initialization failed")
            mark("legacy-protocol-initialize")
            found=post("tools/list",{}).json()["result"]["tools"]
            check(len(found)==1 and found[0]["name"]==TOOL and
                  found[0]["inputSchema"]["additionalProperties"] is False and
                  found[0]["annotations"]["readOnlyHint"] is True,"tool surface mismatch")
            mark("exact-readonly-tool-discovery")
            args={"name":TOOL,"arguments":{}}
            response=post("tools/call",args)
            check(response.status_code==200 and response.json()["result"]["structuredContent"]["status"]=="fresh","snapshot mismatch")
            mark("existing-snapshot-via-sdk")
            deny(post("tools/call",{"name":TOOL,"arguments":{"command":"ignored-fixture"}}))
            deny(post("tools/call",{"name":"unknown","arguments":{}}))
            mark("argument-and-tool-allowlist")
            deny(post("tools/call",args,extra=[("Origin","https://other.invalid")]))
            mark("origin-denial")
            store.write(sample(now-121))
            stale=post("tools/call",args).json()["result"]["structuredContent"]
            check(stale["status"]=="stale" and stale["cpu"] is None and stale["memory"] is None
                  and stale["disk"] is None,"stale metric leakage")
            mark("existing-freshness-contract")
            store.write(sample(now))
            # Probe SDK-only behavior, not a pass requirement: existing raw
            # HTTP gate still required if it normalizes multiple auth headers.
            dup=post("tools/call",args,extra=[("Authorization","Bearer other")])
            try:
                deny(dup)
                print("OPS_SDK_DUPLICATE_AUTH=DENIED",flush=True)
            except AssertionError:
                print("OPS_SDK_DUPLICATE_AUTH=GAP",flush=True)
            revoked=True
            deny(post("tools/call",args))
            mark("grant-revocation")
    print("OPS_SDK_SPIKE=PASS",flush=True)

if __name__=="__main__":
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("RUNNER_ENVIRONMENT")!="github-hosted":
        raise SystemExit(78)
    main()
