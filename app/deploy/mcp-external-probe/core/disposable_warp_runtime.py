"""Review candidate: temporary network on an explicitly approved hosted VM.

No PRP requests are sent here. The caller owns the immutable probe matrix.
Never serialize subprocess output, registration data, or exception messages.
"""
import os
from pathlib import Path
import re
import signal
import subprocess
import time


class RuntimeErrorSafe(Exception): pass


class WarpRuntime:
    def __init__(self):
        self.attempted=False
        self.steps=[]
        self.deadline=None
        self.cleanup=None

    def run(self,label,args,seconds,required=True,cleanup=False):
        remaining=self.deadline-time.monotonic()-(0 if cleanup else 40)
        if remaining<=0:raise RuntimeErrorSafe('RUNTIME_DEADLINE')
        started=time.monotonic()
        env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='a')
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  env=env,start_new_session=True)
        try:
            out,err=process.communicate(timeout=min(seconds,remaining));code=process.returncode
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.communicate();out=b'';code=None
        self.steps.append({'step':label,'exit_code':code,'timed_out':code is None,
                           'elapsed_seconds':round(time.monotonic()-started,3)})
        if required and code!=0:raise RuntimeErrorSafe('RUNTIME_COMMAND_FAILED')
        return code,out

    def __enter__(self):
        conditions={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux',
                    'PRP_WARP_COLLECTION_APPROVED':'true',
                    'GITHUB_REPOSITORY':'micor-cjj-spec/matrix-prp',
                    'GITHUB_REF':'refs/heads/fix/mcp-hosted-network-probe-20261024'}
        if os.name!='posix' or any(os.environ.get(k)!=v for k,v in conditions.items()):
            raise RuntimeErrorSafe('DISPOSABLE_APPROVED_RUNNER_REQUIRED')
        if 'VERSION_CODENAME=noble' not in Path('/etc/os-release').read_text():
            raise RuntimeErrorSafe('PINNED_RUNNER_OS_REQUIRED')
        self.deadline=time.monotonic()+800
        temp=Path(os.environ['RUNNER_TEMP'])
        key=temp/'prp-cloudflare-public.gpg';source=temp/'prp-cloudflare.list'
        try:
            self.run('public_key_download',['curl','--proto','=https','--fail','--silent','--show-error',
                '--connect-timeout','8','--max-time','20','--output',str(key),'https://pkg.cloudflareclient.com/pubkey.gpg'],25)
            self.run('public_key_install',['sudo','gpg','--batch','--yes','--dearmor','--output',
                '/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg',str(key)],15)
            source.write_text('deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ noble main\n')
            self.run('repository_install',['sudo','install','-m','644',str(source),'/etc/apt/sources.list.d/cloudflare-client.list'],10)
            self.run('package_index',['sudo','apt-get','update','-o','Acquire::Retries=0','-o','Acquire::http::Timeout=15'],90)
            self.run('client_install',['sudo','apt-get','install','--assume-yes','--no-install-recommends','cloudflare-warp=2026.8.2115.0'],180)
            _,out=self.run('client_version',['warp-cli','--version'],5)
            if not re.search(rb'\b2026\.8\.2115\.0\b',out):raise RuntimeErrorSafe('CLIENT_VERSION_MISMATCH')
            self.attempted=True
            self.run('registration',['warp-cli','--accept-tos','registration','new'],30)
            self.run('mode',['warp-cli','--accept-tos','mode','warp+doh'],10)
            self.run('connect',['warp-cli','--accept-tos','connect'],10)
            until=time.monotonic()+30
            while time.monotonic()<until:
                code,out=self.run('readiness',['warp-cli','--accept-tos','status'],4,False)
                if code==0 and re.search(rb'Status update:\s*Connected\b',out):return self
                time.sleep(1)
            raise RuntimeErrorSafe('TUNNEL_READINESS_UNVERIFIED')
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.attempted:
            self.cleanup={'registration_not_attempted':True}
            return
        # Cleanup has its own bounded reserve even if collection exhausted the
        # setup budget. Workflow timeout must include these extra 35 seconds.
        self.deadline=time.monotonic()+35
        results={}
        commands=[('disconnect',['warp-cli','--accept-tos','disconnect'],12),
                  ('delete',['warp-cli','--accept-tos','registration','delete'],12),
                  ('absence',['warp-cli','--accept-tos','registration','show'],5)]
        for label,args,budget in commands:
            try:results[label]=self.run('cleanup_'+label,args,budget,False,True)
            except Exception:results[label]=(None,b'')
        code,out=results['absence']
        missing=any(s in out.lower() for s in [b'registration missing',b'missing registration',b'missingregistration',b'registration not found'])
        self.cleanup={'disconnect_succeeded':results['disconnect'][0]==0,
                      'delete_succeeded':results['delete'][0]==0,
                      'local_absence_confirmed':code not in (None,0) and missing,
                      'remote_deletion_independently_verified':False}

    def __exit__(self,kind,error,trace):
        self.close()
        if not all(self.cleanup.get(k) is True for k in ('disconnect_succeeded','delete_succeeded','local_absence_confirmed')):
            raise RuntimeErrorSafe('TEMPORARY_REGISTRATION_CLEANUP_UNVERIFIED')
        return False
