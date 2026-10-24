"""Fixed 32-query DNS worker, 45s budget, owned Windows process-tree cleanup."""
import base64,ctypes,datetime,json,os,subprocess,time
from ctypes import wintypes
from guard_release_engine import GateError,epoch,utc
HOSTS={'micor.top','www.micor.top','prp-test.micor.top','auth-test.micor.top'}
SOURCES={'dns25.hichina.com','dns26.hichina.com','1.1.1.1','8.8.8.8'}
LAST_TRACE=None
class DNSFailure(GateError):
 def __init__(self,name,report):super().__init__(name);self.report=report

class ProcessTree:
 """Windows Job handle owns only the new child; close kills descendants."""
 def __init__(self):
  if os.name!='nt':raise GateError('WINDOWS_DNS_WORKER_REQUIRED')
  class IO(ctypes.Structure):_fields_=[(n,ctypes.c_ulonglong) for n in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
  class BASIC(ctypes.Structure):_fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),('LimitFlags',wintypes.DWORD),('MinWorking',ctypes.c_size_t),('MaxWorking',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
  class EXT(ctypes.Structure):_fields_=[('Basic',BASIC),('Io',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]
  self.k=ctypes.WinDLL('kernel32',use_last_error=True)
  self.k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];self.k.CreateJobObjectW.restype=wintypes.HANDLE
  self.k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];self.k.SetInformationJobObject.restype=wintypes.BOOL
  self.k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];self.k.AssignProcessToJobObject.restype=wintypes.BOOL
  self.k.CloseHandle.argtypes=[wintypes.HANDLE];self.k.CloseHandle.restype=wintypes.BOOL
  self.handle=self.k.CreateJobObjectW(None,None)
  if not self.handle:raise GateError('DNS_JOB_CREATE_FAILED')
  info=EXT();info.Basic.LimitFlags=0x2000
  if not self.k.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
   self.close();raise GateError('DNS_JOB_LIMIT_FAILED')
 def assign(self,p):
  if not self.k.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(p._handle))):raise GateError('DNS_JOB_ASSIGN_FAILED')
 def close(self):
  if getattr(self,'handle',None):self.k.CloseHandle(self.handle);self.handle=None

def run_powershell(script,timeout=45):
 started=time.monotonic();r={'started_utc':utc(),'budget_seconds':timeout,'events':[],'total_deadline_triggered':False,'process_tree_cleanup':False}
 tree=ProcessTree();p=None
 try:
  encoded=base64.b64encode(script.encode('utf-16-le')).decode()
  p=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
  r['process_created_ms']=(time.monotonic()-started)*1000;r['process_created_utc']=utc();tree.assign(p);r['job_assigned']=True
  r['pipe_communication_started_ms']=(time.monotonic()-started)*1000;r['pipe_communication_started_utc']=utc()
  try:out,err=p.communicate(timeout=max(.001,timeout-(time.monotonic()-started)))
  except subprocess.TimeoutExpired:
   r['total_deadline_triggered']=True;tree.close();r['process_tree_cleanup']=True
   out,err=p.communicate(timeout=5)
  r.update(exit_code=p.returncode,stdout_bytes=len(out),stderr_bytes=len(err),read_completed_ms=(time.monotonic()-started)*1000,pipe_communication_completed_utc=utc(),process_exit_observed_utc=utc())
  if len(out)>131072:raise DNSFailure('DNS_OUTPUT_LIMIT',r)
  try:r['events']=[json.loads(x) for x in out.decode('utf-8-sig').splitlines() if x.strip()]
  except Exception:raise DNSFailure('DNS_OUTPUT_FORMAT',r)
  r['ended_utc']=utc();r['total_ms']=(time.monotonic()-started)*1000
  if r['total_deadline_triggered']:raise DNSFailure('DNS_PROCESS_DEADLINE',r)
  if p.returncode or err:raise DNSFailure('DNS_PROCESS_FAILED',r)
  return r
 finally:
  tree.close()
  if p and p.poll() is None:
   p.kill();p.communicate(timeout=5)

