"""Administrator-only exact one-line V20 controller upgrade. Never grants deploy SSH root.

Run check first; apply requires the reviewed digest and a successful isolated
rehearsal using the staged, checksum-verified main artifact. Rollback restores
only controller bytes, never SQL or application releases.
"""
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import tempfile

TARGET = Path('/usr/local/sbin/prp-release')
OLD = '7d23ea686b7eca6e66619979357953a0a18fc366d4896f900ea6cae743b396d1'
NEW = 'bafcd9d7d79d478cf0751db9c49d2456f92a82cf6c051a4876d38fedaa7c566b'
COMMIT = '8e7fc03655b61e7038ea3363864a1207441169f8'
REVIEW = Path('/root/prp-v20-review')
BACKUP = REVIEW / 'controller-backup'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def service():
    return subprocess.check_output(['systemctl','show','matrix-prp','-p','ActiveState','-p','MainPID','-p','ExecMainStartTimestamp','-p','NRestarts']).decode()


def replace(data):
    fd,name = tempfile.mkstemp(prefix='.prp-release-',dir=TARGET.parent)
    os.close(fd)
    temp = Path(name)
    try:
        subprocess.run(['cp','--preserve=all','--',str(TARGET),str(temp)],check=True)
        temp.write_bytes(data)
        ast.parse(data)
        with temp.open('rb') as stream: os.fsync(stream.fileno())
        os.replace(temp,TARGET)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','apply','rollback'])
    parser.add_argument('--approved-sha256')
    args=parser.parse_args()
    if os.geteuid()!=0: raise SystemExit('Administrator required')
    st=TARGET.lstat()
    assert stat.S_ISREG(st.st_mode) and (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))==(0,0,0o755)
    with Path('/var/lib/matrix-prp-deploy/deploy.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action=='rollback':
            assert args.approved_sha256==OLD and sha(TARGET)==NEW and sha(BACKUP/'controller.before')==OLD
            replace((BACKUP/'controller.before').read_bytes())
            assert sha(TARGET)==OLD
            print('Controller bytes restored; remeasure/review SSH baseline before further publication. No SQL/service rollback performed.')
            return
        assert sha(TARGET)==OLD, 'Unreviewed installed controller drift'
        candidate=REVIEW/'prp-release.candidate.py'
        assert not candidate.is_symlink() and candidate.stat().st_uid==0 and not candidate.stat().st_mode&0o022
        assert sha(candidate)==NEW
        old=TARGET.read_bytes()
        needle=b"'prp_ai_conversation_meta','prp_wellness_ai_action_targets'}"
        assert old.count(needle)==1
        assert candidate.read_bytes()==old.replace(needle,b"'prp_ai_conversation_meta','prp_wellness_ai_action_targets','prp_vocal_takes'}")
        ast.parse(candidate.read_bytes())
        if args.action=='check':
            print(json.dumps({'old_sha256':OLD,'new_sha256':NEW,'exact_one_line_diff':True,'syntax':'PASS','production_modified':False}))
            return
        assert args.approved_sha256==NEW, 'Exact administrator-approved digest required'
        assert not BACKUP.exists(), 'Do not overwrite previous review evidence'
        m=runpy.run_path(str(candidate),run_name='candidate_isolated_rehearsal')
        assert m['schema_version']()==19
        initial=m['database_state']()
        current=(m['BASE']/'current').resolve()
        initial_service=service()
        assert 'ActiveState=active' in initial_service
        initial_rows=m['snapshot']()
        protected=[Path('/usr/local/sbin/prp-diagnose'),Path('/usr/local/bin/prp-deploy-gateway'),Path('/home/prp-deploy/.ssh/authorized_keys'),Path('/etc/ssh/sshd_config')]
        protected+=list(Path('/etc/ssh/sshd_config.d').glob('*'))+list(Path('/etc/sudoers.d').glob('*'))
        protected={str(p):sha(p) for p in protected if p.is_file()}
        release=m['BASE']/'r38998871574-1'
        meta=json.loads((release/'release.json').read_text())
        assert meta['commit']==COMMIT and meta['schema_version']==20
        for name,digest in meta['files'].items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha(release/name)==digest
        BACKUP.mkdir(mode=0o700)
        shutil.copy2(TARGET,BACKUP/'controller.before')
        shutil.copy2(REVIEW/'independent-policy-inventory.json',BACKUP/'policy-inventory.before.json')
        shutil.copytree('/etc/matrix-prp',BACKUP/'config')
        (BACKUP/'historical.before.json').write_text(json.dumps(initial_rows))
        # Existing exact production routines: full dump, isolated restore/migrate,
        # all historical fingerprints, new-table empty assertion, cleanup/revoke.
        m['rehearse'](release,meta,BACKUP)
        assert json.loads((BACKUP/'progress.json').read_text())['phase']=='preflight-passed'
        assert m['database_state']()==initial and (m['BASE']/'current').resolve()==current and service()==initial_service
        assert m['snapshot']()==initial_rows, 'Concurrent business writes; stop for a fresh review'
        assert all(sha(Path(p))==digest for p,digest in protected.items())
        assert sha(TARGET)==OLD
        replace(candidate.read_bytes())
        try:
            assert sha(TARGET)==NEW and service()==initial_service and m['database_state']()==initial
            assert all(sha(Path(p))==digest for p,digest in protected.items())
            st=TARGET.lstat()
            assert (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))==(0,0,0o755)
        except Exception:
            replace(old)
            raise
        receipt={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'old_sha256':OLD,'new_sha256':NEW,
            'candidate_commit':COMMIT,'isolated_v19_to_v20':'PASS','historical_fingerprints':'PASS',
            'backup_sha256':sha(BACKUP/'preflight.sql'),'backup_bytes':(BACKUP/'preflight.sql').stat().st_size,
            'service_unchanged':True,'production_schema_version':19,'production_migrated':False,
            'ssh_permissions_unchanged':True,'application_published':False,'service_before':initial_service}
        (BACKUP/'receipt.json').write_text(json.dumps(receipt,indent=2))
        print(json.dumps(receipt))


if __name__=='__main__': main()
