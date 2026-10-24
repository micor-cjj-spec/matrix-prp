"""External Windows launcher over an already authenticated/pinned SSH client.

No new SSH key, server gateway command or sudo permission. The caller supplies
the existing pinned administrator client. Never prints jobs, secrets or logs.
"""
import base64,json,pathlib,shlex,time
from guard_external_probe import collect
from guard_release_engine import GateError,digest,sha,sign,utc
def call(client,code,payload=None):
 i,o,e=client.exec_command('python3 -c '+shlex.quote(code),timeout=30)
 if payload is not None:i.write(json.dumps(payload));i.channel.shutdown_write()
 data=o.read(4000001);error=e.read(1025);status=o.channel.recv_exit_status()
 if status or len(data)>4000000:raise GateError('PINNED_ADMIN_TRANSPORT_FAILED')
 return json.loads(data)
def watch(client,transaction_name,manifest,pin,max_wait=2400):
 if not transaction_name.replace('-','').isalnum() or digest(manifest)!=pin:raise GateError('UNAPPROVED_TRANSACTION_OR_MANIFEST')
 for n,h in manifest['reviewed_sources'].items():
  if sha(pathlib.Path(__file__).parent/n)!=h:raise GateError('LAUNCHER_REVIEWED_SOURCE_DRIFT')
 remote='/root/prp-guard-release-20261024-v4/guard-release-transactions/'+transaction_name
 seen=set();end=time.monotonic()+max_wait
 while time.monotonic()<end:
  # Root-private key crosses the existing encrypted pinned admin channel
  # only; it is never put into command text, environment or stdout logs.
  result=call(client,"from pathlib import Path;import json,base64;r=Path("+repr(remote)+");p=r/'transaction.json';s=json.loads(p.read_text()) if p.exists() else {};print(json.dumps({'state':s.get('state'),'job':s.get('active_job'),'key':base64.b64encode((r/'session-key.private').read_bytes()).decode() if s.get('active_job') else None}))")
  if result['state'] in ('ACCEPT','REJECTED','ROLLED_BACK','RECOVERY_REQUIRED'):return {'state':result['state'],'submitted_phases':len(seen)}
  if result['state'] not in ('PREFLIGHT','COLLECT_EXTERNAL_EVIDENCE','POST_ROLLBACK'):time.sleep(.25);continue
  job=result.get('job')
  if not job or job['nonce'] in seen:time.sleep(.25);continue
  if job['manifest_sha256']!=pin:raise GateError('UNREVIEWED_REMOTE_JOB')
  key=base64.b64decode(result['key']);start=utc()
  try:envelope=collect(job,manifest,pin,key)
  except Exception as error:
   # Signed failure, never synthetic success. Keep watching so rollback can
   # obtain a new, independent health result after the failed forward phase.
   payload={k:job[k] for k in ['deployment_id','phase','nonce','manifest_sha256','source_config','target','probe_sha256']};payload.update(started_utc=start,ended_utc=utc(),dns=[],observations=[],collector_failure=type(error).__name__);envelope=sign(payload,key)
  filename=job['deployment_id']+'.'+job['phase']+'.'+job['nonce']+'.json'
  receipt=call(client,"from pathlib import Path;import json,sys,os;p=Path("+repr(remote+'/inbox/'+filename)+");v=json.load(sys.stdin);t=p.with_suffix('.pending');f=t.open('x');json.dump(v,f);f.flush();os.fsync(f.fileno());f.close();t.chmod(0o600);os.replace(t,p);print(json.dumps({'stored':True}))",envelope)
  if receipt.get('stored') is not True:raise GateError('INBOX_RECEIPT_FAILED')
  seen.add(job['nonce'])
 raise GateError('LAUNCHER_TOTAL_DEADLINE')
