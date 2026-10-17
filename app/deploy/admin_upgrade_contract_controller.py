"""Administrator-only versioned migration-policy controller upgrade. Never grants deploy SSH root.

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
import zipfile

TARGET = Path('/usr/local/sbin/prp-release')
OLD = 'ae01801d85b01a6f978f0d030aad052b72e778f3e50185daf33445c2d32d7f7a'
NEW = 'c329836ed2f48296e5ab505451aab3c59b33db7f7c20aba5ae7c2b1ec80622e2'
COMMIT = '4ba1cce1521329fce302c30dc2bfbd5a3339b7bd'
REVIEW = Path('/root/prp-contract-review')
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


def reviewed_function_diff(old,new):
    old_functions={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(old).body if isinstance(n,ast.FunctionDef)}
    new_functions={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(new).body if isinstance(n,ast.FunctionDef)}
    changed={name for name in old_functions if old_functions[name]!=new_functions.get(name)}
    assert changed=={'snapshot','assert_preserved','unpack','rehearse','deploy_backend'},changed
    assert set(new_functions)-set(old_functions)=={'migration_policy_unique','migration_policy_load','migration_policy_sql_tables','migration_policy_validate','migration_policy_for_release'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['check','apply','rollback']);parser.add_argument('--approved-sha256');args=parser.parse_args()
    assert os.geteuid()==0
    st=TARGET.lstat();assert stat.S_ISREG(st.st_mode) and (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))==(0,0,0o755)
    with Path('/var/lib/matrix-prp-deploy/deploy.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action=='rollback':
            assert args.approved_sha256==OLD and sha(TARGET)==NEW and sha(BACKUP/'controller.before')==OLD
            replace((BACKUP/'controller.before').read_bytes());assert sha(TARGET)==OLD
            print('Controller restored; remeasure policy baseline. No SQL/application rollback.');return
        assert sha(TARGET)==OLD
        candidate=REVIEW/'prp-release.candidate.py';assert candidate.is_file() and not candidate.is_symlink()
        assert candidate.stat().st_uid==0 and not candidate.stat().st_mode&0o022 and sha(candidate)==NEW
        reviewed_function_diff(TARGET.read_bytes(),candidate.read_bytes())
        if args.action=='check':
            print(json.dumps({'old_sha256':OLD,'new_sha256':NEW,'reviewed_changed_functions':5,'new_contract_functions':5,'syntax':'PASS','production_modified':False}));return
        assert args.approved_sha256==NEW and not BACKUP.exists()
        m=runpy.run_path(str(candidate),run_name='contract_rehearsal_only')
        assert m['schema_version']()==20
        initial=m['database_state']();rows=m['snapshot']();initial_service=service();assert 'ActiveState=active' in initial_service
        current=(m['BASE']/'current').resolve();assert json.loads((current/'release.json').read_text())['commit']=='86b1ec3ce9b97d54e084db8040464ff2b5b28a70'
        release=m['BASE']/'r39004753528-1';meta=json.loads((release/'release.json').read_text());assert meta['commit']==COMMIT and meta['schema_version']==21
        for name,digest in meta['files'].items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts and sha(release/name)==digest
        BACKUP.mkdir(mode=0o700);shutil.copy2(TARGET,BACKUP/'controller.before');shutil.copytree('/etc/matrix-prp',BACKUP/'config')
        shutil.copy2(REVIEW/'independent-policy-inventory.json',BACKUP/'policy-inventory.before.json')
        (BACKUP/'historical.before.json').write_text(json.dumps(rows))
        legacy=BACKUP/'legacy-v21';legacy.mkdir(mode=0o700);m['rehearse'](release,meta,legacy)
        with tempfile.TemporaryDirectory(dir=m['BASE'],prefix='.contract-probe-') as tmp:
            probe=Path(tmp);shutil.copytree(release,probe,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.migration-runtime'))
            sql=b'CREATE TABLE prp_controller_contract_probe (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;'
            with zipfile.ZipFile(probe/'backend.jar','a') as jar:jar.writestr('BOOT-INF/classes/db/migration/V22__controller_contract_probe.sql',sql)
            policy={'schema_version':1,'commit':COMMIT,'rules':[{'version':22,'file':'V22__controller_contract_probe.sql','sha256':hashlib.sha256(sql).hexdigest(),'mode':'create-empty','tables':['prp_controller_contract_probe']}]}
            raw=json.dumps(policy).encode();(probe/'migration-policy.json').write_bytes(raw)
            metadata=dict(meta,id='controller-contract-probe-only',schema_version=22)
            metadata['files']={str(p.relative_to(probe)):sha(p) for p in probe.rglob('*') if p.is_file() and p.name!='release.json'}
            (probe/'release.json').write_text(json.dumps(metadata))
            assert m['migration_policy_for_release'](probe,metadata,20)=={'prp_controller_contract_probe'}
            for mutation in ('commit','table'):
                forged=json.loads(raw);forged['commit']='f'*40 if mutation=='commit' else COMMIT
                if mutation=='table':forged['rules'][0]['tables']=['prp_undeclared_probe']
                (probe/'migration-policy.json').write_text(json.dumps(forged));forged_meta=dict(metadata,files=dict(metadata['files']))
                forged_meta['files']['migration-policy.json']=sha(probe/'migration-policy.json')
                try:m['migration_policy_for_release'](probe,forged_meta,20)
                except ValueError:pass
                else:raise AssertionError('Forged policy accepted')
            (probe/'migration-policy.json').write_bytes(raw)
            for p in [probe,*probe.rglob('*')]:
                os.chown(p,0,m['ACCOUNT'].pw_gid);p.chmod(0o755 if p.is_dir() else 0o644)
            (probe/'backend.jar').chmod(0o640)
            generic=BACKUP/'synthetic-v22';generic.mkdir(mode=0o700);m['rehearse'](probe,metadata,generic)
            assert json.loads((generic/'progress.json').read_text())['phase']=='preflight-passed'
        assert m['database_state']()==initial and m['snapshot']()==rows and service()==initial_service and (m['BASE']/'current').resolve()==current
        assert sha(TARGET)==OLD
        replace(candidate.read_bytes())
        try:
            assert sha(TARGET)==NEW and service()==initial_service and m['database_state']()==initial
            st=TARGET.stat();assert (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))==(0,0,0o755)
        except Exception:
            replace((BACKUP/'controller.before').read_bytes());raise
        receipt={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'old_sha256':OLD,'new_sha256':NEW,
            'legacy_v20_to_v21':'PASS','synthetic_v20_to_v22_new_unlisted_table':'PASS','forged_contract_rejections':'PASS',
            'historical_rows_and_schema':'PASS','production_schema_version':20,'production_migrated':False,
            'application_published':False,'service_unchanged':True,'service_before':initial_service,
            'backups':{name:{'sha256':sha(BACKUP/name/'preflight.sql'),'bytes':(BACKUP/name/'preflight.sql').stat().st_size} for name in ('legacy-v21','synthetic-v22')}}
        (BACKUP/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))


if __name__=='__main__':main()
