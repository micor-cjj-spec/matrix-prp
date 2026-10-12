#!/usr/bin/python3
"""Root-owned release installer, invoked by the restricted deployment SSH account.

Uploaded data is an artifact, not a root shell script. Runtime secrets stay on host.
"""
import base64,fcntl,hashlib,hmac,json,os,pwd,re,shutil,subprocess,sys,tarfile,tempfile,time,urllib.request,zipfile
from pathlib import Path
import yaml

BASE=Path('/srv/matrix-prp/releases')
STATE=Path('/var/lib/matrix-prp-deploy')
BACKUPS=Path('/root/prp-deploy-backups')
CONFIG=Path('/etc/matrix-prp/application.yml')
JAVA='/usr/lib/jvm/java-21-openjdk-amd64/bin/java'
SERVICE='matrix-prp'
try:ACCOUNT=pwd.getpwnam('openclaw')
except KeyError:ACCOUNT=None  # Artifact boundary tests also run on GitHub-hosted Linux.

def log(message):print(message,flush=True)
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def sql(query,db='matrix_prp'):
 if not re.fullmatch(r'[a-zA-Z0-9_]+',db):raise ValueError('Invalid database')
 cmd=['docker','exec','-i','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot -N -B '+db]
 return subprocess.check_output(cmd,input=query.encode()).decode().strip()
def dump(path):
 with path.open('wb') as out:
  run(['docker','exec','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --default-character-set=utf8mb4 -uroot --single-transaction --routines --triggers --events --no-tablespaces matrix_prp'],stdout=out)
def restore(path,db):
 with path.open('rb') as inp:
  run(['docker','exec','-i','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot '+db],stdin=inp)
def schema_version():
 if sql("SHOW TABLES LIKE 'flyway_schema_history';")!='flyway_schema_history':return 7
 value=sql("SELECT version FROM flyway_schema_history WHERE success=1 AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1;")
 return int(value)
def snapshot(db='matrix_prp'):
 tables=sql('SHOW TABLES;',db).splitlines()
 counts={t:int(sql('SELECT COUNT(*) FROM `'+t+'`;',db)) for t in tables if t!='flyway_schema_history'}
 videos=sql('SELECT id,user_id,folder_id,storage_key,size_bytes,HEX(title) FROM prp_video_assets ORDER BY id;',db)
 return {'counts':counts,'videos':hashlib.sha256(videos.encode()).hexdigest()}
def schema_fingerprint():
 definitions=[]
 for table in sql('SHOW TABLES;').splitlines():
  if table!='flyway_schema_history':definitions.append(re.sub(r' AUTO_INCREMENT=\d+','',sql('SHOW CREATE TABLE `'+table+'`;')))
 return hashlib.sha256('\n'.join(definitions).encode()).hexdigest()
def assert_preserved(before,after):
 for table,count in before['counts'].items():
  actual=after['counts'].get(table,-1)
  if table=='prp_finance_accounts':assert actual>=count,(table,count,actual)
  else:assert actual==count,(table,count,actual)
 assert before['videos']==after['videos'],'Video ownership or records changed'
def valid_release_id(value):return bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}',value))
def unpack(archive,dest):
 with tarfile.open(archive,'r:gz') as tar:
  members=tar.getmembers()
  if len(members)>10000 or sum(m.size for m in members)>800*1024*1024:raise ValueError('Artifact too large')
  names=set()
  for m in members:
   path=Path(m.name)
   if path.is_absolute() or '..' in path.parts or not (m.isfile() or m.isdir()) or m.name in names:raise ValueError('Unsafe archive member')
   names.add(m.name)
   if path.parts[0] not in {'backend.jar','web','release.json'}:raise ValueError('Unexpected artifact member')
  tar.extractall(dest,filter='data')
 meta=json.loads((dest/'release.json').read_text())
 if not valid_release_id(meta['id']) or not re.fullmatch('[0-9a-f]{40}',meta['commit']):raise ValueError('Invalid release metadata')
 if not isinstance(meta['schema_version'],int) or not 7<=meta['schema_version']<=1000:raise ValueError('Invalid schema version')
 actual={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file() and p!=dest/'release.json'}
 if actual!=meta['files'] or 'backend.jar' not in actual or 'web/index.html' not in actual:raise ValueError('Artifact checksum mismatch')
 with zipfile.ZipFile(dest/'backend.jar') as jar:
  versions=[int(m[1]) for name in jar.namelist() if (m:=re.search(r'/db/migration/V(\d+)__.*\.sql$',name))]
  if not versions or max(versions)!=meta['schema_version'] or 'BOOT-INF/classes/com/matrix/prp/deployment/DatabaseTool.class' not in jar.namelist():raise ValueError('Migration metadata mismatch')
 return meta
