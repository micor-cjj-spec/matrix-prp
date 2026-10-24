import copy,datetime,hashlib,json,pathlib,secrets,shutil,tempfile,time,unittest,os
from unittest.mock import patch
from guard_release_engine import Coordinator,FilePairAdapter,EvidenceGate,GateError,EvidenceTimeout,DirectoryInbox,digest,sign,utc

class ReleaseTests(unittest.TestCase):
 traces=[]
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='prp-release-engine-');self.root=pathlib.Path(self.tmp.name);self.old={};self.new={};self.live={};self.candidate={};self.reloads=[];self.validates=0;self.keys=secrets.token_bytes(32)
  for n in ['micor.top.conf','prp-mcp-test.conf']:
   self.live[n]=self.root/n;self.candidate[n]=self.root/(n+'.candidate');self.live[n].write_bytes(('old '+n).encode());self.candidate[n].write_bytes(('new '+n).encode());self.old[n]=hashlib.sha256(self.live[n].read_bytes()).hexdigest();self.new[n]=hashlib.sha256(self.candidate[n].read_bytes()).hexdigest()
  c={'sni':'micor.top','host':'micor.top','path':'/prp/api/health'}
  self.requests={}
  for ident,kind,status,family in [('v4','availability',200,'IPv4'),('v6','availability',200,'IPv6'),('deny','authority_denial',421,'IPv6'),('static','static_refusal',503,'IPv6'),('mcp','mcp_authentication',401,'IPv6')]:
   self.requests[ident]={'kind':kind,'case':c,'target':'127.0.0.1','status':status,'family':family,'alpn':'http/1.1','protocol':'1.1'}
   if kind in ('authority_denial','static_refusal'):self.requests[ident]['body_sha256']='fixed'
   if kind=='mcp_authentication':self.requests[ident]['www_authenticate']='Bearer exact'
  self.manifest={'target':'127.0.0.1','probe_sha256':'reviewed-code','max_seconds':30,'domains':['micor.top','www.micor.top','prp-test.micor.top','auth-test.micor.top'],'dns_sources':['dns25.hichina.com','dns26.hichina.com','1.1.1.1','8.8.8.8'],'phases':{p:{'config':self.new if p=='post_reload' else self.old,'requests':self.requests if p=='post_reload' else {'v4':self.requests['v4']}} for p in ['preflight','post_reload','post_rollback']}}
  self.proofs={p:{i:{'case':s['case'],'source_config':v['config'],'local_return':True,'upstream_allowed':False} for i,s in v['requests'].items() if s['kind'] in ('authority_denial','static_refusal')} for p,v in self.manifest['phases'].items()}
  self.a=FilePairAdapter(self.live,self.candidate,self.new,self.validate,self.reload)
  self.fault=None;self.saved=[]
 def tearDown(self):self.tmp.cleanup()
 def validate(self):self.validates+=1
 def reload(self,rollback):self.reloads.append(rollback)
 def provider(self,job):
  start=utc();requests=self.manifest['phases'][job['phase']]['requests'];observations=[]
  for ident,spec in requests.items():
   observations.append({'request_id':ident,'case':spec['case'],'target':spec['target'],'started_utc':utc(),'ended_utc':utc(),'status':spec['status'],'error':None,'chain_verified':True,'san_verified':True,'body_sha256':'fixed','www_authenticate':'Bearer exact','alpn':'http/1.1','protocol':'1.1','timings':{'tcp':.01,'tls':.02,'first_byte':.03,'total':.04},'passed':True})
  payload={k:job[k] for k in ['deployment_id','phase','nonce','manifest_sha256','source_config','target','probe_sha256']};payload.update(started_utc=start,ended_utc=utc(),observations=observations,dns=[{'host':h,'source':s,'utc':utc(),'query_ok':True,'a':['207.57.123.94'],'aaaa':[]} for h in self.manifest['domains'] for s in self.manifest['dns_sources']]);payload['ended_utc']=utc()
  if self.fault:self.fault(payload,job)
  result=sign(payload,self.keys);self.saved.append((copy.deepcopy(result),copy.deepcopy(job)));return result
 def coordinator(self,provider=None):return Coordinator(self.a,self.root/'transaction',EvidenceGate(self.manifest,digest(self.manifest),self.keys),provider or self.provider,self.proofs)
 def mutate(self,ident,**values):
  self.fault=lambda p,j:next(r for r in p['observations'] if r['request_id']==ident).update(values) if j['phase']=='post_reload' else None
 def run_state(self,want,provider=None):
  r=self.coordinator(provider).run();self.traces.append({'test':self._testMethodName,'state':r['state'],'history':[x['state'] for x in r['history']],'restored':r.get('restored'),'host_guard_installed':r['host_guard_installed'],'b2_execution_ready':r['b2_execution_ready']});self.assertEqual(r['state'],want);self.assertFalse(r['host_guard_installed']);self.assertFalse(r['b2_execution_ready']);return r
 def test_accept(self):self.run_state('ACCEPT');self.assertEqual(self.reloads,[False])
 def test_v4_failure(self):self.mutate('v4',status=500,passed=True);self.run_state('ROLLED_BACK');self.assertEqual(self.a.snapshot(),self.old)
 def test_v6_security_timeout(self):self.mutate('deny',status=None,error='TCP_CONNECT_TIMEOUT');self.run_state('ROLLED_BACK')
 def test_v6_normal_timeout(self):
  self.mutate('v6',status=None,error='TCP_CONNECT_TIMEOUT');self.run_state('ACCEPT');r=json.loads((self.root/'transaction/post_reload.result.json').read_text());self.assertFalse(r['diagnostics'][0]['passed'])
 def test_challenge(self):self.mutate('mcp',www_authenticate='wrong');self.run_state('ROLLED_BACK')
 def test_static_upstream(self):
  self.proofs['post_reload']['static']['upstream_allowed']=True;self.run_state('ROLLED_BACK')
 def test_bad_body(self):self.mutate('static',body_sha256='upstream');self.run_state('ROLLED_BACK')
 def test_wrong_host_upstream(self):self.proofs['post_reload']['deny']['upstream_allowed']=True;self.run_state('ROLLED_BACK')
 def test_aaaa_pre(self):
  self.fault=lambda p,j:p['dns'][0].update(aaaa=['2001:db8::1']) if j['phase']=='preflight' else None;self.run_state('REJECTED');self.assertFalse(self.reloads)
 def test_aaaa_post(self):
  self.fault=lambda p,j:p['dns'][0].update(aaaa=['2001:db8::1']) if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_dns_failed(self):
  self.fault=lambda p,j:p['dns'][0].update(query_ok=False) if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_dns_duplicate(self):
  self.fault=lambda p,j:p['dns'].append(p['dns'][0]) if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_expired(self):
  self.fault=lambda p,j:p.update(started_utc='2000-01-01T00:00:00+00:00') if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def stale_observation_envelope(self,age):
  self.manifest['max_seconds']=900
  now=time.time();stamp=lambda x:datetime.datetime.fromtimestamp(x,datetime.timezone.utc).isoformat()
  job=dict(deployment_id='age-test',phase='post_reload',nonce='fresh-test',manifest_sha256=digest(self.manifest),source_config=self.new,target=self.manifest['target'],probe_sha256=self.manifest['probe_sha256'],issued_utc=stamp(now-400),max_seconds=900,route_proofs=self.proofs['post_reload'])
  envelope=self.provider(job);payload=envelope['payload'];payload['started_utc']=stamp(now-400);payload['observations'][0]['started_utc']=stamp(now-age)
  return sign(payload,self.keys),job,now
 def test_single_observation_over_300_seconds_refused(self):
  envelope,job,now=self.stale_observation_envelope(301)
  with self.assertRaisesRegex(GateError,'REQUEST_STALE'):EvidenceGate(self.manifest,digest(self.manifest),self.keys).verify(envelope,job,now=now)
 def test_single_observation_within_300_seconds_accepted(self):
  envelope,job,now=self.stale_observation_envelope(299)
  self.assertTrue(EvidenceGate(self.manifest,digest(self.manifest),self.keys).verify(envelope,job,now=now)['accepted'])
 def test_request_missing(self):
  self.fault=lambda p,j:p['observations'].pop() if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_request_duplicate(self):
  self.fault=lambda p,j:p['observations'].append(p['observations'][0]) if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_id_mismatch(self):
  self.fault=lambda p,j:p.update(deployment_id='other') if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_phase_mismatch(self):
  self.fault=lambda p,j:p.update(phase='preflight') if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_source_drift(self):
  self.fault=lambda p,j:p.update(probe_sha256='unreviewed') if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_source_config_mismatch(self):
  self.fault=lambda p,j:p.update(source_config=self.old) if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_bad_mac(self):
  def provider(job):
   e=self.provider(job)
   if job['phase']=='post_reload':e['mac']='0'*64
   return e
  self.run_state('ROLLED_BACK',provider)
 def test_collector_exit(self):
  def provider(job):
   if job['phase']=='post_reload':raise RuntimeError('collector exited')
   return self.provider(job)
  self.run_state('ROLLED_BACK',provider)
 def test_collector_timeout(self):
  def provider(job):
   if job['phase']=='post_reload':raise EvidenceTimeout('bounded deadline')
   return self.provider(job)
  self.run_state('ROLLED_BACK',provider)
 def test_corrupt_output(self):self.run_state('ROLLED_BACK',lambda j: [] if j['phase']=='post_reload' else self.provider(j))
 def test_partial_pair(self):
  def install():
   n=next(iter(self.live));shutil.copyfile(self.candidate[n],self.live[n]);raise RuntimeError('second replace failed')
  self.a.install_pair=install;self.run_state('ROLLED_BACK');self.assertEqual(self.a.snapshot(),self.old);self.assertEqual(self.reloads,[])
 def test_nginx_test_failure(self):
  def validate():
   self.validates+=1
   if self.validates==1:raise RuntimeError('nginx -t failed')
  self.a.validate=validate;self.run_state('ROLLED_BACK');self.assertFalse(self.reloads)
 def test_forward_reload_failure(self):
  def reload(rollback):
   self.reloads.append(rollback)
   if not rollback:raise RuntimeError('reload failed')
  self.a.reload_callback=reload;self.run_state('ROLLED_BACK');self.assertEqual(self.reloads,[False,True])
 def test_rollback_reload_failure(self):
  def reload(rollback):
   if rollback:raise RuntimeError('rollback reload failed')
  self.a.reload_callback=reload;self.mutate('v4',status=500);r=self.run_state('RECOVERY_REQUIRED');self.assertFalse(r['restored'])
 def test_backup_corrupt(self):
  def fault(p,j):
   if j['phase']=='post_reload':
    p['observations'][0]['status']=500;(self.root/'transaction/backup/micor.top.conf').write_bytes(b'bad')
  self.fault=fault;self.run_state('RECOVERY_REQUIRED')
 def test_replay(self):
  self.run_state('ACCEPT');e,j=self.saved[-1];gate=EvidenceGate(self.manifest,digest(self.manifest),self.keys);gate.verify(e,j);self.assertRaises(GateError,gate.verify,e,j)
 def test_lock(self):
  c=self.coordinator();c.state={'deployment_id':'active'};c.acquire();self.assertRaises(GateError,self.coordinator().run)
 def test_repeat_start(self):self.run_state('ACCEPT');self.assertRaises(GateError,self.coordinator().run)
 def test_interrupted_partial_recovery(self):
  def install():
   n=next(iter(self.live));shutil.copyfile(self.candidate[n],self.live[n]);raise KeyboardInterrupt()
  self.a.install_pair=install;c=self.coordinator();self.assertRaises(KeyboardInterrupt,c.run)
  self.assertRaises(GateError,c.reconcile_dead_owner)
  with patch('guard_release_engine.owner_alive',return_value=False):c.reconcile_dead_owner()
  self.assertEqual(c.recover()['state'],'ROLLED_BACK');self.assertEqual(self.a.snapshot(),self.old)
 def test_unknown_interrupted_state(self):
  def install():self.live['micor.top.conf'].write_bytes(b'unknown');raise KeyboardInterrupt()
  self.a.install_pair=install;c=self.coordinator();self.assertRaises(KeyboardInterrupt,c.run)
  with patch('guard_release_engine.owner_alive',return_value=False):c.reconcile_dead_owner()
  self.assertEqual(c.recover()['state'],'RECOVERY_REQUIRED')
 def test_inbox_timeout(self):self.assertRaises(EvidenceTimeout,DirectoryInbox(self.root),{'deployment_id':'x','phase':'post_reload','nonce':'y','max_seconds':.01})
 def test_manifest_pin(self):self.assertRaises(GateError,EvidenceGate,self.manifest,'wrong',self.keys)
 def test_tls(self):self.mutate('mcp',chain_verified=False);self.run_state('ROLLED_BACK')
 def test_san(self):self.mutate('mcp',san_verified=False);self.run_state('ROLLED_BACK')
 def test_alpn(self):self.mutate('mcp',alpn='h2');self.run_state('ROLLED_BACK')
 def test_protocol(self):self.mutate('mcp',protocol='1.0');self.run_state('ROLLED_BACK')
 def test_mcp_status(self):self.mutate('mcp',status=200);self.run_state('ROLLED_BACK')
 def test_wrong_case(self):self.mutate('v4',case={'host':'other'});self.run_state('ROLLED_BACK')
 def test_wrong_target(self):self.mutate('v4',target='207.57.123.94');self.run_state('ROLLED_BACK')
 def test_dns_missing(self):
  self.fault=lambda p,j:p['dns'].pop() if j['phase']=='post_reload' else None;self.run_state('ROLLED_BACK')
 def test_post_rollback_health_failure(self):
  self.fault=lambda p,j:p['observations'][0].update(status=500) if j['phase'] in ('post_reload','post_rollback') else None;self.run_state('RECOVERY_REQUIRED')
 def test_concurrent_distinct_transaction_directory(self):
  c=self.coordinator();c.state={'deployment_id':'active'};c.acquire();other=Coordinator(self.a,self.root/'transaction-two',c.gate,self.provider,self.proofs);self.assertRaises(GateError,other.run)
 def test_wrong_status_v6_normal(self):self.mutate('v6',status=500);self.run_state('ROLLED_BACK')
 def test_production_constructor_disabled(self):self.assertRaises(GateError,FilePairAdapter,{n:'/etc/nginx/conf.d/'+n for n in self.old},self.candidate,self.new,lambda:None,lambda r:None)
 @unittest.skipIf(os.name=='nt','Linux root-private approval semantics tested on Linux')
 def test_single_use_production_approval_in_temp(self):
  from guard_production_release import ProductionAdapter
  from guard_release_engine import NEW,sha
  if os.geteuid()!=0:self.skipTest('requires Linux root-owned temporary fixture')
  a=object.__new__(ProductionAdapter);a.targets=self.live;a.context={};a.pin='reviewed';a.expected_transaction='unit';a.transaction_id='unit-deployment';a.approved_once=False;a.approval=self.root/'approval.json'
  a.approval.write_text(json.dumps({'scope':'GUARD_ONLY_PAIR_ONE_FORWARD_RELOAD','manifest_sha256':a.pin,'candidates':NEW,'transaction_name':'unit','expires_epoch':time.time()+60}));a.approval.chmod(0o600);a.approval_pin=sha(a.approval);a.snapshot=lambda:self.old
  with patch('guard_production_release.command',return_value=b'isolated synthetic config'):
   a.backup(self.root/'backup-one');self.assertRaises(FileExistsError,a.backup,self.root/'backup-two')
if __name__=='__main__':unittest.main()
