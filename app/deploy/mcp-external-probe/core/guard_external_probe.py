"""Fresh Windows/external observation worker; no ready/passed decisions.

Only approved fixed targets, credential-free bounded requests, TLS verification,
and fixed DNS resolvers. Invoke only a phase authorized by the coordinator.
"""
import datetime,hashlib,http.client,io,json,pathlib,socket,ssl,subprocess,time
from guard_release_engine import GateError,digest,sha,sign,utc
HOSTS={'micor.top','www.micor.top','prp-test.micor.top','auth-test.micor.top'}
IPS={'207.57.123.94','2001:df1:7880:6::63','127.0.0.1','::1'}
def exception_detail(stage,error):
 allowed={'OSError','ConnectionRefusedError','ConnectionResetError','ConnectionAbortedError','PermissionError','TimeoutError','SSLError','SSLCertVerificationError','RemoteDisconnected','BadStatusLine','IncompleteRead','GateError','ValueError'}
 return {'stage':stage,'exception_type':type(error).__name__ if type(error).__name__ in allowed else 'OTHER_EXCEPTION_TYPE','errno':getattr(error,'errno',None) if isinstance(getattr(error,'errno',None),int) else None,'winerror':getattr(error,'winerror',None) if isinstance(getattr(error,'winerror',None),int) else None}
class Reader(io.RawIOBase):
 def __init__(self,raw,owner):self.raw=raw;self.owner=owner
 def readable(self):return True
 def readinto(self,b):
  self.owner.budget();n=self.raw.readinto(b)
  if n and self.owner.first is None:self.owner.first=time.monotonic()-self.owner.start
  return n
 def close(self):self.raw.close();super().close()
class TimedSocket:
 def __init__(self,s,start,deadline):self.s=s;self.start=start;self.deadline=deadline;self.first=None
 def budget(self):
  left=self.deadline-time.monotonic()
  if left<=0:raise TimeoutError()
  self.s.settimeout(left)
 def makefile(self,*a,**k):return io.BufferedReader(Reader(self.s.makefile('rb',buffering=0),self))

