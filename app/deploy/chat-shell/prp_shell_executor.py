#!/usr/bin/python3 -I
"""Root-owned forced-SSH execution target; OFF unless separately installed.

Accept only an encrypted GitHub-comment envelope over stdin. A dedicated
forced-command SSH identity + exact-command sudoers rule is a prerequisite.
Never pass caller's SSH_ORIGINAL_COMMAND or shell arguments into Bash.
"""
import json
import os
from pathlib import Path
import pwd
import resource
import signal
import sqlite3
import stat
import subprocess
import sys
# -I disables user PYTHONPATH; load only the independently installed root-owned module.
sys.path.insert(0, '/usr/local/sbin')
import tempfile
import time

from protocol import (InvalidJob, b64_decode, b64_encode, openssl_cms_decrypt,
                      openssl_cms_encrypt, strict_json, validate_payload)

DIR = Path('/etc/matrix-prp-chat-shell')
PRIVATE_KEY = DIR/'recipient.key'
CERT = DIR/'recipient.crt'
STATE_DIR = Path('/var/lib/matrix-prp-chat-shell')
STATE_DB = STATE_DIR/'claimed.sqlite3'
EXEC_USER = 'prp-shell'
MAX_OUTPUT = 10000

def require_root_only():
    if os.geteuid()!=0 or sys.argv != [sys.argv[0]]:
        raise InvalidJob('root forced-command required')
    if os.environ.get('SSH_ORIGINAL_COMMAND')!='run':
        raise InvalidJob('wrong SSH command')
    for path, kind, perm in ((DIR,stat.S_IFDIR,0o700), (PRIVATE_KEY,stat.S_IFREG,0o400),
                             (CERT,stat.S_IFREG,0o444), (STATE_DIR,stat.S_IFDIR,0o700)):
        st=path.lstat()
        if stat.S_IFMT(st.st_mode)!=kind or st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=perm:
            raise InvalidJob('insecure local installation')
    if STATE_DB.exists():
        st=STATE_DB.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o600:
            raise InvalidJob('insecure replay ledger')
    acct=pwd.getpwnam(EXEC_USER)
    if acct.pw_uid<=0 or acct.pw_gid<=0:
        raise InvalidJob('invalid execution identity')
    return acct

def claim(job_id, nonce):
    # Durable host-side one-use barrier, committed BEFORE running a shell.
    with sqlite3.connect(STATE_DB,timeout=10,isolation_level=None) as db:
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS claimed (job_id TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL, created_at INTEGER NOT NULL)')
        try:
            db.execute('INSERT INTO claimed(job_id, nonce, created_at) VALUES(?,?,?)',(job_id,nonce,int(time.time())))
        except sqlite3.IntegrityError as exc:
            db.execute('ROLLBACK')
            raise InvalidJob('duplicate job or nonce') from exc
        db.execute('COMMIT')
    os.chmod(STATE_DB,0o600)

def execute(command,timeout_seconds,account):
    """Bash accepts arbitrary syntax, but runs as distinct unprivileged user."""
    def drop_user():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':account.pw_dir,
         'LANG':'C.UTF-8','USER':EXEC_USER,'LOGNAME':EXEC_USER}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c',command],
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,preexec_fn=drop_user,
            close_fds=True,start_new_session=True,cwd='/',env=env)
        timed_out=False
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out=True
            os.killpg(proc.pid,signal.SIGKILL)
            proc.wait()
        out.seek(0);err.seek(0)
        stdout=out.read(MAX_OUTPUT+1)
        stderr=err.read(MAX_OUTPUT+1)
    return {'exitCode':proc.returncode,'timedOut':timed_out,
            'truncated':len(stdout)>MAX_OUTPUT or len(stderr)>MAX_OUTPUT,
            'stdout':stdout[:MAX_OUTPUT].decode('utf-8','replace'),
            'stderr':stderr[:MAX_OUTPUT].decode('utf-8','replace')}

def process_request(request,account,now=None):
    if not isinstance(request,dict) or set(request)!={'jobId','ciphertext'}:
        raise InvalidJob('invalid transport')
    job_id=request['jobId']
    ciphertext=b64_decode(request['ciphertext'],40000)
    data=strict_json(openssl_cms_decrypt(ciphertext,PRIVATE_KEY,CERT))
    job=validate_payload(data,job_id,now=now)
    claim(job['jobId'],job['nonce'])
    result=execute(job['command'],job['runSeconds'],account)
    result.update({'version':1,'jobId':job['jobId']})
    response_plain=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
    if len(response_plain)>15000:
        # Terminal control bytes can expand dramatically under JSON escaping.
        # Retain a bounded encrypted response instead of losing all results.
        result['stdout']=result['stdout'][:1000]
        result['stderr']=result['stderr'][:1000]
        result['truncated']=True
        response_plain=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
    response_cipher=b64_encode(openssl_cms_encrypt(response_plain,job['answerCertificate'].encode('ascii')))
    if len(response_cipher)>60000:
        raise InvalidJob('result ciphertext exceeds limit')
    return {'jobId':job['jobId'],'ciphertext':response_cipher}

def main():
    account=require_root_only()
    os.environ['PATH']='/usr/sbin:/usr/bin:/sbin:/bin'
    message=sys.stdin.buffer.read(42000)
    if len(message)>41000:
        raise InvalidJob('transport oversized')
    request=strict_json(message)
    response=process_request(request,account)
    sys.stdout.write(json.dumps(response,separators=(',',':'))+'\n')

if __name__=='__main__':
    try:
        main()
    except InvalidJob:
        sys.stderr.write('PRP_SHELL_REQUEST_REJECTED\n')
        sys.exit(2)
    except Exception:
        sys.stderr.write('PRP_SHELL_INTERNAL_ERROR\n')
        sys.exit(3)
