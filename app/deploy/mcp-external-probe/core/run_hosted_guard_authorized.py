"""One authorized guard transaction, at most three disposable WARP dispatches.

Requires fresh actual recovery proof; never updates OAuth, PRP or databases.
No installed source is overwritten. Observation errors do not restart root.
"""
from pathlib import Path
import json,sys,time

HERE=Path(__file__).resolve().parent
BUNDLE=HERE/'worker-core-bundle-v4'
sys.path.insert(0,str(HERE.parent/'release-v4'))
from guard_release_engine import digest,sha,save,GateError


class BudgetPublisher:
    def __init__(self,publisher,ledger):self.publisher,self.ledger=publisher,Path(ledger)
    def start(self,job):
        record=json.loads(self.ledger.read_text())
        attempts=record.setdefault('dispatch_attempts',[])
        if record['maximum_temporary_device_registrations']!=3 or len(attempts)>=3:raise GateError('REGISTRATION_BUDGET_EXHAUSTED')
        if attempts and any(a['deployment_id']!=job['deployment_id'] or a['phase']==job['phase'] for a in attempts):raise GateError('AUTHORIZATION_SINGLE_TRANSACTION_PHASE_ONLY')
        if job['phase'] not in {'preflight','post_reload','post_rollback'}:raise GateError('UNAPPROVED_COLLECTION_PHASE')
        # An ambiguous dispatch consumes its budget; never retry a registration.
        attempts.append({k:job[k] for k in ('deployment_id','phase','nonce')})
        save(self.ledger,record)
        return self.publisher.start(job)
    def poll(self,handle):return self.publisher.poll(handle)


PREPARE=r'''
from pathlib import Path
import sys,json,os,base64,time,hashlib,shutil,re,datetime,subprocess
p=json.load(sys.stdin);os.umask(0o077)
r=Path('/root/prp-guard-release-20261024-v4');sys.path.insert(0,str(r))
from guard_release_engine import digest,sha,NEW,save
from guard_production_release import ProductionAdapter
m=p['manifest'];pin=p['pin'];assert digest(m)==pin
original=json.loads((r/'manifest.candidate.json').read_text())
assert digest(original)=='58899abe603da5b4191469b15cb8b70dc264ed9903e7549d7e45da05fa9b6011'
assert m['parent_manifest_sha256']==digest(original)
assert m['phases']==original['phases'] and m['local_requests']==original['local_requests']
assert m['max_observation_age_seconds']==300 and m['production_external_concurrency']==2
for name,wanted in original['reviewed_sources'].items():assert sha(r/name)==wanted
adapter=ProductionAdapter(m,pin)
adapter.check(m['phases']['preflight']['config']);adapter.check_candidates()
assert not (r/'host-guard/policy-b-release.lock').exists()
assert int(re.search(r'MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text()).group(1))>=2*1024**2
assert shutil.disk_usage('/').free>=25*1024**3
proof_root=Path(p['recovery_directory'])
assert proof_root.parent==Path('/root') and re.fullmatch('prp-fresh-recovery-20261024-[0-9]{6}',proof_root.name)
proof=json.loads((proof_root/'fresh-recovery.safe.json').read_text())
assert proof['complete'] and proof['started_containers_stopped'] and proof['production_services_unchanged']
assert proof['database_restore_fingerprints_match'] and proof['restored_token_signature_verified']
assert not proof['production_configuration_changed'] and not proof['live_database_written']
assert 0<=time.time()-proof['completed_epoch']<3600
backend=json.loads(subprocess.check_output(['docker','inspect','prp-mcp-stage-backend-1']))[0]
assert 'MATRIX_PRP_MCP_WRITE_ENABLED=false' in backend['Config']['Env']
assert set(p['sources'])==set(m['reviewed_sources'])
for name,encoded in p['sources'].items():
 assert re.fullmatch('[A-Za-z0-9_.-]+',name)
 raw=base64.b64decode(encoded);assert hashlib.sha256(raw).hexdigest()==m['reviewed_sources'][name]
 target=r/name
 if target.exists():assert not target.is_symlink() and sha(target)==m['reviewed_sources'][name]
 else:
  with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  target.chmod(0o600)
for name,wanted in m['reviewed_sources'].items():assert sha(r/name)==wanted
manifest_path=r/('manifest.hosted.review-'+pin[:12]+'.json')
if manifest_path.exists():assert digest(json.loads(manifest_path.read_text()))==pin
else:save(manifest_path,m)
check=subprocess.run(['python3',str(r/'guard_production_release.py'),'--manifest',str(manifest_path),'--manifest-sha256',pin,'--check'],capture_output=True,timeout=45)
assert check.returncode==0
if not p['run']:
 print(json.dumps({'prepared':True,'transaction_started':False,'manifest_sha256':pin}));sys.exit(0)
syntax=json.loads((proof_root/'nginx-pair-syntax/result.safe.json').read_text())
assert syntax['isolated_syntax_passed'] and not syntax['active_configuration_changed'] and not syntax['nginx_reloaded']
assert {n:v['after'] for n,v in syntax['changes'].items()}==NEW
name='authorized-hosted-20261024-'+datetime.datetime.now().strftime('%H%M%S')
t=r/'guard-release-transactions'/name;t.mkdir(mode=0o700)
import secrets
key=t/'session-key.private';key.write_bytes(secrets.token_bytes(32));key.chmod(0o600)
approval=t/'approval.private.json'
save(approval,{'scope':'GUARD_ONLY_PAIR_ONE_FORWARD_RELOAD','manifest_sha256':pin,'candidates':NEW,'transaction_name':name,'expires_epoch':time.time()+1800,'authorization_reference':'user-explicit-formal-six-conditions-and-max-three-warp-devices','oauth_authorized_by_this_file':False})
command=['python3',str(r/'guard_production_release.py'),'--manifest',str(manifest_path),'--manifest-sha256',pin,'--run','--approval',str(approval),'--approval-sha256',sha(approval),'--transaction-root',str(t),'--inbox',str(t/'inbox')]
with (t/'coordinator.private.log').open('xb') as log:proc=subprocess.Popen(command,cwd=r,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
save(t/'process.safe.json',{'pid':proc.pid,'transaction_name':name})
print(json.dumps({'prepared':True,'transaction_started':True,'transaction_name':name,'pid':proc.pid,'manifest_sha256':pin}))
'''


