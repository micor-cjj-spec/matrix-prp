"""Durable guard-only coordinator and authenticated, observation-based evidence.

Production mutators are inert unless explicitly constructed with execute=True
by an approved operator. This module has no mutation CLI. Session keys are
ephemeral capabilities conveyed over the existing pinned admin channel; they
are never logged, put in manifests, or accepted from uploaded evidence.
"""
import datetime,hashlib,hmac,json,os,pathlib,secrets,shutil,time,uuid

OLD={'micor.top.conf':'ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b','prp-mcp-test.conf':'be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d'}
NEW={'micor.top.conf':'da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b','prp-mcp-test.conf':'90814118bda4c8ca0be3d87ae36accb003a4be7f593954d552bfe05c1c98e6bd'}
TIMEOUTS={'TCP_CONNECT_TIMEOUT','TLS_OR_CERT_VALIDATION_TIMEOUT','REQUEST_OR_FIRST_BYTE_TIMEOUT','RESPONSE_COMPLETION_TIMEOUT'}
class GateError(Exception):pass
class EvidenceTimeout(GateError):pass
def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(encoded(x)).hexdigest()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def epoch(s):return datetime.datetime.fromisoformat(s).timestamp()
def owner_alive(pid):
 if os.name=='nt':
  import ctypes
  k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=ctypes.c_void_p
  h=k.OpenProcess(0x1000,False,int(pid))
  if not h:
   if ctypes.get_last_error()==87:return False
   raise GateError('OWNER_LIVENESS_UNVERIFIED')
  code=ctypes.c_ulong()
  try:
   if not k.GetExitCodeProcess(ctypes.c_void_p(h),ctypes.byref(code)):raise GateError('OWNER_LIVENESS_UNVERIFIED')
   return code.value==259
  finally:k.CloseHandle(ctypes.c_void_p(h))
 try:os.kill(int(pid),0);return True
 except ProcessLookupError:return False
def save(path,data):
 path=pathlib.Path(path);tmp=path.with_suffix('.pending')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'wb') as f:f.write(encoded(data));f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
 if os.name!='nt':
  fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
def sign(payload,key):return {'payload':payload,'mac':hmac.new(key,encoded(payload),hashlib.sha256).hexdigest()}

