#!/usr/bin/env python3
"""Export tested IMAGE layers only. Never export/commit runtime containers or volumes."""
import datetime,gzip,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parent

def run(args,timeout=30):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if p.returncode:raise RuntimeError('IMAGE_EXPORT_COMMAND_FAILED')
 return p.stdout

def main():
 if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_OS')!='Linux' or not os.environ.get('RUNNER_TEMP'):raise RuntimeError('DISPOSABLE_EXPORT_ONLY')
 result=json.loads((ROOT/'auth-candidate-result.safe.json').read_text())
 if (result.get('failed')!=0 or result.get('passed',0)<181 or len(result.get('checks',[]))!=result.get('passed')
     or result.get('combined_health_backend',{}).get('scope')!='REAL_KEYCLOAK_PRP_MYSQL_COMBINED'
     or result.get('official_jvm_jwks_fetch_verified') is not True
     or not all(x.get('passed') is True for x in result['checks'])):raise RuntimeError('COMBINED_ACCEPTANCE_REQUIRED')
 refs={'auth':'prp-health-auth-candidate:ci','egress':'prp-health-egress-candidate:ci','postgres':'postgres:17.6-alpine'}
 expected={'auth':result['image_id'],'egress':result['egress_image_id'],'postgres':result['postgres_image_id']}
 forbidden={'KC_BOOTSTRAP_ADMIN_PASSWORD','KC_DB_PASSWORD','POSTGRES_PASSWORD','PRP_HEALTH_DB_PASSWORD','MYSQL_ROOT_PASSWORD','MATRIX_PRP_JWT_SECRET'}
 images={}
 for name,ref in refs.items():
  image=json.loads(run(['docker','image','inspect',ref]))[0]
  if image['Id']!=expected[name]:raise RuntimeError('TESTED_IMAGE_DRIFT')
  if any(v.split('=',1)[0] in forbidden for v in image['Config'].get('Env',[])):raise RuntimeError('RUNTIME_SECRET_IN_IMAGE_CONFIG')
  images[name]={'tag':ref,'image_id':image['Id'],'layers':image['RootFS']['Layers']}
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 source=event.get('pull_request',{}).get('head',{}).get('sha',os.environ['GITHUB_SHA'])
 raw=ROOT/'tested-auth-images.tar';archive=ROOT/'tested-auth-images.tar.gz'
 try:
  with raw.open('xb') as f:
   p=subprocess.run(['docker','image','save',*refs.values()],stdout=f,stderr=subprocess.PIPE,timeout=180)
   if p.returncode:raise RuntimeError('IMAGE_ARCHIVE_EXPORT_FAILED')
  with raw.open('rb') as src,archive.open('xb') as dest,gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0,compresslevel=6) as gz:
   shutil.copyfileobj(src,gz,1024*1024)
 finally:
  if raw.exists():raw.unlink()
 with archive.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 manifest={'source_head_sha':source,'checkout_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
  'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive':archive.name,'archive_sha256':digest,'archive_bytes':archive.stat().st_size,
  'images':images,'keycloak_base_digest':result['keycloak_base_digest'],'python_base_digest':result['python_base_digest'],
  'postgres_digest':result['postgres_image_digest'],'postgres_uid_gid':result['postgres_uid_gid'],'provider_jar_sha256':result['policy_jar_sha256'],
  'auth_checks_passed':result['passed'],'auth_checks_failed':result['failed'],'runtime_containers_exported':False,'database_data_exported':False,
  'fixture_ca_or_private_keys_exported':False,'real_chatgpt_verified':False,'production_changed':False}
 (ROOT/'tested-auth-images.manifest.safe.json').write_text(json.dumps(manifest,indent=2))
 print('TESTED_IMAGE_LAYERS_EXPORTED_NO_RUNTIME_DATA',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  safe=str(e)
  if len(safe)>90 or not safe.replace('_','').isalnum():safe=type(e).__name__
  print('FAIL_IMAGE_EXPORT '+safe,flush=True);raise SystemExit(1) from None