def main():
    import argparse,base64
    sys.path.insert(0,str(BUNDLE))
    from guard_external_launcher import call
    from github_artifact_transport import GitHubArtifactClient
    from hosted_phase_publisher import Publisher
    from watch_existing_hosted_transaction import watch_existing
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    manifest=json.loads((BUNDLE/'manifest.linux.review.json').read_text());pin=digest(manifest)
    assert pin=='5ef1f8d6202f449aa443a975867182c68ae9bf6d77827557bc10ceaff8414c9b'
    sources={}
    for name,wanted in manifest['reviewed_sources'].items():
        assert sha(BUNDLE/name)==wanted
        sources[name]=base64.b64encode((BUNDLE/name).read_bytes()).decode()
    recovery=json.loads((HERE/'fresh-recovery.handle.safe.json').read_text())
    workflow=json.loads((HERE/'full-phase-workflow-source.safe.json').read_text())
    authorization=json.loads((HERE/'full-collection-authorization.safe.json').read_text())
    assert authorization['maximum_temporary_device_registrations']==3
    assert authorization['manifest_sha256']==workflow['manifest_sha256']==pin
    assert authorization['workflow_sha256']==workflow['workflow_sha256']
    if args.run:
        assert not (HERE/'hosted-production-transaction.handle.safe.json').exists(),'Inspect the existing transaction; do not launch another.'
        assert not authorization.get('dispatch_attempts')
    helper=HERE.parent.parent/'prp_remote.py';namespace={'__file__':str(helper)}
    exec(helper.read_text(encoding='utf-8').split('try:\n    client.connect',1)[0],namespace)
    client=namespace['client'];credentials=namespace['values']
    try:
        client.connect(credentials['IP'],username=credentials['\u8d26\u53f7'],password=credentials['\u5bc6\u7801'],timeout=20,look_for_keys=False,allow_agent=False)
        prepared=call(client,PREPARE,{'manifest':manifest,'pin':pin,'sources':sources,'recovery_directory':recovery['directory'],'run':args.run})
        print(json.dumps(prepared),flush=True)
        if not args.run:return
        save(HERE/'hosted-production-transaction.handle.safe.json',prepared)
        sys.path.insert(0,str(HERE.parent.parent))
        import prp_github_admin as github
        artifacts=GitHubArtifactClient(github.creds['password'])
        publisher=BudgetPublisher(Publisher(github.api,artifacts,workflow['commit'],workflow['workflow_sha256'],1261866723,123868412,warp_authorized=True),HERE/'full-collection-authorization.safe.json')
        cli=json.loads((HERE/'gh-verifier.pin.safe.json').read_text())
        # The CLI executable's immutable pin is independently checked by bridge.
        cli_path=HERE/'portable-gh-2.103.2/gh.exe'
        cli_sha='f1efa3796052b576a11abcc8e69c3966cf54e5858c94cc7bdae0d9fbf7ee91d8'
        result=watch_existing(client,prepared['transaction_name'],manifest,pin,publisher,cli_path,cli_sha)
        save(HERE/'hosted-production-watch.safe.json',result)
        print(json.dumps(result),flush=True)
    finally:client.close()


if __name__=='__main__':main()