class EvidenceGate:
 def __init__(self,manifest,pin,key):
  if digest(manifest)!=pin:raise GateError('REVIEWED_MANIFEST_DRIFT')
  self.manifest=manifest;self.key=key;self.consumed=set()
 def verify(self,envelope,job,now=None):
  now=time.time() if now is None else now
  if not isinstance(envelope,dict) or len(encoded(envelope))>4000000:raise GateError('EVIDENCE_SIZE_OR_FORMAT')
  p=envelope.get('payload',{})
  if not hmac.compare_digest(str(envelope.get('mac','')),hmac.new(self.key,encoded(p),hashlib.sha256).hexdigest()):raise GateError('EVIDENCE_AUTHENTICATION')
  for name in ['deployment_id','phase','nonce','manifest_sha256','source_config','target','probe_sha256']:
   if p.get(name)!=job.get(name):raise GateError('EVIDENCE_IDENTITY:'+name)
  profile=self.manifest['phases'][job['phase']]
  if job['source_config']!=profile['config']:raise GateError('WRONG_PHASE_CONFIGURATION')
  identity=(job['deployment_id'],job['phase'],job['nonce'])
  if identity in self.consumed:raise GateError('EVIDENCE_REPLAY')
  try:start=epoch(p['started_utc']);end=epoch(p['ended_utc']);issued=epoch(job['issued_utc'])
  except Exception:raise GateError('EVIDENCE_TIME_MISSING')
  if not issued<=start<=end<=now+2 or now-end>60 or end-start>job['max_seconds'] or now>issued+job['max_seconds']:raise GateError('EVIDENCE_EXPIRED_OR_TIMEOUT')
  dns=p.get('dns',[]);keys=[(r.get('host'),r.get('source')) for r in dns]
  expected={(h,s) for h in self.manifest['domains'] for s in self.manifest['dns_sources']}
  if len(keys)!=len(expected) or set(keys)!=expected:raise GateError('DNS_MISSING_DUPLICATE')
  for r in dns:
   if r.get('query_ok') is not True or r.get('a')!=['207.57.123.94'] or r.get('aaaa')!=[]:raise GateError('DNS_FAILED_OR_AAAA_REVIEW_REQUIRED')
   if not issued<=epoch(r['utc'])<=end or now-epoch(r['utc'])>300:raise GateError('DNS_STALE')
  rows=p.get('observations',[]);ids=[r.get('request_id') for r in rows]
  if len(ids)!=len(set(ids)) or set(ids)!=set(profile['requests']):raise GateError('REQUEST_MISSING_DUPLICATE_OR_UNKNOWN')
  diagnostics=[]
  for r in rows:
   spec=profile['requests'][r['request_id']]
   if r.get('case')!=spec['case'] or r.get('target')!=spec['target']:raise GateError('REQUEST_SOURCE_MISMATCH')
   if not start<=epoch(r['started_utc'])<=epoch(r['ended_utc'])<=end:raise GateError('REQUEST_TIME')
   if now-epoch(r['started_utc'])>300:raise GateError('REQUEST_STALE')
   if r.get('error'):
    if spec['kind']=='availability' and spec['family']=='IPv6' and r['error'] in TIMEOUTS and r.get('status') in (None,spec.get('status')):
     diagnostics.append({**r,'passed':False});continue
    raise GateError('REQUIRED_TRANSPORT:'+r['request_id'])
   # Derive every decision from observations. Ignore any uploaded ready/passed.
   for name in ['status','body_sha256','body_bytes','json_canonical_sha256','www_authenticate','location','alpn','protocol','semantic']:
    if name in spec and r.get(name)!=spec[name]:raise GateError('RESPONSE_CONTRACT:'+r['request_id']+':'+name)
   if not spec['case'].get('plain') and (r.get('chain_verified') is not True or r.get('san_verified')!=spec.get('san_required',True)):raise GateError('TLS_SAN_OR_CHAIN')
   if spec['kind'] in ('authority_denial','path_denial','static_refusal'):
    # Local routing is a separate server attestation in the same trusted
    # administrative session. It is not invented by the Windows uploader.
    proof=job['route_proofs'].get(r['request_id'])
    if not proof or proof['source_config']!=job['source_config'] or proof['case']!=spec['case'] or proof.get('local_return') is not True or proof.get('upstream_allowed') is not False:raise GateError('LOCAL_ROUTE_PROOF_MISSING')
    if 'local_route_proofs' in profile and proof!=profile['local_route_proofs'].get(r['request_id']):raise GateError('UNREVIEWED_ROUTE_PROOF')
  self.consumed.add(identity)
  return {'accepted':True,'diagnostics':diagnostics,'raw_evidence_sha256':digest(p)}

class DirectoryInbox:
 """Bounded inbox; a separate trusted collector sends HMAC envelopes here."""
 def __init__(self,root):self.root=pathlib.Path(root)
 def __call__(self,job):
  p=self.root/(job['deployment_id']+'.'+job['phase']+'.'+job['nonce']+'.json')
  deadline=time.monotonic()+job['max_seconds']
  while time.monotonic()<deadline:
   if p.exists():
    if p.is_symlink() or p.stat().st_size>4000000:raise GateError('INBOX_FILE_REJECTED')
    try:return json.loads(p.read_text(encoding='utf-8'))
    except Exception:raise GateError('COLLECTOR_CORRUPT_OUTPUT')
   time.sleep(.2)
  raise EvidenceTimeout('COLLECTOR_TIMEOUT')

