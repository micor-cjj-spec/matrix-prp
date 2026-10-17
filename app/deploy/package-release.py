#!/usr/bin/env python3
"""Create a checksummed release; no credentials or user data enter the artifact."""
import hashlib,json,subprocess,tarfile,tempfile,shutil,sys,re
from pathlib import Path
from migration_policy import migration_policy_load, migration_policy_validate, migration_policy_for_release

root=Path(__file__).resolve().parents[2]
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
release_id=sys.argv[1]
if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}',release_id):raise SystemExit('Invalid release ID')
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)
 shutil.copy2(root/'app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar',p/'backend.jar')
 shutil.copytree(root/'app/web/dist',p/'web')
 migrations=root/'app/backend/src/main/resources/db/migration'
 version=max(int(re.match(r'V(\d+)__',x.name)[1]) for x in migrations.glob('V*__*.sql'))
 policy=migration_policy_load((root/'app/deploy/migration-policy.json').read_bytes())
 policy['commit']=commit
 sql_files={int(re.match(r'V(\d+)__',x.name)[1]):(x.name,x.read_bytes().replace(b'\r\n',b'\n')) for x in migrations.glob('V*__*.sql')}
 migration_policy_validate(policy,sql_files,commit)
 (p/'migration-policy.json').write_text(json.dumps(policy,sort_keys=True,separators=(',',':')),encoding='utf-8')

 backend_source=subprocess.check_output(['git','rev-parse','HEAD:app/backend'],cwd=root,text=True).strip()
 web_source=hashlib.sha256(subprocess.check_output(['git','ls-tree','HEAD','app/web','app/scripts','app/config'],cwd=root)).hexdigest()
 files={str(x.relative_to(p)).replace('\\','/'):hashlib.sha256(x.read_bytes()).hexdigest() for x in p.rglob('*') if x.is_file()}
 migration_policy_for_release(p,{'commit':commit,'schema_version':version,'files':files},0)
 (p/'release.json').write_text(json.dumps({'id':release_id,'commit':commit,'schema_version':version,'backend_source':backend_source,'web_source':web_source,'files':files},indent=2),encoding='utf-8')
 with tarfile.open(root/'release.tar.gz','w:gz') as archive:
  for item in sorted(p.iterdir()):archive.add(item,arcname=item.name)
 print('Packaged',release_id,'commit',commit,'schema',version)
