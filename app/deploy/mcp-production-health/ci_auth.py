#!/usr/bin/env python3
"""DISPOSABLE CI only. Actual Keycloak/PostgreSQL, exact production issuer/resource.

Local TLS trust and a synthetic client signing certificate are test-only runtime
substitutions. No private key/user/CA is part of the image or production import.
Never calls a real ChatGPT callback or a production MCP/database.
"""
import base64
import hashlib
import http.client
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPSHandler, HTTPCookieProcessor, ProxyHandler
from build_realm import build
from contract import *
from render_auth_nginx import render

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'mcp-oauth'))
import ci_pkce_browser as flow
from ci_static_client_jwt import create_keypair, assertion, ASSERTION_TYPE, openssl
from oauth_token_check import check_token, _b64url

ADMIN_BASE='http://127.0.0.1:18080'
TOKEN=ISSUER+'/protocol/openid-connect/token'
RESULTS=[]
def check(name,ok):
    if not ok:raise RuntimeError(name)
    RESULTS.append({'name':name,'passed':True});print('PASS HEALTH_AUTH '+name,flush=True)

def command(args,**kwargs):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=kwargs.pop('timeout',60),**kwargs)
    if p.returncode:raise RuntimeError('LOCAL_PROCESS_FAILED_'+Path(args[0]).name.upper())
    return p.stdout

def admin(path,*,token=None,data=None,method=None):
    if not path.startswith(('/realms/master/','/admin/realms/')):raise RuntimeError('ADMIN_PATH')
    h={'Host':'auth.micor.top','X-Forwarded-Proto':'https','X-Forwarded-Host':'auth.micor.top'}
    if token:h['Authorization']='Bearer '+token
    payload=None
    if data is not None:
        if path.startswith('/realms/master/'):
            payload=urlencode(data).encode();h['Content-Type']='application/x-www-form-urlencoded'
        else:payload=json.dumps(data).encode();h['Content-Type']='application/json'
    try:r=build_opener(ProxyHandler({})).open(Request(ADMIN_BASE+path,data=payload,headers=h,method=method),timeout=10)
    except HTTPError as e:r=e
    with r:
        raw=r.read(250001)
        if len(raw)>250000:raise RuntimeError('ADMIN_OUTPUT_LIMIT')
        return r.status,json.loads(raw) if raw else None

def public_opener(cafile):
    context=ssl.create_default_context(cafile=str(cafile))
    class LocalTLS(http.client.HTTPSConnection):
        def connect(self):
            if self.host!='auth.micor.top':raise RuntimeError('NONLOCAL_TARGET_REFUSED')
            self.sock=context.wrap_socket(socket.create_connection(('127.0.0.1',18446),self.timeout),server_hostname=self.host)
    class LocalHandler(HTTPSHandler):
        def https_open(self,req):return self.do_open(LocalTLS,req,context=context)
    return build_opener(ProxyHandler({}),LocalHandler(context=context),HTTPCookieProcessor(CookieJar()),flow.SafeRedirect())

def token(opener,key,*,code=None,verifier=None,refresh=None,**changes):
    p={'grant_type':'refresh_token' if refresh else 'authorization_code','client_id':CLIENT,
       'client_assertion_type':ASSERTION_TYPE,'client_assertion':assertion(key,aud=TOKEN,issuer=CLIENT,subject=CLIENT),
       'resource':RESOURCE}
    if refresh:p['refresh_token']=refresh
    else:p.update(code=code,code_verifier=verifier,redirect_uri=REDIRECT)
    p.update(changes)
    if p.get('resource') is None:p.pop('resource',None)
    r=flow.request(opener,TOKEN,data=p,form=True)
    return r[0],json.loads(r[2]) if r[0]==200 else None

def verify(tokens,jwks):
    raw=tokens['access_token'];check_token(raw,jwks,issuer=ISSUER,resource=RESOURCE,client_id=CLIENT,required_scope='prp.wellness.read')
    c=json.loads(_b64url(raw.split('.')[1]));aud=c['aud'];aud=[aud] if isinstance(aud,str) else aud
    check('signed_health_scope_subject_and_exact_audience',set(c['scope'].split())==set(SCOPES) and aud==[RESOURCE] and bool(c['sub']))
    return c['sub']