def script_for(domains,sources):
 if set(domains)!=HOSTS or len(domains)!=4 or set(sources)!=SOURCES or len(sources)!=4:raise GateError('DNS_SOURCE_NOT_APPROVED')
 script=r'''$ProgressPreference='SilentlyContinue'
$watch=[Diagnostics.Stopwatch]::StartNew()
function Emit($v){$v.utc=[DateTime]::UtcNow.ToString('o');$v.elapsed_ms=$watch.Elapsed.TotalMilliseconds;[Console]::Out.WriteLine(($v|ConvertTo-Json -Compress -Depth 5));[Console]::Out.Flush()}
Emit @{event='INITIALIZED'}
foreach($s in SOURCES){foreach($h in DOMAINS){foreach($t in 'A','AAAA'){
 Emit @{event='QUERY_START';source=$s;host=$h;type=$t}
 $q=[Diagnostics.Stopwatch]::StartNew();$ok=$true;$class=$null;$values=@()
 try{$a=Resolve-DnsName $h -Type $t -Server $s -DnsOnly -ErrorAction Stop;$values=@($a|Where-Object {$_.Type -eq $t}|ForEach-Object IPAddress)}catch{$ok=$false;$class='DNS_QUERY_EXCEPTION'}
 Emit @{event='QUERY_END';source=$s;host=$h;type=$t;query_ok=$ok;values=$values;duration_ms=$q.Elapsed.TotalMilliseconds;error_class=$class}
}}}
Emit @{event='SCRIPT_COMPLETE'}'''
 return script.replace('SOURCES',','.join("'"+s+"'" for s in sources)).replace('DOMAINS',','.join("'"+s+"'" for s in domains))

def rows_from_trace(trace,domains,sources,now=None):
 now=time.time() if now is None else now
 expected={(h,s,t) for h in domains for s in sources for t in ['A','AAAA']};start={};end={}
 for e in trace['events']:
  if e.get('event') not in ('QUERY_START','QUERY_END'):continue
  key=(e.get('host'),e.get('source'),e.get('type'));target=start if e['event']=='QUERY_START' else end
  if key not in expected or key in target:raise DNSFailure('DNS_MISSING_DUPLICATE_OR_SOURCE',trace)
  target[key]=e
 if set(start)!=expected or set(end)!=expected:raise DNSFailure('DNS_MISSING_DUPLICATE_OR_SOURCE',trace)
 if sum(e.get('event')=='INITIALIZED' for e in trace['events'])!=1 or sum(e.get('event')=='SCRIPT_COMPLETE' for e in trace['events'])!=1:raise DNSFailure('DNS_SCRIPT_INCOMPLETE',trace)
 rows=[]
 for s in sources:
  for h in domains:
   queries=[]
   for t in ['A','AAAA']:
    key=(h,s,t);a=start[key];b=end[key]
    if not epoch(trace['started_utc'])<=epoch(a['utc'])<=epoch(b['utc'])<=epoch(trace['ended_utc']) or not 0<=now-epoch(b['utc'])<=300:raise DNSFailure('DNS_QUERY_TIME_OR_STALE',trace)
    if b.get('query_ok') is not True or not isinstance(b.get('values'),list):raise DNSFailure('DNS_QUERY_FAILED',trace)
    queries.append({'type':t,'started_utc':a['utc'],'ended_utc':b['utc'],'duration_ms':b['duration_ms'],'values':b['values'],'query_ok':True})
   if queries[0]['values']!=['207.57.123.94'] or queries[1]['values']!=[]:raise DNSFailure('DNS_WRONG_A_OR_AAAA_REVIEW_REQUIRED',trace)
   rows.append({'host':h,'source':s,'utc':queries[0]['started_utc'],'query_ok':True,'a':queries[0]['values'],'aaaa':queries[1]['values'],'queries':queries})
 return rows

def dns_windows(domains,sources):
 global LAST_TRACE
 try:
  LAST_TRACE=run_powershell(script_for(domains,sources),45)
  return rows_from_trace(LAST_TRACE,domains,sources)
 except DNSFailure as e:LAST_TRACE=e.report;raise
