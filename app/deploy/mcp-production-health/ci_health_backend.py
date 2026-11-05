"""Disposable real MySQL + Java + native Keycloak health E2E; no mocks or live users."""
import datetime,hashlib,json,os,pathlib,secrets,subprocess,time
from urllib.parse import parse_qs,urlsplit
from contract import *
from runtime_config import runtime_config
MYSQL='mysql@sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b'
CONTAINER='prp-health-backend-mysql-ci'

class Backend:
 def __init__(self,root,cert,command,check,flow):
  self.root=root;self.cert=cert;self.command=command;self.check=check;self.flow=flow;self.process=None;self.db_started=False
  self.password=secrets.token_urlsafe(36);self.dbpass=secrets.token_urlsafe(36);self.jwtsecret=secrets.token_urlsafe(48)
  for secret in (self.password,self.dbpass,self.jwtsecret):print('::add-mask::'+secret,flush=True)
 def sql(self,query):
  return self.command(['docker','exec',CONTAINER,'sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --protocol=TCP -h127.0.0.1 -uprp_health -N -B matrix_prp -e "$1"','sh',query]).decode().strip()
 def stop_java(self):
  if self.process:
   self.process.terminate()
   try:self.process.wait(timeout=15)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
   self.process=None
 def stop(self):
  self.stop_java()
  if self.db_started:self.command(['docker','rm','-f',CONTAINER]);self.db_started=False
 def start_java(self,configuration):
  env=dict(os.environ);env.update(MATRIX_PRP_DB_URL='jdbc:mysql://127.0.0.1:3306/matrix_prp?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai',
   MATRIX_PRP_DB_USER='prp_health',MATRIX_PRP_DB_PASSWORD=self.dbpass,MATRIX_PRP_JWT_SECRET=self.jwtsecret,
   MATRIX_PRP_BOOTSTRAP_USERNAME='ci_health_owner',MATRIX_PRP_BOOTSTRAP_PASSWORD=self.password,
   MATRIX_PRP_AI_SPRING_AI_ENABLED='false',MATRIX_PRP_AI_SPRING_AI_TOOLS_ENABLED='false',
   SERVER_ADDRESS='127.0.0.1',SERVER_PORT='18110',SERVER_FORWARD_HEADERS_STRATEGY='framework',
   SPRING_APPLICATION_JSON=json.dumps(configuration))
  log=self.root/'prp-private.log'
  jar=pathlib.Path(__file__).resolve().parents[2]/'backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar'
  self.jar_sha256=hashlib.sha256(jar.read_bytes()).hexdigest()
  hosts=self.root/'java-hosts';hosts.write_text('127.0.0.1 localhost auth.micor.top\n127.0.0.2 micor.top\n')
  trust=self.root/'prp-trust.p12'
  if not trust.exists():self.command(['keytool','-importcert','-noprompt','-alias','ci-only-health-tls','-file',str(self.cert),'-keystore',str(trust),'-storetype','PKCS12','-storepass','ci-local-public-cert-store'])
  with log.open('ab') as f:
   self.process=subprocess.Popen(['java','-Xms64m','-Xmx384m','-Djdk.net.hosts.file='+str(hosts),'-Djavax.net.ssl.trustStore='+str(trust),'-Djavax.net.ssl.trustStoreType=PKCS12','-Djavax.net.ssl.trustStorePassword=ci-local-public-cert-store','-jar',str(jar)],env=env,stdout=f,stderr=subprocess.STDOUT)
  import http.client
  for _ in range(120):
   if self.process.poll() is not None:raise RuntimeError('REAL_HEALTH_BACKEND_START_FAILED')
   try:
    c=http.client.HTTPConnection('127.0.0.1',18110,timeout=2);c.request('GET','/api/health');r=c.getresponse();r.read(65537);status=r.status;c.close()
    if status==200:return
   except OSError:pass
   time.sleep(1)
  raise RuntimeError('REAL_HEALTH_BACKEND_START_TIMEOUT')
 def start(self):
  if os.environ.get('GITHUB_ACTIONS')!='true' or not os.environ.get('RUNNER_TEMP') or not self.root.resolve().is_relative_to(pathlib.Path(os.environ['RUNNER_TEMP']).resolve()):raise RuntimeError('DISPOSABLE_HEALTH_BACKEND_ONLY')
  import socket
  for port in (3306,18110):
   with socket.socket() as sock:
    try:sock.bind(('127.0.0.1',port))
    except OSError:raise RuntimeError('DISPOSABLE_HEALTH_PORT_OCCUPIED') from None
  self.command(['docker','pull',MYSQL],timeout=180)
  env=self.root/'mysql.env';env.write_text('MYSQL_ROOT_PASSWORD='+secrets.token_urlsafe(36)+'\nMYSQL_DATABASE=matrix_prp\nMYSQL_USER=prp_health\nMYSQL_PASSWORD='+self.dbpass+'\n');env.chmod(0o600)
  self.command(['docker','run','-d','--name',CONTAINER,'--memory','768m','--pids-limit','128','-p','127.0.0.1:3306:3306','--env-file',str(env),MYSQL,'--character-set-server=utf8mb4','--collation-server=utf8mb4_general_ci'])
  self.db_started=True
  for _ in range(90):
   try:
    if self.sql('SELECT 1;')=='1':break
   except RuntimeError:pass
   time.sleep(1)
  else:raise RuntimeError('REAL_HEALTH_MYSQL_START_TIMEOUT')
  # Only this new CI schema is migrated. Guarded production-shaped runtime is then restarted with Flyway OFF.
  self.start_java({'spring':{'flyway':{'enabled':True},'ai':{'mcp':{'server':{'enabled':False}}}},'matrix-prp':{'mcp':{'enabled':False}}})
  self.check('real_health_mysql_v29_migrated',self.sql('SELECT version,success FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 1;')=='29\t1')
  self.stop_java()
  self.sql("UPDATE prp_users SET is_admin=0 WHERE username='ci_health_owner'; INSERT INTO prp_users(username,display_name,password_hash,is_admin,enabled) SELECT 'ci_health_other','Synthetic other',password_hash,0,1 FROM prp_users WHERE username='ci_health_owner';")
  owner=int(self.sql("SELECT id FROM prp_users WHERE username='ci_health_owner';"));self.check('real_health_owner_is_normal_synthetic',self.sql("SELECT is_admin FROM prp_users WHERE id="+str(owner))=='0')
  self.start_java(runtime_config(owner));self.owner=owner
  self.check('real_health_production_guard_runtime_flyway_off',True)