def negative_authorization(opener,**changes):
    p={'client_id':CLIENT,'response_type':'code','redirect_uri':REDIRECT,'scope':' '.join(SCOPES),
       'resource':RESOURCE,'code_challenge_method':'S256','code_challenge':'A'*43,'state':secrets.token_urlsafe(24)}
    p.update(changes)
    try:
        r=flow.request(opener,ISSUER+'/protocol/openid-connect/auth?'+urlencode(p),form=True)
        return r[0] in (400,401,403)
    except flow.CallbackReceived as c:
        q=parse_qs(urlsplit(c.url).query)
        return 'code' not in q and q.get('error',[None])[0] in ('invalid_request','invalid_scope','invalid_client','unauthorized_client')

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_OS')!='Linux' or not os.environ.get('RUNNER_TEMP'):
        raise RuntimeError('DISPOSABLE_GITHUB_RUNNER_REQUIRED')
    flow.ISSUER=ISSUER;flow.RESOURCE=RESOURCE;flow.CLIENT=CLIENT;flow.CALLBACK=REDIRECT
    with tempfile.TemporaryDirectory(prefix='prp-health-auth-',dir=os.environ['RUNNER_TEMP']) as folder:
        root=Path(folder);root.chmod(0o700)
        realm=root/'realm';realm.mkdir();(realm/'health.json').write_text(json.dumps(build()))
        # A first import contains no synthetic identities/keys. All substitutions below use CI admin only.
        admin_password=secrets.token_urlsafe(36);db_password=secrets.token_urlsafe(36)
        for value in (admin_password,db_password):print('::add-mask::'+value,flush=True)
        env=root/'keycloak.env';env.write_text('KC_DB=postgres\nKC_DB_URL=jdbc:postgresql://127.0.0.1:15432/prp_health_auth\nKC_DB_USERNAME=prp_health_auth\nKC_DB_PASSWORD='+db_password+'\nKC_BOOTSTRAP_ADMIN_USERNAME=ci-health-admin\nKC_BOOTSTRAP_ADMIN_PASSWORD='+admin_password+'\n');env.chmod(0o600)
        pg=root/'postgres.env';pg.write_text('POSTGRES_DB=prp_health_auth\nPOSTGRES_USER=prp_health_auth\nPOSTGRES_PASSWORD='+db_password+'\n');pg.chmod(0o600)
        cert=root/'ci-tls.pem';tlskey=root/'ci-tls.key'
        openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',tlskey,'-out',cert,'-subj','/CN=auth.micor.top','-addext','subjectAltName=DNS:auth.micor.top')
        tlskey.chmod(0o600)
        conf=root/'nginx.conf';conf.write_text('pid '+str(root/'nginx.pid')+';\nerror_log stderr emerg;\nevents {}\nhttp {\n'+render(port=18446,upstream=18080,cert=str(cert),key=str(tlskey))+'}\n')
        nginx=None
        try:
            command(['docker','run','-d','--name','prp-health-auth-pg-ci','--memory','256m','-p','127.0.0.1:15432:5432','--env-file',str(pg),'--tmpfs','/var/lib/postgresql/data','postgres:17.6-alpine'])
            for _ in range(40):
                p=subprocess.run(['docker','exec','prp-health-auth-pg-ci','pg_isready','-U','prp_health_auth'],capture_output=True,timeout=3)
                if p.returncode==0:break
                time.sleep(1)
            command(['docker','pull','quay.io/keycloak/keycloak:26.8.1'],timeout=120)
            base=json.loads(command(['docker','image','inspect','quay.io/keycloak/keycloak:26.8.1']))[0]['RepoDigests'][0]
            command(['docker','build','--build-arg','KEYCLOAK_BASE='+base,'-t','prp-health-auth-candidate:ci','-f',str(ROOT/'Dockerfile.auth'),str(ROOT)],timeout=180)
            command(['docker','run','-d','--name','prp-health-auth-kc-ci','--network','host','--memory','1g','--cap-drop','ALL','--security-opt','no-new-privileges','--env-file',str(env),'-v',str(realm)+':/opt/keycloak/data/import:ro','prp-health-auth-candidate:ci','start','--optimized','--import-realm','--http-enabled=true','--http-port=18080','--hostname=https://auth.micor.top','--proxy-headers=xforwarded','--proxy-trusted-addresses=127.0.0.1'])
            command(['nginx','-t','-p',str(root),' -c'.strip(),str(conf)])
            nginx=subprocess.Popen(['nginx','-p',str(root),'-c',str(conf),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            op=public_opener(cert)
            flow.wait_ready(op,ISSUER+'/.well-known/openid-configuration',max_seconds=150)
            meta=flow.json_response(flow.request(op,ISSUER+'/.well-known/openid-configuration'),'Health discovery')
            check('discovery_exact_health_no_registration',meta['issuer']==ISSUER and set(meta['scopes_supported'])==set(SCOPES) and not meta.get('registration_endpoint') and meta['code_challenge_methods_supported']==['S256'])
            s,a=admin('/realms/master/protocol/openid-connect/token',data={'grant_type':'password','client_id':'admin-cli','username':'ci-health-admin','password':admin_password});check('disposable_admin_ready',s==200);access=a['access_token']
            prefix='/admin/realms/'+REALM
            s,clients=admin(prefix+'/clients',token=access);check('realm_imported_only_three_enabled_clients',s==200 and len([c for c in clients if c['enabled']])==3)
            c=next(c for c in clients if c['clientId']==CLIENT)
            s,c=admin(prefix+'/clients/'+c['id'],token=access);check('registered_client_readback',s==200)
            check('production_registration_uses_official_jwks',c['attributes']['jwks.url']==JWKS and c['clientAuthenticatorType']=='client-jwt' and c['redirectUris']==[REDIRECT] and set(c['optionalClientScopes'])==set(SCOPES))
            key,certificate=create_keypair(root)
            # Only this ephemeral instance uses the synthetic signer. Production import/image unchanged.
            c['attributes']['use.jwks.url']='false';c['attributes'].pop('jwks.url');c['attributes']['jwt.credential.certificate']=certificate
            s,_=admin(prefix+'/clients/'+c['id'],token=access,data=c,method='PUT');check('explicit_ci_signer_substitution',s==204)
            password=secrets.token_urlsafe(24);print('::add-mask::'+password,flush=True)
            s,_=admin(prefix+'/users',token=access,data={'username':'synthetic-health-user','enabled':True,'credentials':[{'type':'password','value':password,'temporary':False}]},method='POST');check('synthetic_user_only',s==201)
            for name,changes in [('task_scope',{'scope':'prp.tasks.read'}),('finance_scope',{'scope':'prp.finance.read'}),('generic_write',{'scope':'prp.write.create'}),('offline_scope',{'scope':'offline_access'}),('wrong_redirect',{'redirect_uri':REDIRECT+'/'}),('wrong_resource',{'resource':'https://prp-test.micor.top/api/mcp'}),('plain_pkce',{'code_challenge_method':'plain'}),('wrong_client',{'client_id':'https://chatgpt.com/oauth/not-approved.json'})]:
                check('authorization_denies_'+name,negative_authorization(public_opener(cert),**changes))
            for path in ['/admin/','/realms/master/.well-known/openid-configuration','/realms/'+REALM+'/clients-registrations/openid-connect','/health']:
                check('public_path_denied_'+str(len(RESULTS)),flow.request(op,'https://auth.micor.top'+path)[0]==404)
            code,verifier=flow.code_pkce(op,'synthetic-health-user',password,' '.join(SCOPES))
            s,t=token(op,key,code=code,verifier='wrong-verifier');check('wrong_pkce_refused',s in (400,401))
            code,verifier=flow.code_pkce(op,'synthetic-health-user',password,' '.join(SCOPES))
            s,t=token(op,key,code=code,verifier=verifier,client_assertion=assertion(key,aud=TOKEN,issuer=CLIENT,subject=CLIENT,replace_signature=True));check('wrong_signature_refused',s in (400,401))
            code,verifier=flow.code_pkce(op,'synthetic-health-user',password,' '.join(SCOPES))
            s,t=token(op,key,code=code,verifier=verifier);check('private_jwt_pkce_code_exchange',s==200)
            jwks=flow.json_response(flow.request(op,ISSUER+'/protocol/openid-connect/certs'),'JWKS');subject=verify(t,jwks)
            s,_=token(op,key,code=code,verifier=verifier);check('authorization_code_replay_refused',s in (400,401))
            # Native code replay may invalidate the session. Do not reuse its refresh family.
            code,verifier=flow.code_pkce(public_opener(cert),'synthetic-health-user',password,' '.join(SCOPES))
            s,t=token(op,key,code=code,verifier=verifier);check('fresh_refresh_test_session',s==200)
            refresh=t.get('refresh_token');check('session_refresh_without_offline_access',bool(refresh))
            s,_=token(op,key,refresh=refresh,resource='https://prp-test.micor.top/api/mcp');check('refresh_other_resource_refused',s in (400,401))
            s,_=token(op,key,refresh=refresh,resource=None);check('refresh_missing_resource_refused',s in (400,401))
            s,new=token(op,key,refresh=refresh);check('health_refresh_rotates',s==200 and new.get('refresh_token')!=refresh)
            check('refresh_subject_bound',verify(new,jwks)==subject)
            s,_=token(op,key,refresh=refresh);check('old_refresh_replay_refused',s in (400,401))
            # Fresh session avoids depending on an invalidated refresh family after replay detection.
            code,verifier=flow.code_pkce(public_opener(cert),'synthetic-health-user',password,' '.join(SCOPES))
            s,fresh=token(op,key,code=code,verifier=verifier);check('fresh_session_exchange',s==200)
            s,_,_=flow.request(op,ISSUER+'/protocol/openid-connect/revoke',data={'client_id':CLIENT,'client_assertion_type':ASSERTION_TYPE,'client_assertion':assertion(key,aud=TOKEN,issuer=CLIENT,subject=CLIENT),'token':fresh['refresh_token'],'token_type_hint':'refresh_token'},form=True)
            check('refresh_revocation',s==200)
            s,_=token(op,key,refresh=fresh['refresh_token']);check('revoked_refresh_refused',s in (400,401))
            image=json.loads(command(['docker','image','inspect','prp-health-auth-candidate:ci']))[0]
            result={'checks':RESULTS,'passed':len(RESULTS),'failed':0,'image_id':image['Id'],'keycloak_base_digest':base,'policy_jar_sha256':hashlib.sha256((ROOT/'auth-policy/target/prp-production-health-policy.jar').read_bytes()).hexdigest(),'issuer':ISSUER,'resource':RESOURCE,'registration':'exact-pre-registered-not-dynamic-CIMD','actual_chatgpt_signature_verified':False,'official_jvm_jwks_fetch_verified':False,'production_changed':False}
            out=ROOT/'auth-candidate-result.safe.json';out.write_text(json.dumps(result,indent=2));print('HEALTH_AUTH_CANDIDATE_SUCCESS checks='+str(len(RESULTS)),flush=True)
        finally:
            if nginx:nginx.terminate();nginx.wait(timeout=10)
            for name in ['prp-health-auth-kc-ci','prp-health-auth-pg-ci']:
                subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)

if __name__=='__main__':
    try:main()
    except Exception as e:
        # Raw exception text can include an authorization URL or child-process arguments.
        safe=str(e)
        if not safe or len(safe)>110 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in safe):safe=type(e).__name__
        print('FAIL HEALTH_AUTH '+safe,flush=True);raise SystemExit(1) from None