def properties(values):
 def escape(v):return str(v).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r')
 return ''.join(k+'='+escape(v)+'\n' for k,v in values.items()).encode()
def config():return yaml.safe_load(CONFIG.read_text())
def migrate(release,db,baseline=False,baseline_only=False):
 runtime=release/'.migration-runtime'
 if not runtime.exists():
  runtime.mkdir()
  with zipfile.ZipFile(release/'backend.jar') as jar:
   for name in jar.namelist():
    if name.startswith('BOOT-INF/lib/') and name.endswith('.jar') or name.startswith('BOOT-INF/classes/db/migration/') and name.endswith('.sql') or name=='BOOT-INF/classes/com/matrix/prp/deployment/DatabaseTool.class':
     if '..' in Path(name).parts:raise ValueError('Unsafe JAR member')
     target=runtime/name
     target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(jar.read(name))
  for p in [runtime,*runtime.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
 cfg=config()['spring']['datasource']
 original=cfg['url']
 url=re.sub(r'(?<=/)[a-zA-Z0-9_]+(?=\?|$)',db,original,count=1)
 if '/'+db not in url:raise ValueError('Cannot select migration database')
 user=cfg['username']
 # Grant only this isolated verification schema to the existing app identity.
 if db!='matrix_prp':
  if not re.fullmatch(r'[a-zA-Z0-9_]+',user):raise ValueError('Invalid DB user')
  hosts=sql("SELECT host FROM mysql.user WHERE user='"+user+"';").splitlines()
  for host in hosts:
   if not re.fullmatch(r'[a-zA-Z0-9_.%:-]+',host):raise ValueError('Invalid DB user host')
   sql("GRANT ALL PRIVILEGES ON `"+db+"`.* TO '"+user+"'@'"+host+"';")
 values={'url':url,'user':user,'password':cfg['password'],'migrations':str(runtime/'BOOT-INF/classes/db/migration')}
 cp=str(runtime/'BOOT-INF/classes')+':'+str(runtime/'BOOT-INF/lib/*')
 actions=['baseline-v7'] if baseline_only else (['baseline-v7','migrate','validate'] if baseline else ['migrate','validate'])
 for action in actions:
  log('Database '+db+': '+action)
  run([JAVA,'-Xmx160m','-XX:MaxMetaspaceSize=128m','-cp',cp,'com.matrix.prp.deployment.DatabaseTool',action],input=properties(values),user=ACCOUNT.pw_uid,group=ACCOUNT.pw_gid,cwd=str(release))
def drop_test_db(db):
 sql('DROP DATABASE `'+db+'`;')
 user=config()['spring']['datasource']['username']
 # Remove stale per-schema grants as well as the temporary database.
 hosts=sql("SELECT Host FROM mysql.db WHERE User='"+user+"' AND Db='"+db+"';").splitlines()
 for host in hosts:sql("REVOKE ALL PRIVILEGES ON `"+db+"`.* FROM '"+user+"'@'"+host+"';")
def check_legacy(release,reference):
 migrations=release/'.migration-runtime/BOOT-INF/classes/db/migration'
 # Extract SQL only; we do not baseline or migrate the production schema here.
 with zipfile.ZipFile(release/'backend.jar') as jar:
  for name in jar.namelist():
   if re.search(r'/db/migration/V[1-7]__.*\.sql$',name):
    content=jar.read(name).decode()
    sql(content,reference)
 expected=set(sql('SHOW TABLES;',reference).splitlines())
 actual=set(sql('SHOW TABLES;').splitlines())
 assert expected==actual,'Legacy table set differs; explicit migration review required'
 for table in expected:
  def definition(db):
   return re.sub(r' AUTO_INCREMENT=\d+','',sql('SHOW CREATE TABLE `'+table+'`;',db).split('\t',1)[1])
  assert definition(reference)==definition('matrix_prp'),'Legacy schema mismatch: '+table
 log('Legacy V1-V7 schema definitions match exactly; explicit baseline is permitted')
def request(path,token=None,byte_range=None):
 headers={}
 if token:headers['Authorization']='Bearer '+token
 if byte_range:headers['Range']=byte_range
 with urllib.request.urlopen(urllib.request.Request('https://micor.top/prp'+path,headers=headers),timeout=15) as response:return response.status,response.read()
def token_for(username,user_id):
 secret=str(config()['matrix-prp']['security']['jwt-secret']).encode()
 enc=lambda value:base64.urlsafe_b64encode(value).decode().rstrip('=')
 algo='HS512' if len(secret)>=64 else 'HS384' if len(secret)>=48 else 'HS256'
 data=enc(json.dumps({'alg':algo}).encode())+'.'+enc(json.dumps({'sub':username,'uid':user_id,'iat':int(time.time()),'exp':int(time.time())+300}).encode())
 return data+'.'+enc(hmac.new(secret,data.encode(),getattr(hashlib,'sha'+algo[2:])).digest())
def check():
 for i in range(45):
  try:
   with urllib.request.urlopen('http://127.0.0.1:11000/api/health',timeout=3) as response:
    assert json.load(response)['code']=='SUCCESS'
   break
  except Exception:
   if i==44:raise
   time.sleep(2)
 for path in ['/','/learning','/notifications','/manifest.webmanifest','/sw.js']:
  status,body=request(path);assert status==200
 for row in sql('SELECT id,username FROM prp_users WHERE enabled=1 ORDER BY id LIMIT 10;').splitlines():
  user_id,username=row.split('\t');token=token_for(username,int(user_id))
  for path in ['/api/users/me','/api/dashboard/summary','/api/video/items','/api/wellness/foods/frequent','/api/practice/subjects','/api/practice/statistics']:
   status,body=request(path,token);assert status==200 and json.loads(body)['code']=='SUCCESS',path
 videos=sql('SELECT id,user_id,storage_key,size_bytes FROM prp_video_assets ORDER BY id;').splitlines()
 for row in videos:
  video,user,key,size=row.split('\t');assert (Path('/srv/matrix-prp/video/media')/user/(key+'.mp4')).stat().st_size==int(size)
 if videos:
  video,user,_,_=videos[0].split('\t');username=sql('SELECT username FROM prp_users WHERE id='+user+';')
  status,body=request('/api/video/items/'+video+'/playback',token_for(username,int(user)))
  url=json.loads(body)['data']['url'];status,body=request(url,byte_range='bytes=0-1023');assert status==206 and len(body)==1024
 log('Health, authenticated APIs, PWA and '+str(len(videos))+' private video files verified')
def point(release):
 temp=BASE/'.current-next'
 if temp.exists() or temp.is_symlink():temp.unlink()
 temp.symlink_to(release.name);os.replace(temp,BASE/'current')
def status():
 current=(BASE/'current').resolve()
 log(json.dumps({'release':current.name,'schema_version':schema_version(),'metadata':json.loads((current/'release.json').read_text()) if (current/'release.json').exists() else {},'service':subprocess.check_output(['systemctl','is-active',SERVICE]).decode().strip()}))
def deploy(allow_baseline=False):
 incoming=STATE/('incoming-'+str(int(time.time()))+'.tar.gz')
 total=0
 try:
  with incoming.open('wb') as out:
   while block:=sys.stdin.buffer.read(1024*1024):
    total+=len(block)
    if total>256*1024*1024:raise ValueError('Upload too large')
    out.write(block)
  with tempfile.TemporaryDirectory(dir=BASE,prefix='.staging-') as tmp:
   staging=Path(tmp);meta=unpack(incoming,staging)
   release=BASE/meta['id']
   previous=(BASE/'current').resolve()
   old=json.loads((previous/'release.json').read_text())
   if old.get('commit')==meta['commit']:
    log('This commit is already deployed');check();return
   if release.exists():raise ValueError('Release ID already exists')
   os.rename(staging,release)
  for p in [release,*release.rglob('*')]:
   os.chown(p,0,ACCOUNT.pw_gid);p.chmod(0o755 if p.is_dir() else 0o644)
  (release/'backend.jar').chmod(0o640)
  backend_changed=old.get('backend_source')!=meta['backend_source']
  db_before=schema_version()
  structure_before=schema_fingerprint()
  if meta['schema_version']<db_before:raise ValueError('Artifact is older than database; use reviewed rollback')
  backup=BACKUPS/meta['id'];backup.mkdir(mode=0o700)
  shutil.copytree('/etc/matrix-prp',backup/'config')
  shutil.copy2('/etc/nginx/snippets/matrix-prp.conf',backup/'nginx.conf')
  (backup/'previous.json').write_text(json.dumps({'release':previous.name,'schema_version':db_before}))
  # Only frontend changed: keep the tested running backend artifact and skip restart/migration.
  if not backend_changed:
   assert meta['schema_version']==db_before
   shutil.copy2(previous/'backend.jar',release/'backend.jar')
   meta['files']['backend.jar']=hashlib.sha256((release/'backend.jar').read_bytes()).hexdigest()
   (release/'release.json').write_text(json.dumps(meta,indent=2))
   point(release)
   try:check()
   except Exception:point(previous);raise
   log('Frontend published; backend restart and database migration skipped');return
  stopped=False;switched=False;success=False
  try:
   run(['systemctl','stop',SERVICE]);stopped=True
   dump(backup/'database.sql')
   before=snapshot();(backup/'snapshot.json').write_text(json.dumps(before))
   db='prp_verify_'+str(int(time.time()))
   sql('CREATE DATABASE `'+db+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
   try:
    restore(backup/'database.sql',db);assert_preserved(before,snapshot(db))
    no_history=not sql("SHOW TABLES LIKE 'flyway_schema_history';")
    if no_history:
     if not allow_baseline:raise ValueError('Legacy baseline must be performed once by the administrator')
     ref=db+'_ref';sql('CREATE DATABASE `'+ref+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
     try:check_legacy(release,ref)
     finally:sql('DROP DATABASE `'+ref+'`;')
    migrate(release,db,baseline=no_history)
    assert_preserved(before,snapshot(db))
    log('Actual backup restoration and pending migrations verified')
   finally:drop_test_db(db)
   migrate(release,'matrix_prp',baseline=no_history)
   assert_preserved(before,snapshot())
   assert schema_version()==meta['schema_version']
   point(release);switched=True
   run(['systemctl','start',SERVICE]);stopped=False
   check();success=True
   (backup/'result.json').write_text(json.dumps({'status':'success','commit':meta['commit'],'schema_version':schema_version(),'time':int(time.time())}))
   log('Deployment complete: '+meta['id'])
  finally:
   if not success:
    (backup/'result.json').write_text(json.dumps({'status':'failed','schema_version':schema_version(),'switched':switched}))
    if schema_version()==db_before and schema_fingerprint()==structure_before:
     point(previous)
     if stopped or switched:run(['systemctl','restart',SERVICE])
     log('Previous application restored; database was not restored')
    else:
     run(['systemctl','stop',SERVICE])
     log('Database advanced: automatic rollback blocked; application/database require operator review')
 finally:
  if incoming.exists():incoming.unlink()
def rollback(release_id):
 if not valid_release_id(release_id):raise ValueError('Invalid release ID')
 release=BASE/release_id
 if not release.is_dir() or release.is_symlink():raise ValueError('Unknown release')
 meta=json.loads((release/'release.json').read_text())
 if meta['schema_version']!=schema_version():raise ValueError('Cross-schema rollback requires operator review; never restore an old DB automatically')
 previous=(BASE/'current').resolve()
 run(['systemctl','stop',SERVICE]);point(release);run(['systemctl','start',SERVICE])
 try:check()
 except Exception:
  point(previous);run(['systemctl','restart',SERVICE]);raise
 log('Application rollback complete: '+release_id+'; current database and videos retained')
def baseline_only():
 # A one-time administrator operation, deliberately unavailable through SSH gateway.
 if sql("SHOW TABLES LIKE 'flyway_schema_history';"):raise ValueError('Flyway history already exists')
 archive=STATE/'baseline-artifact.tar.gz'
 with archive.open('wb') as out:
  total=0
  while block:=sys.stdin.buffer.read(1024*1024):
   total+=len(block)
   if total>256*1024*1024:raise ValueError('Upload too large')
   out.write(block)
 backup=BACKUPS/('baseline-v7-'+str(int(time.time())));backup.mkdir(mode=0o700)
 stopped=False
 try:
  with tempfile.TemporaryDirectory(dir=BASE,prefix='.baseline-') as tmp:
   release=Path(tmp);unpack(archive,release)
   release.chmod(0o755)
   for p in release.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
   run(['systemctl','stop',SERVICE]);stopped=True
   dump(backup/'database.sql');before=snapshot()
   db='prp_baseline_'+str(int(time.time()));ref=db+'_ref'
   sql('CREATE DATABASE `'+db+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
   sql('CREATE DATABASE `'+ref+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
   try:
    restore(backup/'database.sql',db);assert_preserved(before,snapshot(db))
    check_legacy(release,ref)
    migrate(release,db,baseline_only=True);assert_preserved(before,snapshot(db))
    migrate(release,'matrix_prp',baseline_only=True);assert_preserved(before,snapshot())
    assert schema_version()==7
    (backup/'result.json').write_text(json.dumps({'baseline':7,'data':'unchanged','restoration':'verified'}))
   finally:
    drop_test_db(db);sql('DROP DATABASE `'+ref+'`;')
  log('Explicit V7 baseline registered; no V1-V7 SQL replayed and no new migrations applied')
 finally:
  if stopped:run(['systemctl','start',SERVICE])
  if archive.exists():archive.unlink()
def main():
 if os.geteuid()!=0:raise SystemExit('Must run through the deployment gateway')
 if ACCOUNT is None:raise SystemExit('Runtime account openclaw is missing')
 STATE.mkdir(mode=0o700,exist_ok=True);BASE.mkdir(mode=0o755,parents=True,exist_ok=True);BACKUPS.mkdir(mode=0o700,exist_ok=True)
 with (STATE/'deploy.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  action=sys.argv[1] if len(sys.argv)>1 else ''
  if action=='deploy' and len(sys.argv)==2:deploy()
  elif action=='bootstrap-v7' and len(sys.argv)==2:baseline_only()
  elif action=='rollback' and len(sys.argv)==3:rollback(sys.argv[2])
  elif action=='status' and len(sys.argv)==2:status()
  elif action=='check' and len(sys.argv)==2:check()
  else:raise ValueError('Invalid deployment action')
if __name__=='__main__':
 try:main()
 except Exception as exc:
  # Exceptions from DB drivers can contain connection strings. Full details stay root-only.
  STATE.mkdir(mode=0o700,exist_ok=True)
  import traceback
  with (STATE/'last-error.log').open('w') as out:traceback.print_exc(file=out)
  log('Deployment failed: '+type(exc).__name__+'. Administrator details: /var/lib/matrix-prp-deploy/last-error.log')
  sys.exit(1)