def http_probe(spec,isolated=False):
 c=spec['case'];ip=spec['target'];plain=c.get('plain',False);port=c.get('port',80 if plain else 443)
 if ip not in IPS or (not isolated and (ip in ('127.0.0.1','::1') or port not in (80,443))) or (isolated and ip not in ('127.0.0.1','::1')):raise GateError('UNAPPROVED_DESTINATION')
 started=utc();t=time.monotonic();deadline=t+10;stage='TCP';s=None;tls=None;ts=None;response=None;times={'tcp':None,'tls':None,'request_sent':None,'headers_complete':None,'first_byte':None,'total':None}
 r=dict(case=c,target=ip,started_utc=started,status=None,error=None,chain_verified=plain,san_verified=plain)
 try:
  s=socket.create_connection((ip,port),8);times['tcp']=time.monotonic()-t
  if not plain:
   stage='TLS';ctx=ssl.create_default_context();sni=c.get('sni');ctx.check_hostname=sni in HOSTS;ctx.set_alpn_protocols(['http/1.1']);s.settimeout(max(.001,deadline-time.monotonic()));s=ctx.wrap_socket(s,server_hostname=sni);times['tls']=time.monotonic()-t
   r.update(chain_verified=True,san_verified=ctx.check_hostname,alpn=s.selected_alpn_protocol())
  stage='REQUEST';body=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' if c.get('method')=='POST' else b''
  lines=[c.get('method','GET')+' '+c['path']+' '+c.get('http_version','HTTP/1.1')]
  if c.get('host') is not None:lines.append('Host: '+c['host'])
  lines+=c.get('extra',[])
  if body:lines+=['Content-Type: application/json','Content-Length: '+str(len(body))]
  lines+=['Connection: close'];s.settimeout(max(.001,deadline-time.monotonic()));s.sendall(('\r\n'.join(lines)+'\r\n\r\n').encode()+body)
  times['request_sent']=time.monotonic()-t;stage='FIRST_BYTE'
  ts=TimedSocket(s,t,deadline);response=http.client.HTTPResponse(ts,method=c.get('method','GET'));response.begin();times['headers_complete']=time.monotonic()-t;stage='BODY';r['status']=response.status
  chunks=[];size=0
  while True:
   ts.budget();b=response.read1(min(65536,262145-size))
   if not b:break
   chunks.append(b);size+=len(b)
   if size>262144:raise GateError('OUTPUT_LIMIT')
  b=b''.join(chunks);times['first_byte']=ts.first
  semantic={}
  try:
   data=json.loads(b)
   r['json_canonical_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
   if 'keys' in data:semantic['jwks_nonempty']=bool(data['keys'])
   if isinstance(data.get('data'),dict) and 'status' in data['data']:semantic['health']=data['data']['status'] if data['data']['status'] in ('UP','DOWN','UNKNOWN') else 'UNEXPECTED_VALUE'
  except (ValueError,TypeError):pass
  challenge=response.getheader('WWW-Authenticate');location=response.getheader('Location')
  # Never persist an unexpected authorization URL, state, code or reflected
  # bearer value. Exact reviewed values remain available for gate comparison;
  # mismatches are represented by None + a digest, and fail the contract.
  safe_challenge=challenge if challenge is not None and challenge==spec.get('www_authenticate') else None
  safe_location=location if location is not None and location==spec.get('location') else None
  r.update(body_sha256=hashlib.sha256(b).hexdigest(),body_bytes=size,www_authenticate=safe_challenge,location=safe_location,unexpected_challenge_sha256=hashlib.sha256(challenge.encode()).hexdigest() if challenge and not safe_challenge else None,unexpected_location_sha256=hashlib.sha256(location.encode()).hexdigest() if location and not safe_location else None,protocol='1.1' if response.version==11 else '1.0',semantic=semantic)
 except (TimeoutError,socket.timeout) as e:
  if stage=='FIRST_BYTE' and ts is not None and ts.first is not None:stage='HEADERS'
  r['error']={'TCP':'TCP_CONNECT_TIMEOUT','TLS':'TLS_OR_CERT_VALIDATION_TIMEOUT','REQUEST':'REQUEST_OR_FIRST_BYTE_TIMEOUT','FIRST_BYTE':'REQUEST_OR_FIRST_BYTE_TIMEOUT','HEADERS':'RESPONSE_HEADERS_TIMEOUT','BODY':'RESPONSE_COMPLETION_TIMEOUT'}[stage];r['error_detail']=exception_detail(stage,e)
 except ssl.SSLCertVerificationError as e:r['error']='CERTIFICATE_FAILED';r['error_detail']=exception_detail(stage,e)
 except ssl.SSLError as e:r['error']='TLS_FAILED';r['error_detail']=exception_detail(stage,e)
 except Exception as e:r['error']='OUTPUT_LIMIT' if isinstance(e,GateError) and str(e)=='OUTPUT_LIMIT' else 'TRANSPORT_OR_PROTOCOL_ERROR';r['error_detail']=exception_detail(stage,e)
 finally:
  if ts is not None:times['first_byte']=ts.first
  if response is not None:response.close()
  if s is not None:s.close()
  r.update(ended_utc=utc(),timings={**times,'total':time.monotonic()-t})
 return r

def tls_probe(spec,isolated=False):
 c=spec['case'];ip=spec['target'];port=c.get('port',443)
 if ip not in IPS or c['sni'] not in HOSTS or (not isolated and (ip in ('127.0.0.1','::1') or port!=443)):raise GateError('UNAPPROVED_TLS_DESTINATION')
 start=utc();t=time.monotonic();stage='TCP';r=dict(case=c,target=ip,status=None,error=None,started_utc=start)
 try:
  ctx=ssl.create_default_context();ctx.set_alpn_protocols(['h2','http/1.1'])
  with socket.create_connection((ip,port),8) as s:
   tcp=time.monotonic()-t;stage='TLS';s.settimeout(max(.001,10-tcp))
   with ctx.wrap_socket(s,server_hostname=c['sni']) as tls:r.update(chain_verified=True,san_verified=True,alpn=tls.selected_alpn_protocol(),protocol='TLS',status=0)
  r['timings']={'tcp':tcp,'tls':time.monotonic()-t,'first_byte':None,'total':time.monotonic()-t}
 except Exception as e:r.update(error='CERTIFICATE_FAILED' if isinstance(e,ssl.SSLCertVerificationError) else 'TLS_PROBE_FAILED',error_detail=exception_detail(stage,e),timings={'total':time.monotonic()-t})
 r['ended_utc']=utc();return r

def dns_windows(domains,sources):
 from windows_dns_worker import dns_windows as bounded_dns
 return bounded_dns(domains,sources)

def collect(job,manifest,pin,key,dns=dns_windows,isolated=False,experimental_concurrency=1):
 if experimental_concurrency not in (1,2):raise GateError('CONCURRENCY_LIMIT')
 if experimental_concurrency!=1 and not isolated:raise GateError('EXPERIMENT_REQUIRES_ISOLATION')
 production_concurrency=manifest.get('production_external_concurrency',1)
 if type(production_concurrency) is not int or production_concurrency not in (1,2):raise GateError('PRODUCTION_CONCURRENCY_LIMIT')
 concurrency=experimental_concurrency if isolated else production_concurrency
 if concurrency==2 and 'guard_experimental_scheduler.py' not in manifest['worker_sources']:raise GateError('SCHEDULER_SOURCE_NOT_BOUND')
 if digest(manifest)!=pin or job['manifest_sha256']!=pin:raise GateError('WORKER_MANIFEST_DRIFT')
 source={n:sha(pathlib.Path(__file__).parent/n) for n in manifest['worker_sources']}
 if source!=manifest['worker_sources'] or digest(source)!=job['probe_sha256']:raise GateError('WORKER_SOURCE_DRIFT')
 start=utc();rows=[];profile=manifest['phases'][job['phase']]
 if profile['config']!=job['source_config']:raise GateError('WORKER_PHASE_SOURCE_MISMATCH')
 def run_probe(spec):
  if spec.get('probe')=='tls':r=tls_probe(spec,isolated)
  elif spec.get('probe')=='h2':r=h2_probe(spec,isolated)
  else:r=http_probe(spec,isolated)
  return r
 if concurrency==2:
  from guard_experimental_scheduler import schedule
  remaining=epoch_deadline(job)-time.time()
  if remaining<=0:raise GateError('COLLECTOR_DEADLINE')
  rows=schedule(profile['requests'],run_probe,time.monotonic()+remaining,concurrency=2)
 else:
  for ident,spec in profile['requests'].items():
   if time.time()>epoch_deadline(job):raise GateError('COLLECTOR_DEADLINE')
   r=run_probe(spec);r['request_id']=ident;rows.append(r);time.sleep(.18)
 if time.time()>epoch_deadline(job):raise GateError('COLLECTOR_DEADLINE')
 answers=dns(manifest['domains'],manifest['dns_sources'])
 if time.time()>epoch_deadline(job):raise GateError('COLLECTOR_DEADLINE')
 payload={k:job[k] for k in ['deployment_id','phase','nonce','manifest_sha256','source_config','target','probe_sha256']}
 payload.update(started_utc=start,ended_utc=utc(),observations=rows,dns=answers)
 return sign(payload,key)
def epoch_deadline(job):return datetime.datetime.fromisoformat(job['issued_utc']).timestamp()+job['max_seconds']

def h2_probe(spec,isolated=False):
 c=spec['case'];ip=spec['target'];start=utc();t=time.monotonic()
 if ip not in IPS or (not isolated and ip in ('127.0.0.1','::1')):raise GateError('H2_DESTINATION')
 q=dict(ip=ip,port=c.get('port',443),sni=c['sni'],authority=c['authority'],host=c.get('host'),path=c.get('path','/prp/api/health'))
 try:p=subprocess.run(['node',str(pathlib.Path(__file__).with_name('guard_external_h2.js'))],input=json.dumps(q).encode(),capture_output=True,timeout=13)
 except (subprocess.TimeoutExpired,OSError) as e:
  return dict(case=c,target=ip,started_utc=start,ended_utc=utc(),status=None,error='H2_WORKER_FAILED',error_detail=exception_detail('H2_SUBPROCESS',e),worker_returncode=None,worker_stderr_bytes=len(getattr(e,'stderr',None) or b''),timings={'total':time.monotonic()-t})
 if p.returncode or len(p.stdout)>16384:r={'error':'H2_WORKER_FAILED'}
 else:
  try:r=json.loads(p.stdout)
  except Exception:r={'error':'H2_OUTPUT_CORRUPT'}
 r.update(case=c,target=ip,started_utc=start,ended_utc=utc(),timings={'total':time.monotonic()-t},worker_returncode=p.returncode,worker_stderr_bytes=len(p.stderr));return r
