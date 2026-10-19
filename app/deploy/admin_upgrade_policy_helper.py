#!/usr/bin/python3 -I
"""Explicit administrator-only one-file helper upgrade. No SSH/database/service mutations."""
import argparse,ast,datetime,fcntl,hashlib,json,os,re,shutil,stat,subprocess,tempfile
from pathlib import Path

TARGET=Path('/usr/local/sbin/prp-diagnose')
CONTROLLER=Path('/usr/local/sbin/prp-release')
BASE=Path('/var/backups/prp-policy-attestor')
OLD='9070861e69b3ec2a0106f3e6c9992f3344397eecccd9cc80e42370392517121f'
CONTROLLER_SHA='c329836ed2f48296e5ab505451aab3c59b33db7f7c20aba5ae7c2b1ec80622e2'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require_clock_only_change(before,after):
    old=ast.parse(before).body;new=ast.parse(after).body
    if len(old)!=len(new):raise ValueError('Only the reviewed daemon_birth function may change')
    changed=[]
    for a,b in zip(old,new):
        if ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False):continue
        if not isinstance(a,ast.FunctionDef) or not isinstance(b,ast.FunctionDef) or a.name!=b.name:
            raise ValueError('Unexpected helper change')
        changed.append(a.name)
    if changed!=['daemon_birth']:raise ValueError('Only daemon_birth may change')
def state():
    files=[CONTROLLER,Path('/usr/local/bin/prp-deploy-gateway'),Path('/home/prp-deploy/.ssh/authorized_keys'),Path('/etc/ssh/sshd_config')]
    files+=sorted(Path('/etc/ssh/sshd_config.d').glob('*'))+sorted(Path('/etc/sudoers.d').glob('*'))
    hashes={str(p):{'sha256':digest(p),'uid':p.stat().st_uid,'gid':p.stat().st_gid,'mode':stat.S_IMODE(p.stat().st_mode)} for p in files if p.is_file()}
    service=subprocess.check_output(['/usr/bin/systemctl','show','matrix-prp','-p','MainPID','-p','ExecMainStartTimestamp','-p','NRestarts']).decode()
    return {'hashes':hashes,'service':service}
def replace(source):
    fd,name=tempfile.mkstemp(prefix='.prp-diagnose-',dir=TARGET.parent);os.close(fd);temp=Path(name)
    try:
        subprocess.run(['cp','--preserve=all','--',str(TARGET),str(temp)],check=True)
        temp.write_bytes(source);ast.parse(source)
        with temp.open('rb') as file:os.fsync(file.fileno())
        os.replace(temp,TARGET)
        directory=os.open(TARGET.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temp.exists():temp.unlink()
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','apply','rollback']);p.add_argument('--candidate',type=Path)
    p.add_argument('--approved-sha256');p.add_argument('--backup-id');a=p.parse_args()
    if os.geteuid()!=0:raise SystemExit('Administrator access required')
    with Path('/var/lib/matrix-prp-deploy/deploy.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if digest(CONTROLLER)!=CONTROLLER_SHA:raise SystemExit('STOP: production controller drift')
        st=TARGET.lstat()
        if not stat.S_ISREG(st.st_mode) or (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))!=(0,0,0o755):raise SystemExit('STOP: unexpected helper permissions')
        before=state()
        if a.action=='rollback':
            if not a.backup_id or re.fullmatch(r'[0-9]{8}T[0-9]{6}Z',a.backup_id) is None:raise SystemExit('Invalid fixed backup ID')
            backup=BASE/a.backup_id;receipt=json.loads((backup/'receipt.json').read_text())
            if digest(TARGET)!=receipt['new_sha256'] or digest(backup/'helper.before')!=OLD:raise SystemExit('STOP: rollback drift')
            replace((backup/'helper.before').read_bytes())
            if state()!=before:raise SystemExit('Protected state changed; review required')
            print('Only diagnose helper rolled back; controller, SSH policy and service untouched');return
        if a.candidate is None or a.candidate.is_symlink():raise SystemExit('Candidate regular file required')
        data=a.candidate.read_bytes();ast.parse(data);sha=hashlib.sha256(data).hexdigest()
        if digest(TARGET)!=OLD:raise SystemExit('STOP: unknown installed helper; do not overwrite')
        require_clock_only_change(TARGET.read_bytes(),data)
        print('old_sha256='+OLD);print('candidate_sha256='+sha)
        if a.action=='check':
            print('CHECK ONLY: no production file modified');return
        if a.approved_sha256!=sha:raise SystemExit('Explicit reviewed --approved-sha256 is required')
        BASE.mkdir(mode=0o700,exist_ok=True,parents=True)
        if BASE.is_symlink() or BASE.stat().st_uid!=0 or stat.S_IMODE(BASE.stat().st_mode)!=0o700:raise SystemExit('STOP: untrusted backup directory')
        backup=BASE/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup.mkdir(mode=0o700)
        shutil.copy2(TARGET,backup/'helper.before')
        if digest(backup/'helper.before')!=OLD:raise SystemExit('STOP: backup verification failed')
        receipt={'old_sha256':OLD,'new_sha256':sha,'protected_before':before}
        (backup/'receipt.json').write_text(json.dumps(receipt,indent=2))
        try:
            replace(data)
            r=subprocess.run([str(TARGET)],stdin=subprocess.DEVNULL,capture_output=True,timeout=3)
            body=json.loads(r.stdout)
            if r.returncode!=0 or r.stderr or set(body)!={'schema_version','state','code','stage','table','exception','timestamp_utc'}:raise ValueError('Legacy diagnostic compatibility failed')
            if digest(TARGET)!=sha or state()!=before:raise ValueError('Protected file/service drift detected')
        except Exception:
            replace((backup/'helper.before').read_bytes());raise
        print('ONE-FILE UPGRADE COMPLETE; backup='+str(backup))
        print('No publication authorized; collect and independently approve live baseline next')
if __name__=='__main__':main()
