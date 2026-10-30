#!/usr/bin/env python3
"""Disposable CI-only preflight for exact ChatGPT inline-JWKS auth-code shape.

This is NOT a completed authorization-code exchange: a separate browser
login/consent/code fixture and signed assertion redemption are still required.
"""
import os
import subprocess
import json
from urllib.parse import quote
from ci_chatgpt_cimd_pkce import REALM_ADMIN, AUTH_URL, request, admin_token, require_pkce_result
from review_chatgpt_inline_jwks import review_inline_candidate
from ci_embedded_jwks_rotation import keypair

CLIENT_ID = "https://chatgpt.com/oauth/client.json"

def disposable_only():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("CI_ONLY")
    result=subprocess.run(["docker","inspect","--format",
        '{{.Name}}|{{.State.Running}}|{{.Config.Image}}|{{index .Config.Labels "prp.disposable-ci"}}',
        "prp-mcp-keycloak-ci"],capture_output=True,text=True,timeout=8,check=False)
    parts=result.stdout.strip().split("|")
    if result.returncode or len(parts)!=4 or parts[0]!="/prp-mcp-keycloak-ci" or parts[1]!="true" or parts[3]!="true":
        raise RuntimeError("DISPOSABLE_CONTAINER_REQUIRED")
    if parts[2] not in ("quay.io/keycloak/keycloak:26.8.0","quay.io/keycloak/keycloak:26.8.1"):
        raise RuntimeError("UNEXPECTED_CI_IMAGE")

def main():
    disposable_only()
    _, public_key=keypair()
    reviewed=review_inline_candidate({"keys":[public_key]})
    candidate=reviewed["candidate"]
    if candidate["clientId"]!=CLIENT_ID or candidate["standardFlowEnabled"] is not True:
        raise RuntimeError("CLIENT_SHAPE_INVALID")
    if candidate["serviceAccountsEnabled"] is not False:
        raise RuntimeError("SERVICE_GRANT_NOT_DISABLED")
    token=admin_token()
    endpoint=REALM_ADMIN+"/clients"
    status,_,raw=request(endpoint+"?clientId="+quote(CLIENT_ID,safe=""),bearer=token)
    if status!=200 or any(x.get("clientId")==CLIENT_ID for x in json.loads(raw)):
        raise RuntimeError("EXACT_CLIENT_ALREADY_EXISTS")
    status,_,_=request(endpoint,method="POST",json_body=candidate,bearer=token)
    if status!=201:
        raise RuntimeError("DISPOSABLE_CLIENT_CREATE_REJECTED")
    try:
        status,_,raw=request(endpoint+"?clientId="+quote(CLIENT_ID,safe=""),bearer=token)
        found=[x for x in json.loads(raw) if x.get("clientId")==CLIENT_ID] if status==200 else []
        if len(found)!=1:
            raise RuntimeError("CLIENT_READBACK_FAILED")
        client_id=found[0]["id"]
        status,_,raw=request(endpoint+"/"+client_id,bearer=token)
        persisted=json.loads(raw) if status==200 else {}
        attrs=persisted.get("attributes") or {}
        if (attrs.get("use.jwks.string")!="true" or attrs.get("use.jwks.url")!="false"
                or persisted.get("redirectUris")!=candidate["redirectUris"]):
            raise RuntimeError("INLINE_JWKS_NOT_PERSISTED")
        require_pkce_result("S256",scope="openid offline_access prp.tasks.read")
        for mode in ("missing","plain"):
            require_pkce_result(mode)
        print("PASS EXACT_INLINE_JWKS_PKCE_AUTH_ENTRY_CI")
        print("AUTH_CODE_REDEMPTION_NOT_TESTED")
    finally:
        status,_,raw=request(endpoint+"?clientId="+quote(CLIENT_ID,safe=""),bearer=token)
        found=[x for x in json.loads(raw) if x.get("clientId")==CLIENT_ID] if status==200 else []
        if len(found)!=1:
            raise RuntimeError("DISPOSABLE_CLEANUP_LOOKUP_FAILED")
        status,_,_=request(endpoint+"/"+found[0]["id"],method="DELETE",bearer=token)
        if status!=204:
            raise RuntimeError("DISPOSABLE_CLEANUP_FAILED")

if __name__=="__main__":
    try:
        main()
    except Exception:
        print("FAIL EXACT_INLINE_JWKS_PKCE_AUTH_ENTRY_CI")
        raise SystemExit(1) from None