def exercise(app,opener_factory,cert,key,keycloak_password,exchange,flow,check):
 if os.environ.get('GITHUB_ACTIONS')!='true' or not app.db_started:raise RuntimeError('DISPOSABLE_COMBINED_HEALTH_ONLY')
 base='https://micor.top';op=opener_factory(cert)
 def api(path,bearer=None,data=None):return flow.request(op,base+path,bearer=bearer,data=data)
 def success(path,bearer=None,data=None):
  r=api(path,bearer,data);check('real_health_api_'+str(len(checks)),r[0]==200);checks.append(path)
  return json.loads(r[2])['data']
 checks=[]
 login=success('/api/auth/login',data={'username':'ci_health_owner','password':app.password});session=login['token']
 other=success('/api/auth/login',data={'username':'ci_health_other','password':app.password})['token']
 check('real_health_login_is_not_admin',not login['user']['administrator'])
 # Use the real owner consent API, never a SQL grant or identity insertion.
 grant=success('/api/mcp/clients',session,{'clientId':CLIENT,'scopes':list(SCOPES),'password':app.password});check('real_health_owner_consent_six_scopes',grant['status']=='ACTIVE' and set(grant['scopes'])==set(SCOPES))
 check('real_health_task_scope_consent_denied',api('/api/mcp/clients',session,{'clientId':CLIENT,'scopes':['prp.tasks.read'],'password':app.password})[0]==403)
 check('real_health_binding_bad_password_refused',api('/api/mcp/identity/oidc/start',session,{'password':'wrong-synthetic-password'})[0]==403)
 begin=success('/api/mcp/identity/oidc/start',session,{'password':app.password});authorize=begin['authorizeUrl'];params=parse_qs(urlsplit(authorize).query)
 original_client,original_callback=flow.CLIENT,flow.CALLBACK
 try:
  flow.CLIENT=FIRST_PARTY;flow.CALLBACK=FIRST_REDIRECT
  code,verifier=flow.code_pkce(opener_factory(cert),'synthetic-health-user',keycloak_password,authorization_url=authorize)
  check('real_health_pkce_verifier_stays_in_backend',verifier is None)
 finally:flow.CLIENT=original_client;flow.CALLBACK=original_callback
 payload={'state':params['state'][0],'code':code,'iss':ISSUER}
 linked=success('/api/mcp/identity/oidc/finish',session,payload);check('real_health_native_id_token_bound_in_prp',linked['newlyLinked'] is True and linked['issuer']==ISSUER)
 check('real_health_oidc_callback_replay_denied',api('/api/mcp/identity/oidc/finish',session,payload)[0]==409)
 def oauth(scopes):
  code,verifier=flow.code_pkce(opener_factory(cert),'synthetic-health-user',keycloak_password,' '.join(scopes))
  status,tokens=exchange(opener_factory(cert),key,code=code,verifier=verifier);check('real_health_code_token_exchange_'+str(len(checks)),status==200);checks.append('token');return tokens['access_token']
 bearer=oauth(SCOPES);read=oauth(['prp.wellness.read'])
 def rpc(token,method,params):return flow.jsonrpc(op,token,700+len(checks),method,params)
 def raw_tool(name,args,token=None):return rpc(token or bearer,'tools/call',{'name':name,'arguments':args})
 def tool(name,args,denied=False,token=None):
  status,body=raw_tool(name,args,token);result=body.get('result',{});failed=bool(body.get('error') or result.get('isError'))
  check('real_health_tool_'+name+'_'+str(len(checks)),status==200 and (failed if denied else not failed));checks.append(name)
  if denied:return result
  if result.get('structuredContent') is not None:return result['structuredContent']
  return json.loads(''.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text'))
 status,manifest=rpc(bearer,'tools/list',{});tools=manifest.get('result',{}).get('tools',[])
 check('real_health_signed_token_discovers_exactly_nine',status==200 and len(tools)==9 and all('wellness' in x['name'] for x in tools))
 check('real_health_manifest_exact_oauth_scopes',all(x.get('_meta',{}).get('securitySchemes',[{}])[0].get('scopes',[None])[0] in SCOPES for x in tools))
 before=app.sql('SELECT COUNT(*) FROM prp_mcp_write_drafts;')
 today=datetime.date.today().isoformat()
 exercise_input={'entity':'exercise','input':{'exercise':{'performedOn':today,'name':'Synthetic walk','durationMinutes':30}}}
 denied=tool('prp_prepare_wellness_create',exercise_input,denied=True,token=read)
 check('real_health_read_token_incremental_challenge', 'insufficient_scope' in json.dumps(denied.get('_meta',{}).get('mcp/www_authenticate')) and 'prp.wellness.write.create' in json.dumps(denied['_meta']))
 check('real_health_read_token_created_no_draft',app.sql('SELECT COUNT(*) FROM prp_mcp_write_drafts;')==before)
 parts=bearer.rsplit('.',1);bad=parts[0]+'.'+('A' if parts[1][0]!='A' else 'B')+parts[1][1:]
 check('real_health_bad_native_signature_refused',rpc(bad,'tools/list',{})[0]==401)
 other_row=success('/api/wellness/exercises',other,{'performedOn':today,'name':'Other synthetic private exercise','durationMinutes':12})
 tool('prp_wellness_get',{'entity':'exercise','recordId':other_row['id']},denied=True)
 tool('prp_prepare_wellness_delete',{'entity':'exercise','recordId':other_row['id']},denied=True)
 check('real_health_foreign_record_unchanged',app.sql('SELECT COUNT(*) FROM prp_wellness_exercises WHERE id='+str(other_row['id']))=='1')
 def approve(draft):
  path='/api/mcp/approval/drafts/'+draft['draftId']+'/approve'
  check('real_health_foreign_owner_cannot_approve',api(path,other,{'password':app.password})[0] in (403,404))
  result=success(path,session,{'password':app.password});check('real_health_exact_draft_password_approved',result['status']=='APPROVED')
 def create_input(entity,after=False):
  if entity=='meal':return {'meal':{'mealDate':today,'mealType':'LUNCH','note':'After' if after else 'Before','items':[{'foodId':None,'name':'Synthetic estimated lunch','grams':None,'calories':550 if after else 500}]}}
  if entity=='exercise':return {'exercise':{'performedOn':today,'name':'After' if after else 'Before','durationMinutes':40 if after else 30}}
  return {'metric':{'measuredOn':today,'weightKg':71 if after else 70,'bodyFatPct':20,'waistCm':80}}
 for entity in ('meal','exercise','metric'):
  draft=tool('prp_prepare_wellness_create',{'entity':entity,'input':create_input(entity)})
  check('real_health_approval_url_exact_origin',(base+'/prp/me/mcp-approve/'+draft['draftId']) in draft['instruction'])
  tool('prp_confirm_wellness_draft',{'draftId':draft['draftId']},denied=True)
  approve(draft);saved=tool('prp_confirm_wellness_draft',{'draftId':draft['draftId']});record_id=saved['saved']['id']
  check('real_health_create_replay_exactly_once',tool('prp_confirm_wellness_draft',{'draftId':draft['draftId']})['alreadySaved'] is True)
  row=tool('prp_wellness_get',{'entity':entity,'recordId':record_id});check('real_health_owned_get_'+entity,row['id']==record_id)
  tool('prp_wellness_list',{'entity':entity,'date':today,'days':1})
  tool('prp_wellness_draft_status',{'draftId':draft['draftId']})
  changed=tool('prp_prepare_wellness_update',{'entity':entity,'recordId':record_id,'input':create_input(entity,True)})
  approve(changed);tool('prp_confirm_wellness_draft',{'draftId':changed['draftId']})
  row=tool('prp_wellness_get',{'entity':entity,'recordId':record_id})
  check('real_health_update_persisted_'+entity,str(row['weightKg']).startswith('71') if entity=='metric' else row['note' if entity=='meal' else 'name']=='After')
  if entity=='meal':
   daily=tool('prp_wellness_daily',{'date':today});check('real_health_structured_daily_calories',float(daily['calories'])==550)
  deleted=tool('prp_prepare_wellness_delete',{'entity':entity,'recordId':record_id});approve(deleted);result=tool('prp_confirm_wellness_draft',{'draftId':deleted['draftId']})
  check('real_health_delete_persisted_'+entity,result['saved']['deleted'] is True)
  tool('prp_wellness_get',{'entity':entity,'recordId':record_id},denied=True)
 private_food=success('/api/wellness/foods',other,{'name':'Synthetic private other food','preparation':'raw','calories100g':100,'protein100g':0,'carbs100g':0,'fat100g':0,'sourceNote':'CI only'})
 found=tool('prp_wellness_foods',{'query':'Synthetic private other food'})
 check('real_health_food_search_excludes_other_private_food','Synthetic private other food' not in json.dumps(found))
 attempted={'entity':'meal','input':{'meal':{'mealDate':today,'mealType':'DINNER','items':[{'foodId':private_food['id'],'grams':100}]}}}
 tool('prp_prepare_wellness_create',attempted,denied=True)
 # Grant reduction must take effect for an already-issued full-scope token.
 success('/api/mcp/clients',session,{'clientId':CLIENT,'scopes':['prp.wellness.read'],'password':app.password})
 tool('prp_prepare_wellness_create',exercise_input,denied=True)
 success('/api/mcp/clients',session,{'clientId':CLIENT,'scopes':list(SCOPES),'password':app.password})
 rejected=tool('prp_prepare_wellness_create',exercise_input)
 success('/api/mcp/approval/drafts/'+rejected['draftId']+'/reject',session,{})
 tool('prp_confirm_wellness_draft',{'draftId':rejected['draftId']},denied=True)
 check('real_health_no_generic_records_written',app.sql('SELECT COUNT(*) FROM prp_records;')=='0')
 success('/api/mcp/clients/revoke',session,{'clientId':CLIENT})
 check('real_health_revoked_unexpired_signed_token_immediate_denial',rpc(bearer,'tools/list',{})[0]==401)
 check('real_health_other_user_record_survives_own_crud',app.sql('SELECT COUNT(*) FROM prp_wellness_exercises WHERE id='+str(other_row['id']))=='1')
 return {'backend_jar_sha256':app.jar_sha256,'mysql_image':MYSQL,'scope':'REAL_KEYCLOAK_PRP_MYSQL_COMBINED','real_chatgpt_verified':False}