class Coordinator:
 def __init__(self,adapter,root,gate,collector,source_proofs=None,lock_root=None):
  self.a=adapter;self.root=pathlib.Path(root);self.gate=gate;self.collector=collector;self.proofs=source_proofs or {p:v.get('local_route_proofs',{}) for p,v in gate.manifest['phases'].items()};self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
  self.journal=self.root/'transaction.json';self.lock=pathlib.Path(lock_root) if lock_root else self.root.parent/'guard-release.lock';self.state={}
 def transition(self,name,**extra):
  self.state.update(extra,state=name);self.state.setdefault('history',[]).append({'state':name,'utc':utc()});save(self.journal,self.state)
 def final_report(self):
  self.state.update(host_guard_installed=bool(getattr(self.a,'production',False) and self.state['state']=='ACCEPT'),b2_execution_ready=False)
  self.state['history'].append({'state':'FINAL_REPORT','utc':utc()});save(self.journal,self.state);save(self.root/'final-report.json',self.state);return self.state
 def acquire(self):
  try:self.lock.mkdir(mode=0o700)
  except FileExistsError:raise GateError('TRANSACTION_LOCKED_RECOVERY_REQUIRED')
  save(self.lock/'owner.json',{'pid':os.getpid(),'deployment_id':self.state['deployment_id']})
 def release(self):shutil.rmtree(self.lock)
 def reconcile_dead_owner(self):
  owner=json.loads((self.lock/'owner.json').read_text());state=json.loads(self.journal.read_text())
  if owner['deployment_id']!=state['deployment_id']:raise GateError('LOCK_OWNER_MISMATCH')
  if not owner_alive(owner['pid']):shutil.rmtree(self.lock);return
  raise GateError('OWNER_STILL_ALIVE')
 def collect(self,phase):
  profile=self.gate.manifest['phases'][phase];actual=self.a.snapshot()
  if actual!=profile['config']:raise GateError('PHASE_CONFIG_DRIFT')
  job=dict(deployment_id=self.state['deployment_id'],phase=phase,nonce=secrets.token_hex(24),manifest_sha256=digest(self.gate.manifest),source_config=actual,target=self.gate.manifest['target'],probe_sha256=self.gate.manifest['probe_sha256'],issued_utc=utc(),max_seconds=self.gate.manifest['max_seconds'],route_proofs=self.proofs.get(phase,self.proofs))
  self.transition('COLLECT_EXTERNAL_EVIDENCE' if phase=='post_reload' else phase.upper(),active_job={k:v for k,v in job.items() if k!='route_proofs'})
  envelope=self.collector(job)
  if self.a.snapshot()!=actual:raise GateError('SOURCE_CHANGED_DURING_EXTERNAL_COLLECTION')
  self.transition('VERIFY_POLICY_B' if phase=='post_reload' else phase.upper()+'_VERIFY')
  result=self.gate.verify(envelope,job);save(self.root/(phase+'.evidence.json'),envelope);save(self.root/(phase+'.result.json'),result);return result
 def rollback(self,reason):
  self.transition('ROLLBACK',failure=reason)
  try:
   actual=self.a.snapshot();old=self.gate.manifest['phases']['preflight']['config'];new=self.gate.manifest['phases']['post_reload']['config']
   if set(actual)!=set(old) or any(actual[n] not in (old[n],new[n]) for n in old):raise GateError('UNKNOWN_FILE_STATE_MANUAL_RECOVERY_REQUIRED')
   self.a.restore(self.root/'backup');self.a.check(self.gate.manifest['phases']['post_rollback']['config']);self.a.nginx_test()
   if self.state.get('reload_attempted'):self.a.reload(rollback=True)
   self.collect('post_rollback');self.transition('ROLLED_BACK',restored=True)
  except Exception as error:self.transition('RECOVERY_REQUIRED',restored=False,recovery_error=type(error).__name__+':'+str(error))
 def run(self):
  if self.journal.exists():raise GateError('EXISTING_TRANSACTION_REQUIRES_RECOVERY')
  self.state={'deployment_id':uuid.uuid4().hex,'mutated':False,'reload_attempted':False,'history':[]};self.acquire()
  self.a.transaction_id=self.state['deployment_id'];self.a.transaction_root=self.root
  try:
   self.transition('PRECHECK');self.a.check(self.gate.manifest['phases']['preflight']['config']);self.a.check_candidates();self.collect('preflight')
   self.transition('BACKUP');self.a.backup(self.root/'backup')
   # Persist intent before touching either file, so partial installs recover.
   self.transition('INSTALL_PAIR',mutated=True);self.a.install_pair()
   self.transition('NGINX_TEST');self.a.check(self.gate.manifest['phases']['post_reload']['config']);self.a.nginx_test()
   self.transition('RELOAD',reload_attempted=True);self.a.reload(rollback=False)
   self.collect('post_reload');self.transition('ACCEPT',restored=False)
  except Exception as error:
   if self.state['mutated']:self.rollback(type(error).__name__+':'+str(error))
   else:self.transition('REJECTED',failure=type(error).__name__+':'+str(error))
  # BaseException deliberately simulates power loss: lock and intent survive.
  else:pass
  finally:
   if self.state.get('state') in ('ACCEPT','REJECTED','ROLLED_BACK'):self.release()
  return self.final_report()
 def recover(self):
  if self.lock.exists():raise GateError('LOCK_MUST_BE_RECONCILED_BY_OPERATOR')
  self.state=json.loads(self.journal.read_text());self.acquire()
  try:
   actual=self.a.snapshot();old=self.gate.manifest['phases']['preflight']['config'];new=self.gate.manifest['phases']['post_reload']['config']
   if set(actual)!=set(old) or any(actual[n] not in (old[n],new[n]) for n in old):self.transition('RECOVERY_REQUIRED',restored=False,recovery_error='UNKNOWN_ACTUAL_FILE_STATE')
   elif self.state['mutated']:self.rollback('INTERRUPTED_TRANSACTION')
   else:self.a.check(old);self.collect('post_rollback');self.transition('ROLLED_BACK',restored=True)
  finally:
   if self.state.get('state')=='ROLLED_BACK':self.release()
  return self.final_report()

