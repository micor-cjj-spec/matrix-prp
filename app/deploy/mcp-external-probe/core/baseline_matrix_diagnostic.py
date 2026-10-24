"""Fixed 682-request baseline diagnostic, NEVER production acceptance evidence.

No root job, session key, inbox, configuration change, or acceptance decision.
The diagnostic reports batches exceeding 300 seconds as stale, never passes
them. Its artifact is diagnostics.json, incompatible with the evidence bridge.
"""
import collections
import math
from pathlib import Path
import statistics
import threading
import time
from guard_release_engine import GateError,digest,epoch,sha,utc
from guard_external_probe import http_probe,tls_probe,h2_probe
from guard_experimental_scheduler import schedule
from linux_dns_worker import dns_linux
from linux_external_collector import PARENT,SAFE_ERRORS

ROOT=Path(__file__).resolve().parent
DNS_PIN='5b40eeeda63017f3f14ccb071213c20cfb617b9475a932137c7775384ed656fe'


def validate(manifest):
    if digest(manifest)!=PARENT:raise GateError('DIAGNOSTIC_PARENT_DRIFT')
    if len(manifest['phases']['post_reload']['requests'])!=682:raise GateError('DIAGNOSTIC_MATRIX_DRIFT')
    if manifest['max_observation_age_seconds']!=300 or manifest['production_external_concurrency']!=2:
        raise GateError('DIAGNOSTIC_LIMIT_DRIFT')
    for name,wanted in manifest['worker_sources'].items():
        path=ROOT/name
        if Path(name).name!=name or path.is_symlink() or sha(path)!=wanted:raise GateError('DIAGNOSTIC_SOURCE_DRIFT')
    if sha(ROOT/'linux_dns_worker.py')!=DNS_PIN:raise GateError('DIAGNOSTIC_DNS_SOURCE_DRIFT')


def diagnose(manifest):
    validate(manifest)
    started=utc();begin=time.monotonic();rows=[];lock=threading.Lock();dns=[];failure=None
    def probe(spec):
        first=time.monotonic()
        if spec.get('probe')=='tls':row=tls_probe(spec,False)
        elif spec.get('probe')=='h2':row=h2_probe(spec,False)
        else:row=http_probe(spec,False)
        # Keep only telemetry needed to distinguish delay from transport errors.
        error=row.get('error')
        metric={'family':spec['family'],'error':error if error in SAFE_ERRORS else ('OTHER_ERROR' if error else None),
                'started_utc':row['started_utc'],'elapsed':time.monotonic()-first}
        with lock:rows.append(metric)
        return row
    try:
        dns=dns_linux(manifest['domains'],manifest['dns_sources'])
        schedule(manifest['phases']['post_reload']['requests'],probe,begin+900,concurrency=2)
    except Exception as error:
        # Exception messages and raw HTTP/DNS output are never exported.
        failure=type(error).__name__ if type(error).__name__ in {'GateError','DNSFailure','TimeoutError','ValueError'} else 'OTHER_EXCEPTION'
    now=time.time();elapsed=time.monotonic()-begin
    durations=[r['elapsed'] for r in rows if math.isfinite(r['elapsed']) and r['elapsed']>=0]
    ages=[max(0,now-epoch(r['started_utc'])) for r in rows]
    dns_ages=[max(0,now-epoch(r['utc'])) for r in dns]
    return {'kind':'BASELINE_DIAGNOSTIC_ONLY','production_acceptance':False,
        'root_job_used':False,'configuration_changed':False,'expected_requests':682,
        'completed_requests':len(rows),'dns_rows':len(dns),'failure_type':failure,
        'elapsed_seconds':round(elapsed,3),'concurrency':2,'freshness_limit_seconds':300,
        'stale_request_count':sum(age>300 for age in ages),'stale_dns_rows':sum(age>300 for age in dns_ages),
        'oldest_request_age_seconds':round(max(ages,default=0),3),
        'oldest_dns_age_seconds':round(max(dns_ages,default=0),3),
        'family_counts':dict(collections.Counter(r['family'] for r in rows)),
        'transport_error_counts':dict(collections.Counter(r['error'] for r in rows if r['error'])),
        'request_duration_seconds':{'median':round(statistics.median(durations),3) if durations else None,
                                    'maximum':round(max(durations),3) if durations else None},
        'started_utc':started,'ended_utc':utc()}
