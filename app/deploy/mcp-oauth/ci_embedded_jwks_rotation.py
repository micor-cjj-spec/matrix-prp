#!/usr/bin/env python3
"""Disposable CI Keycloak only: two-key embedded JWKS rotation and rollback."""
import json
import secrets
from urllib.parse import quote
from cryptography.hazmat.primitives.asymmetric import rsa
from ci_embedded_jwks_token import b64, TOKEN, TYPE, BASE
from ci_chatgpt_cimd_pkce import REALM_ADMIN, request, admin_token
import os
import subprocess
import time
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private.public_key().public_numbers()
    kid = "ci-rotation-" + secrets.token_hex(8)
    return private, {"kty":"RSA","use":"sig","alg":"RS256","kid":kid,
        "n":b64(pub.n.to_bytes((pub.n.bit_length()+7)//8,"big")),
        "e":b64(pub.e.to_bytes((pub.e.bit_length()+7)//8,"big"))}

def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or not os.getenv("RUNNER_TEMP") or BASE != "http://127.0.0.1:18080":
        raise RuntimeError("CI_ONLY")
    result = subprocess.run(["docker","inspect","--format",
        '{{.Name}}|{{.State.Running}}|{{.Config.Image}}|{{index .Config.Labels "prp.disposable-ci"}}',
        "prp-mcp-keycloak-ci"],capture_output=True,text=True,timeout=8,check=False)
    parts = result.stdout.strip().split("|")
    if result.returncode or len(parts)!=4 or parts[0]!="/prp-mcp-keycloak-ci" or parts[1]!="true" or parts[3]!="true" or parts[2] not in (
        "quay.io/keycloak/keycloak:26.8.0","quay.io/keycloak/keycloak:26.8.1"):
        raise RuntimeError("DISPOSABLE_CI_CONTAINER_REQUIRED")
    client_id="ci-embedded-rotation-"+secrets.token_hex(8)
    def make_jwt(key,kid):
        now=int(time.time())
        header={"alg":"RS256","kid":kid,"typ":"JWT"}
        claims={"iss":client_id,"sub":client_id,"aud":TOKEN,"iat":now,"nbf":now-2,
                "exp":now+90,"jti":secrets.token_urlsafe(20)}
        msg=".".join(b64(json.dumps(item,separators=(",",":")).encode()) for item in (header,claims))
        return msg+"."+b64(key.sign(msg.encode(),padding.PKCS1v15(),hashes.SHA256()))
    old_key,old_jwk=keypair()
    new_key,new_jwk=keypair()
    admin=admin_token()
    clients_url=REALM_ADMIN+"/clients"
    lookup=clients_url+"?clientId="+quote(client_id,safe="")
    status,_,raw=request(lookup,bearer=admin)
    if status!=200 or any(c.get("clientId")==client_id for c in json.loads(raw)):
        raise RuntimeError("CLIENT_ALREADY_EXISTS")
    def jwks(keys):
        return json.dumps({"keys":keys},separators=(",",":"))
    candidate={"clientId":client_id,"enabled":True,"protocol":"openid-connect",
        "publicClient":False,"clientAuthenticatorType":"client-jwt",
        "serviceAccountsEnabled":True,"standardFlowEnabled":False,
        "directAccessGrantsEnabled":False,"fullScopeAllowed":False,
        "attributes":{"use.jwks.url":"false","use.jwks.string":"true",
            "jwks.string":jwks([old_jwk]),"token.endpoint.auth.signing.alg":"RS256"}}
    status,_,_=request(clients_url,method="POST",json_body=candidate,bearer=admin)
    if status!=201:
        raise RuntimeError("CI_CREATE_FAILED_"+str(status))
    try:
        status,_,raw=request(lookup,bearer=admin)
        matches=[c for c in json.loads(raw) if c.get("clientId")==client_id] if status==200 else []
        if len(matches)!=1:
            raise RuntimeError("CI_LOOKUP_FAILED")
        client_uuid=matches[0]["id"]
        def set_keys(keys):
            status,_,raw=request(clients_url+"/"+client_uuid,bearer=admin)
            if status!=200:
                raise RuntimeError("CLIENT_GET_FAILED")
            body=json.loads(raw)
            attrs=body.get("attributes") or {}
            attrs.update({"use.jwks.url":"false","use.jwks.string":"true","jwks.string":jwks(keys)})
            body["attributes"]=attrs
            status,_,_=request(clients_url+"/"+client_uuid,method="PUT",json_body=body,bearer=admin)
            if status!=204:
                raise RuntimeError("CI_CLIENT_LOCAL_UPDATE_FAILED_"+str(status))
        def assert_auth(name,key,kid,valid):
            status,_,raw=request(TOKEN,method="POST",form={
                "grant_type":"client_credentials","client_id":client_id,
                "client_assertion_type":TYPE,"client_assertion":make_jwt(key,kid)})
            try: payload=json.loads(raw)
            except ValueError: payload={}
            if valid:
                if status!=200 or not payload.get("access_token"):
                    raise RuntimeError(name+"_REJECTED_"+str(status))
            elif status not in (400,401) or payload.get("error")!="invalid_client":
                raise RuntimeError(name+"_NOT_DENIED_"+str(status))
            print("PASS ROTATION_"+name)
        assert_auth("initial_old",old_key,old_jwk["kid"],True)
        set_keys([old_jwk,new_jwk])
        assert_auth("overlap_old",old_key,old_jwk["kid"],True)
        assert_auth("overlap_new",new_key,new_jwk["kid"],True)
        assert_auth("unknown_kid",new_key,"unknown-kid",False)
        set_keys([new_jwk])
        assert_auth("removed_old",old_key,old_jwk["kid"],False)
        assert_auth("new_only",new_key,new_jwk["kid"],True)
        set_keys([old_jwk])
        assert_auth("rollback_old",old_key,old_jwk["kid"],True)
        assert_auth("rollback_new_denied",new_key,new_jwk["kid"],False)
        print("EMBEDDED_JWKS_ROTATION_CI_PROOF=PASS")
    finally:
        status,_,raw=request(lookup,bearer=admin)
        matches=[c for c in json.loads(raw) if c.get("clientId")==client_id] if status==200 else []
        if len(matches)!=1:
            raise RuntimeError("CI_CLEANUP_LOOKUP_FAILED")
        status,_,_=request(clients_url+"/"+matches[0]["id"],method="DELETE",bearer=admin)
        if status!=204:
            raise RuntimeError("CI_CLEANUP_FAILED")

if __name__=="__main__":
    main()