class FilePairAdapter:
 """Same file/backup code for isolated and production targets; callbacks scoped.

The production constructor requires execute=True; no caller in this delivery
uses it. Candidate source hashes are immutable constants for production.
"""
 def __init__(self,targets,candidates,expected_candidates,validate,reload,execute=False,context=None):
  self.targets={k:pathlib.Path(v) for k,v in targets.items()};self.candidates={k:pathlib.Path(v) for k,v in candidates.items()};self.expected_candidates=expected_candidates;self.validate=validate;self.reload_callback=reload
  self.context={k:pathlib.Path(v) for k,v in (context or {}).items()}
  self.production=any(p.as_posix().startswith('/etc/nginx/') for p in self.targets.values())
  if self.production and (not execute or expected_candidates!=NEW or set(targets)!=set(OLD)):raise GateError('PRODUCTION_EXECUTION_NOT_AUTHORIZED')
  self.expected_original={n:sha(p) for n,p in self.targets.items()}
 def snapshot(self):return {n:sha(p) for n,p in {**self.targets,**self.context}.items()}
 def check(self,expected):
  if self.snapshot()!=expected or any(p.is_symlink() or not p.is_file() for p in self.targets.values()):raise GateError('PAIR_SOURCE_DRIFT')
 def check_candidates(self):
  if set(self.candidates)!=set(self.targets) or any(sha(p)!=self.expected_candidates[n] for n,p in self.candidates.items()):raise GateError('CANDIDATE_DRIFT')
 def backup(self,path):
  path.mkdir(mode=0o700)
  for n,p in self.targets.items():
   shutil.copy2(p,path/n);os.chmod(path/n,0o600)
   with (path/n).open('r+b') as f:os.fsync(f.fileno())
   if sha(path/n)!=sha(p):raise GateError('BACKUP_VERIFICATION')
 def replace(self,source):
  for n,p in self.targets.items():
   tmp=p.with_suffix('.guard-pending')
   if tmp.exists() or tmp.is_symlink():
    if tmp.is_symlink() or sha(tmp) not in (self.expected_original[n],self.expected_candidates[n]):raise GateError('UNKNOWN_PENDING_FILE')
    tmp.unlink()
   shutil.copyfile(source[n],tmp);os.chmod(tmp,0o644)
   with tmp.open('r+b') as f:os.fsync(f.fileno())
   os.replace(tmp,p)
   if os.name!='nt':
    fd=os.open(p.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
 def install_pair(self):self.check_candidates();self.replace(self.candidates)
 def restore(self,backup):
  original=self.expected_original
  if any(sha(backup/n)!=original[n] for n in self.targets):raise GateError('BACKUP_CORRUPTED')
  self.replace({n:backup/n for n in self.targets})
 def nginx_test(self):self.validate()
 def reload(self,rollback=False):self.reload_callback(rollback)
