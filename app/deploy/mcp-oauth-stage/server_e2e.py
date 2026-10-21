"""Explicitly isolated server lab only. Never print tokens, cookies or payloads."""
import base64
import concurrent.futures
import copy
import http.client
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPSHandler, HTTPCookieProcessor, ProxyHandler

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'mcp-oauth'))
sys.path.insert(0,str(HERE.parent/'mcp-staging'))
import ci_pkce_browser as flow
from check_env import parse_env
from oauth_token_check import check_token

STATE=Path('/root/prp-mcp-oauth-stage')
REPORT=Path('/root/prp-mcp-phase2-evidence/oauth-tests.json')
flow.ISSUER='https://auth-test.micor.top/realms/prp-mcp'
flow.RESOURCE='https://prp-test.micor.top/api/mcp'
flow.ADMIN='https://auth-test.micor.top'
PRP='https://prp-test.micor.top'
ROWS=[]
CONTEXT=ssl.create_default_context(cafile=str(STATE/'certs/ca.pem'))


class LocalTLS(http.client.HTTPSConnection):
    def connect(self):
        if self.host not in ('auth-test.micor.top','prp-test.micor.top'):
            raise RuntimeError('Unexpected HTTPS destination')
        import socket
        self.sock=socket.create_connection(('127.0.0.1',18443),self.timeout)
        self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)


class LabHTTPS(HTTPSHandler):
    def https_open(self,req):
        return self.do_open(LocalTLS,req,context=CONTEXT)


def opener():
    return build_opener(ProxyHandler({}),LabHTTPS(context=CONTEXT),
                        HTTPCookieProcessor(CookieJar()),flow.SafeRedirect())


def record(name,status,expected,kind='server HTTP'):
    ok=status in expected
    ROWS.append({'name':name,'type':kind,'expected':expected,'actual':status,'passed':ok})
    REPORT.write_text(json.dumps({'tests':ROWS},indent=2))
    print(('PASS ' if ok else 'FAIL ')+name+' status='+str(status),flush=True)
    if not ok:raise RuntimeError('Recorded test failed')


def obj(response):
    if response[0]!=200:raise RuntimeError('Required JSON operation failed HTTP '+str(response[0]))
    return json.loads(response[2])


def claims(token):
    return json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'=='))


def mint(user,password,client=None):
    original=flow.CLIENT
    if client:flow.CLIENT=client
    try:
        op=opener();code,verifier=flow.code_pkce(op,user,password)
        response=flow.request(op,flow.ISSUER+'/protocol/openid-connect/token',form=True,data={
            'grant_type':'authorization_code','client_id':flow.CLIENT,'redirect_uri':flow.CALLBACK,
            'code':code,'code_verifier':verifier,'resource':flow.RESOURCE})
        return op,obj(response),code,verifier
    finally:flow.CLIENT=original


def rpc(op,token,method='tools/list',params=None):
    return flow.jsonrpc(op,token,7,method,params or {})


def admin_request(op,admin,path,data=None,method=None):
    return flow.request(op,flow.ADMIN+'/admin/realms/prp-mcp'+path,
                        bearer=admin,data=data,method=method)


