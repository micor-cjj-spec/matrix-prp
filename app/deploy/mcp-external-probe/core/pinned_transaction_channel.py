"""Existing pinned admin SSH channel, scoped to one guard transaction.

No connection credentials, deployment start, reload or configuration writes.
Only the transaction's private inbox is writable by submit().
"""
import base64
import hashlib
import re
from guard_release_engine import GateError, digest
from guard_external_launcher import call

ROOT='/root/prp-guard-release-20261024-v4'
HOST_PIN='NOEkvKq3BcBnErn+vjNMyjPaEt21xXLUJptsK9HXX64'

REMOTE = r'''
import base64,hashlib,json,os,pathlib,stat,sys
request=json.load(sys.stdin)
root=pathlib.Path('/root/prp-guard-release-20261024-v4')
transaction=root/'guard-release-transactions'/request['transaction']
def private(path,directory=False):
 st=path.lstat()
 if path.is_symlink() or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)!=(0o700 if directory else 0o600):raise RuntimeError('PRIVATE_PATH_POLICY')
 if directory and not path.is_dir():raise RuntimeError('DIRECTORY_REQUIRED')
 if not directory and not path.is_file():raise RuntimeError('FILE_REQUIRED')
def read_json(path):
 private(path)
 if path.stat().st_size>4000000:raise RuntimeError('FILE_LIMIT')
 return json.loads(path.read_text())
private(transaction,True)
journal=transaction/'transaction.json'
state=read_json(journal)
terminal={'ACCEPT','REJECTED','ROLLED_BACK','RECOVERY_REQUIRED'}
active={'PREFLIGHT':'preflight','COLLECT_EXTERNAL_EVIDENCE':'post_reload','POST_ROLLBACK':'post_rollback'}
if state['state'] in terminal:
 if request['operation']!='read':raise RuntimeError('TRANSACTION_TERMINAL')
 print(json.dumps({'state':state['state'],'deployment_id':state['deployment_id']}));sys.exit(0)
if state['state'] not in active:
 if request['operation']!='read':raise RuntimeError('TRANSACTION_NOT_COLLECTING')
 print(json.dumps({'state':state['state']}));sys.exit(0)
job=state['active_job']
if job['manifest_sha256']!=request['pin'] or job['phase']!=active[state['state']]:raise RuntimeError('JOB_IDENTITY')
owner=read_json(root/'host-guard/policy-b-release.lock/owner.json')
if owner['deployment_id']!=job['deployment_id'] or type(owner['pid']) is not int or owner['pid']<=0:raise RuntimeError('OWNER_IDENTITY')
os.kill(owner['pid'],0)
argv=(pathlib.Path('/proc')/str(owner['pid'])/'cmdline').read_bytes().split(b'\0')
if str(transaction).encode() not in argv or str(root/'guard_production_release.py').encode() not in argv:raise RuntimeError('OWNER_COMMAND_IDENTITY')
manifest=request['manifest']
def hash_file(p):
 if p.is_symlink() or not p.is_file():raise RuntimeError('SOURCE_FILE_REQUIRED')
 return hashlib.sha256(p.read_bytes()).hexdigest()
if hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=request['pin']:raise RuntimeError('MANIFEST_PIN')
sources={}
for name,wanted in manifest['reviewed_sources'].items():
 if pathlib.Path(name).name!=name:raise RuntimeError('SOURCE_NAME')
 sources[name]=hash_file(root/name)
 if sources[name]!=wanted:raise RuntimeError('SOURCE_DRIFT')
config={}
for name,wanted in job['source_config'].items():
 if name in ('micor.top.conf','prp-mcp-test.conf'):path=pathlib.Path('/etc/nginx/conf.d')/name
 elif name=='nginx_binary':path=pathlib.Path('/usr/sbin/nginx')
 elif name in ('/etc/nginx/nginx.conf','/etc/nginx/mime.types','/etc/nginx/snippets/matrix-prp.conf','/etc/nginx/conf.d/prp-rate-limit.conf'):path=pathlib.Path(name)
 else:raise RuntimeError('UNREVIEWED_CONFIG_PATH')
 config[name]=hash_file(path)
 if config[name]!=wanted:raise RuntimeError('CONFIG_DRIFT')
local=read_json(transaction/'local-attestation.json') if job['phase']=='post_reload' else None
context={'state':state['state'],'deployment_id':job['deployment_id'],'active_job':job,'owner_alive':True,'source_config':config,'reviewed_sources':sources,'local_attestation':local}
if read_json(journal)!=state:raise RuntimeError('TRANSACTION_CHANGED')
if request['operation']=='read':
 key_path=transaction/'session-key.private';private(key_path)
 key=key_path.read_bytes()
 if len(key)!=32:raise RuntimeError('KEY_LENGTH')
 print(json.dumps({'state':state['state'],'job':job,'context':context,'key':base64.b64encode(key).decode()}))
elif request['operation']=='submit':
 if request['job']!=job:raise RuntimeError('SUBMISSION_JOB_CHANGED')
 inbox=transaction/'inbox';private(inbox,True)
 filename=job['deployment_id']+'.'+job['phase']+'.'+job['nonce']+'.json'
 if any(c not in '0123456789abcdef._' for c in filename):raise RuntimeError('INBOX_NAME')
 payload=json.dumps(request['envelope'],sort_keys=True,separators=(',',':')).encode()
 if len(payload)>4000000:raise RuntimeError('ENVELOPE_LIMIT')
 final=inbox/filename;pending=inbox/(filename+'.channel-pending')
 fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
  if read_json(journal)!=state:raise RuntimeError('TRANSACTION_CHANGED_BEFORE_DELIVERY')
  os.link(pending,final) # Never overwrite an existing nonce receipt.
  fd=os.open(inbox,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:pending.unlink()
 print(json.dumps({'stored':True}))
else:raise RuntimeError('UNSUPPORTED_OPERATION')
'''


class PinnedChannel:
    def __init__(self, client, transaction, manifest, pin):
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9-]{0,99}',transaction) or digest(manifest)!=pin:
            raise GateError('UNAPPROVED_TRANSACTION_OR_MANIFEST')
        self.client,self.transaction,self.manifest,self.pin=client,transaction,manifest,pin

    def _call(self, operation, **extra):
        transport=self.client.get_transport()
        if transport is None or not transport.is_active() or not transport.is_authenticated():
            raise GateError('PINNED_ADMIN_CHANNEL_UNAVAILABLE')
        fingerprint=base64.b64encode(hashlib.sha256(transport.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
        if fingerprint!=HOST_PIN:raise GateError('ADMIN_HOST_PIN_MISMATCH')
        return call(self.client,REMOTE,dict(operation=operation,transaction=self.transaction,
                    manifest=self.manifest,pin=self.pin,**extra))

    def read(self):
        result=self._call('read')
        if 'key' in result:
            try:key=base64.b64decode(result.pop('key'),validate=True)
            except (ValueError,TypeError):raise GateError('PRIVATE_CHANNEL_KEY_FORMAT') from None
            if len(key)!=32:raise GateError('PRIVATE_CHANNEL_KEY_LENGTH')
            return result,key
        return result,None

    def submit(self,job,envelope):
        receipt=self._call('submit',job=job,envelope=envelope)
        if receipt!={'stored':True}:raise GateError('PRIVATE_INBOX_RECEIPT')
