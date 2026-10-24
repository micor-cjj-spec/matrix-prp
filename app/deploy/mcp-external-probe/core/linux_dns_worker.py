"""Review-only Linux DNS adapter preserving the existing 32-query contract.

No shell, no resolver changes, no retries. Raw DNS stdout/stderr is not exported.
Only owned process groups may be killed. Not installed in a production manifest.
"""
import concurrent.futures
import ipaddress
import os
import re
import signal
import subprocess
import sys
import threading
import time
from guard_release_engine import GateError, utc
from windows_dns_worker import HOSTS, SOURCES, DNSFailure, rows_from_trace

AUTHORITIES={'dns25.hichina.com','dns26.hichina.com'}
LAST_TRACE=None

def validate(domains,sources):
    if len(domains)!=4 or set(domains)!=HOSTS or len(sources)!=4 or set(sources)!=SOURCES:
        raise GateError('DNS_SOURCE_NOT_APPROVED')

def command(host,source,kind):
    if host not in HOSTS or source not in SOURCES or kind not in {'A','AAAA'}:
        raise GateError('DNS_QUERY_NOT_APPROVED')
    return ['dig','@'+source,host,kind,'+time=2','+tries=1','+noall','+nocmd',
            '+comments','+question','+answer','+authority','+stats',
            '+norecurse' if source in AUTHORITIES else '+recurse']

def parse(output,host,source,kind):
    command(host,source,kind)
    if len(output)>32768:raise GateError('DNS_OUTPUT_LIMIT')
    try:text=output.decode('ascii')
    except UnicodeDecodeError:raise GateError('DNS_OUTPUT_FORMAT')
    headers=re.findall(r'^;; ->>HEADER<<- opcode: QUERY, status: ([A-Z]+), id: \d+\s*$',text,re.M)
    if headers!=['NOERROR']:raise GateError('DNS_RCODE_NOT_NOERROR')
    flag_rows=re.findall(r'^;; flags: ([^;]+);',text,re.M)
    if len(flag_rows)!=1:raise GateError('DNS_FLAGS_MISSING')
    flags=set(flag_rows[0].split())
    if 'qr' not in flags or 'tc' in flags or source in AUTHORITIES and 'aa' not in flags:
        raise GateError('DNS_RESPONSE_FLAGS_INVALID')
    questions=re.findall(r'^;([^;\s]+)\s+IN\s+(A|AAAA)\s*$',text,re.M)
    if questions!=[(host+'.',kind)]:raise GateError('DNS_QUESTION_MISMATCH')
    servers=re.findall(r'^;; SERVER: ([^#\s]+)#53\(',text,re.M)
    if len(servers)!=1:raise GateError('DNS_SERVER_MISSING')
    try:address=ipaddress.ip_address(servers[0])
    except ValueError:raise GateError('DNS_SERVER_ADDRESS_INVALID')
    if not address.is_global or address.is_multicast:raise GateError('DNS_SERVER_ADDRESS_INVALID')
    if source not in AUTHORITIES and str(address)!=source:raise GateError('DNS_SERVER_MISMATCH')
    if ';; WARNING:' in text:raise GateError('DNS_WARNING_REQUIRES_REVIEW')
    values=[];answer=False
    for line in text.splitlines():
        if line.startswith(';; '):
            if line.endswith('SECTION:'):answer=line==';; ANSWER SECTION:'
            continue
        if not answer or not line.strip() or line.startswith(';'):continue
        parts=line.split()
        if len(parts)!=5 or parts[0]!=host+'.' or not parts[1].isdigit() or parts[2:4]!=['IN',kind]:
            raise GateError('DNS_UNREVIEWED_ANSWER')
        try:value=ipaddress.ip_address(parts[4])
        except ValueError:raise GateError('DNS_ANSWER_ADDRESS_INVALID')
        if value.version!=(4 if kind=='A' else 6):raise GateError('DNS_ANSWER_FAMILY_INVALID')
        values.append(str(value))
    if len(set(values))!=len(values):raise GateError('DNS_DUPLICATE_ANSWER')
    return values

def execute(args,timeout):
    if not sys.platform.startswith('linux'):raise GateError('LINUX_DNS_WORKER_REQUIRED')
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        try:out,err=p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
            p.communicate(timeout=1)
            raise GateError('DNS_QUERY_TIMEOUT')
        if p.returncode or err:raise GateError('DNS_PROCESS_FAILED')
        return out
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGKILL);p.communicate(timeout=1)

def dns_linux(domains,sources):
    global LAST_TRACE
    validate(domains,sources)
    started=time.monotonic();deadline=started+45;lock=threading.Lock()
    trace={'started_utc':utc(),'budget_seconds':45,'events':[{'event':'INITIALIZED'}]}
    LAST_TRACE=trace
    def query(host,source,kind):
        first=time.monotonic()
        with lock:trace['events'].append({'event':'QUERY_START','host':host,'source':source,'type':kind,'utc':utc()})
        values=[];ok=False;error=None
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise GateError('DNS_TOTAL_DEADLINE')
            values=parse(execute(command(host,source,kind),min(3,remaining)),host,source,kind);ok=True
        except Exception as exc:
            # Exception text and raw DNS responses never enter the trace.
            error=str(exc) if type(exc) is GateError and re.fullmatch('DNS_[A-Z_]+',str(exc)) else 'DNS_QUERY_EXCEPTION'
        with lock:trace['events'].append({'event':'QUERY_END','host':host,'source':source,'type':kind,
            'utc':utc(),'query_ok':ok,'values':values,'error_class':error,'duration_ms':(time.monotonic()-first)*1000})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(query,h,s,t) for s in sources for h in domains for t in ['A','AAAA']]
        for future in futures:future.result()
    trace['events'].append({'event':'SCRIPT_COMPLETE'})
    trace.update(ended_utc=utc(),total_ms=(time.monotonic()-started)*1000)
    if time.monotonic()>deadline:raise DNSFailure('DNS_TOTAL_DEADLINE',trace)
    return rows_from_trace(trace,domains,sources)