def main():
    if STATE.stat().st_uid!=0 or (STATE/'.env').stat().st_mode&0o777!=0o600:
        raise RuntimeError('Private staging configuration required')
    env=parse_env((STATE/'.env').read_text())
    base=parse_env((HERE.parent/'mcp-staging/.env').read_text())
    op=opener()
    flow.wait_ready(op,flow.ISSUER+'/.well-known/openid-configuration',120)
    flow.wait_ready(op,PRP+'/api/health',60)
    metadata=obj(flow.request(op,flow.ISSUER+'/.well-known/openid-configuration'))
    assert metadata['issuer']==flow.ISSUER and 'S256' in metadata['code_challenge_methods_supported']
    assert metadata.get('authorization_response_iss_parameter_supported') is True
    protected=obj(flow.request(op,PRP+'/.well-known/oauth-protected-resource/api/mcp'))
    assert protected['resource']==flow.RESOURCE and protected['authorization_servers']==[flow.ISSUER]
    record('OIDC / protected-resource metadata and S256',200,[200])
    unauth=flow.request(op,flow.RESOURCE,data={'jsonrpc':'2.0','id':1,'method':'tools/list'})
    record('Missing access token',unauth[0],[401])
    admin=obj(flow.request(op,flow.ADMIN+'/realms/master/protocol/openid-connect/token',form=True,
              data={'grant_type':'password','client_id':'admin-cli','username':'stage_oauth_admin',
                    'password':env['OAUTH_ADMIN_PASSWORD']}))['access_token']
    boot=obj(flow.request(op,PRP+'/api/auth/login',data={
        'username':base['PRP_STAGE_ADMIN_USERNAME'],'password':base['PRP_STAGE_ADMIN_PASSWORD']}))['data']['token']
    suffix=secrets.token_hex(5)
    owners=[]
    for i in range(2):
        name='oauth_lab_'+suffix+str(i);password=secrets.token_urlsafe(32)
        response=admin_request(op,admin,'/users',{'username':name,'enabled':True,
            'emailVerified':True,'email':name+'@example.invalid','firstName':'Lab','lastName':'Test',
            'requiredActions':[],'credentials':[{'type':'password','value':password,'temporary':False}]})
        record('Create isolated issuer user '+str(i),response[0],[201])
        invitation=obj(flow.request(op,PRP+'/api/auth/invitations',bearer=boot,data={}))['data']['code']
        session=obj(flow.request(op,PRP+'/api/auth/register',data={
            'username':name,'password':password,'displayName':'Synthetic OAuth lab',
            'invitationCode':invitation}))['data']['token']
        grant=flow.request(op,PRP+'/api/mcp/clients',bearer=session,data={
            'clientId':flow.CLIENT,'scopes':['prp.tasks.read'],'password':password})
        record('PRP owner consent '+str(i),grant[0],[200])
        userop,tokens,code,verifier=mint(name,password)
        bearer=tokens['access_token']
        jwks=obj(flow.request(op,metadata['jwks_uri']))
        check_token(bearer,jwks,issuer=flow.ISSUER,resource=flow.RESOURCE,client_id=flow.CLIENT)
        record('PKCE and actual RSA / issuer / audience '+str(i),200,[200])
        record('Unlinked identity denied '+str(i),rpc(userop,bearer)[0],[401])
        ticket=obj(flow.request(op,PRP+'/api/mcp/identity/tickets',bearer=session,
            data={'clientId':flow.CLIENT,'password':password}))['data']['code']
        linked=flow.request(op,flow.RESOURCE+'/link',bearer=bearer,data={'ticket':ticket})
        record('Verified identity binding '+str(i),linked[0],[200])
        record('Link ticket replay '+str(i),flow.request(op,flow.RESOURCE+'/link',
            bearer=bearer,data={'ticket':ticket})[0],[409])
        record('MCP initialize '+str(i),rpc(userop,bearer,'initialize',{
            'protocolVersion':flow.PROTOCOL,'capabilities':{},'clientInfo':{'name':'private-server-lab','version':'1'}})[0],[200])
        title='synthetic-owner-'+suffix+'-'+str(i)
        task=obj(flow.request(op,PRP+'/api/tasks',bearer=session,data={
            'title':title,'moduleCode':'work','description':'Isolated test data','priority':'low'}))['data']
        owners.append({'name':name,'password':password,'session':session,'op':userop,
                       'tokens':tokens,'title':title,'task':task,'code':code,'verifier':verifier})
    one,two=owners;bearer=one['tokens']['access_token']
    for owner,other in [(one,two),(two,one)]:
        status,body=rpc(owner['op'],owner['tokens']['access_token'],'tools/call',{
            'name':'prp_tasks_list','arguments':{}})
        assert owner['title'] in json.dumps(body) and other['title'] not in json.dumps(body)
        record('MCP two-user task isolation '+owner['name'][-1],status,[200])
    tools=rpc(op,bearer)[1]['result']['tools']
    assert all(t.get('description') and isinstance(t.get('inputSchema'),dict) for t in tools)
    record('Discoverable tool names descriptions schemas',200,[200])
    for name,args in [('prp_finance_month',{}),('prp_prepare_task',{'title':'not permitted','moduleCode':'work'})]:
        status,body=rpc(op,bearer,'tools/call',{'name':name,'arguments':args})
        assert body.get('result',{}).get('isError') or body.get('error')
        record('Unapproved scope / writes denied '+name,status,[200])
    for label,token in [('Malformed','not-a-jwt'),('Tampered',bearer[:-8]+'invalidx'),('Wrong issuer',admin)]:
        record(label+' access token',rpc(op,token)[0],[401])
    badparams={'client_id':flow.CLIENT,'response_type':'code','redirect_uri':'https://wrong.example/callback',
               'scope':'openid','code_challenge_method':'S256','code_challenge':'A'*43,'state':'safe-state'}
    record('Incorrect callback URI',flow.request(op,metadata['authorization_endpoint']+'?'+urlencode(badparams))[0],[400])
    original_resource=flow.RESOURCE
    flow.RESOURCE='https://wrong.example/api/mcp'
    try:
        badresourceop=opener()
        try:
            resourcecode,resourceverifier=flow.code_pkce(badresourceop,one['name'],one['password'])
        except RuntimeError as error:
            if 'unexpected HTTP 400' not in str(error):raise
            record('Unregistered resource rejected after login',400,[400])
        else:
            record('Unregistered resource rejected at token exchange',flow.request(badresourceop,
                metadata['token_endpoint'],form=True,data={'grant_type':'authorization_code',
                'client_id':flow.CLIENT,'redirect_uri':flow.CALLBACK,'code':resourcecode,
                'code_verifier':resourceverifier,'resource':flow.RESOURCE})[0],[400])
    finally:flow.RESOURCE=original_resource
    original_parse=flow.parse_callback
    def wrong_state(url,state):return original_parse(url,state+'-wrong')
    flow.parse_callback=wrong_state
    try:
        try:flow.code_pkce(opener(),one['name'],one['password'])
        except RuntimeError as e:
            assert str(e)=='OAuth state/code verification failed'
            record('Real callback rejected on state mismatch',302,[302],'server callback / client validation')
        else:raise RuntimeError('State mismatch accepted')
    finally:flow.parse_callback=original_parse
    replay=flow.request(op,metadata['token_endpoint'],form=True,data={
        'grant_type':'authorization_code','client_id':flow.CLIENT,'redirect_uri':flow.CALLBACK,
        'code':one['code'],'code_verifier':one['verifier'],'resource':flow.RESOURCE})
    record('Authorization code replay',replay[0],[400])
    badop=opener();badcode,badv=flow.code_pkce(badop,one['name'],one['password'])
    record('Wrong PKCE verifier',flow.request(badop,metadata['token_endpoint'],form=True,data={
        'grant_type':'authorization_code','client_id':flow.CLIENT,'redirect_uri':flow.CALLBACK,
        'code':badcode,'code_verifier':secrets.token_urlsafe(48),'resource':flow.RESOURCE})[0],[400])
    clients=json.loads(admin_request(op,admin,'/clients?clientId='+flow.CLIENT)[2])
    wrong=copy.deepcopy(clients[0]);wrong.pop('id',None);wrong['clientId']='wrong-audience-'+suffix
    wrong['protocolMappers']=[]
    record('Prepare isolated wrong-audience client',admin_request(op,admin,'/clients',wrong)[0],[201])
    wrongop,wrongtokens,_,_=mint(one['name'],one['password'],wrong['clientId'])
    assert flow.RESOURCE not in claims(wrongtokens['access_token']).get('aud',[])
    record('Real signed wrong-audience token',rpc(wrongop,wrongtokens['access_token'])[0],[401])
    # Fresh tokens for bounded cache tests. Only the lab issuer is stopped.
    op,tokens,_,_=mint(one['name'],one['password']);bearer=tokens['access_token']
    record('Prime JWKS cache',rpc(op,bearer)[0],[200])
    compose=['docker','compose','--project-name','prp-mcp-oauth-stage','--env-file',str(STATE/'.env'),'-f',str(HERE/'compose.yaml')]
    subprocess.run(compose+['stop','keycloak'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        record('Issuer down: cached valid key',rpc(op,bearer)[0],[200])
        header=json.loads(base64.urlsafe_b64decode(bearer.split('.')[0]+'=='));header['kid']='unknown-lab-key'
        forged=base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b'=').decode()+'.'+'.'.join(bearer.split('.')[1:])
        record('Issuer down: unknown key / JWKS fetch failure',rpc(op,forged)[0],[401])
    finally:
        subprocess.run(compose+['start','keycloak'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    flow.wait_ready(op,flow.ISSUER+'/.well-known/openid-configuration',120)
    afterkeys=obj(flow.request(op,metadata['jwks_uri']))
    assert {k['kid'] for k in jwks['keys']}=={k['kid'] for k in afterkeys['keys']}
    op,tokens,_,_=mint(one['name'],one['password']);bearer=tokens['access_token']
    record('Issuer restart: keys users sessions and PRP links persist',rpc(op,bearer)[0],[200])
    # Rotate to a new signing key while keeping old verification keys enabled.
    component={'name':'server-lab-rotation-'+suffix,'parentId':'prp-mcp','providerId':'rsa-generated',
        'providerType':'org.keycloak.keys.KeyProvider','config':{'priority':['200'],
        'enabled':['true'],'active':['true'],'keySize':['2048'],'algorithm':['RS256']}}
    record('Create independent rotated signing key',admin_request(op,admin,'/components',component)[0],[201])
    newop,newtokens,_,_=mint(one['name'],one['password']);newbearer=newtokens['access_token']
    assert claims(newbearer) and json.loads(base64.urlsafe_b64decode(newbearer.split('.')[0]+'=='))['kid']!=json.loads(base64.urlsafe_b64decode(bearer.split('.')[0]+'=='))['kid']
    record('JWKS cache refresh accepts real rotated key',rpc(newop,newbearer)[0],[200])
    record('Retained previous verification key',rpc(op,bearer)[0],[200])
    # Refresh rotation is real token endpoint behavior, not a mocked assertion.
    refresh={'grant_type':'refresh_token','client_id':flow.CLIENT,'refresh_token':newtokens['refresh_token'],'resource':flow.RESOURCE}
    updated=flow.request(newop,metadata['token_endpoint'],form=True,data=refresh)
    record('Refresh token rotation',updated[0],[200]);refreshed=obj(updated)
    assert refreshed['refresh_token']!=newtokens['refresh_token']
    record('Previous refresh token replay',flow.request(newop,metadata['token_endpoint'],form=True,data=refresh)[0],[400])
    # Isolated grant for logout/revocation, avoiding reused-refresh side effects.
    logoutop,logouttokens,_,_=mint(two['name'],two['password'])
    uid=json.loads(admin_request(op,admin,'/users?username='+two['name']+'&exact=true')[2])[0]['id']
    record('Issuer administrator logout',admin_request(op,admin,'/users/'+uid+'/logout',method='POST')[0],[204])
    record('Logged-out session refresh rejected',flow.request(logoutop,metadata['token_endpoint'],form=True,data={
        'grant_type':'refresh_token','client_id':flow.CLIENT,'refresh_token':logouttokens['refresh_token'],'resource':flow.RESOURCE})[0],[400])
    # Stateless JWTs do not promise immediate IdP logout invalidation.
    record('Bounded stateless access JWT after issuer logout',rpc(logoutop,logouttokens['access_token'])[0],[200])
    freshop,fresh,_,_=mint(one['name'],one['password']);valid=fresh['access_token']
    record('Unauthorized PRP revocation attempt',flow.request(op,PRP+'/api/mcp/clients/revoke',data={'clientId':flow.CLIENT})[0],[401])
    record('Failed revocation not misreported as success',rpc(freshop,valid)[0],[200])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        statuses=list(pool.map(lambda _:rpc(opener(),valid)[0],range(12)))
    assert statuses==[200]*12
    record('Concurrent authenticated read-only discovery (12 / 4)',200,[200])
    record('PRP client grant revocation',flow.request(op,PRP+'/api/mcp/clients/revoke',bearer=one['session'],data={'clientId':flow.CLIENT})[0],[200])
    record('Still-unexpired token after PRP revocation',rpc(freshop,valid)[0],[401])
    # Refresh-token revocation endpoint blocks subsequent refresh.
    revokeop,revoked,_,_=mint(two['name'],two['password'])
    record('Issuer refresh token revocation',flow.request(revokeop,metadata['revocation_endpoint'],form=True,data={
        'client_id':flow.CLIENT,'token':revoked['refresh_token'],'token_type_hint':'refresh_token'})[0],[200])
    record('Revoked refresh token rejected',flow.request(revokeop,metadata['token_endpoint'],form=True,data={
        'grant_type':'refresh_token','client_id':flow.CLIENT,'refresh_token':revoked['refresh_token'],'resource':flow.RESOURCE})[0],[400])
    expiry=claims(revoked['access_token'])['exp']
    delay=max(0,int(expiry+65-time.time()))
    print('Waiting for real access-token expiry including verifier clock skew',flush=True)
    while delay>0:
        time.sleep(min(delay,20));delay=max(0,int(expiry+65-time.time()))
    record('Actually expired signed access token',rpc(revokeop,revoked['access_token'])[0],[401])
    result={'tests':ROWS,'all_passed':all(r['passed'] for r in ROWS),'server_end_to_end':True,
        'access_token_lifespan_seconds':60,'verifier_clock_skew_seconds':60,
        'refresh_rotation_max_reuse':0,'session_idle_seconds':600,'session_max_seconds':1800,
        'tool_names':[t['name'] for t in tools],'writes_enabled':False,
        'tls_certificate_validation':True,'public_access':False,
        'idp_logout_access_token_policy':'Existing signed access JWT valid until expiry; PRP owner revocation is immediate'}
    REPORT.write_text(json.dumps(result,indent=2));print('PASS server lab complete',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never include exception text/URLs, response bodies or credential values.
        print('FAIL server lab: '+type(error).__name__+'; inspect sanitized recorded step statuses',flush=True)
        raise SystemExit(1)
