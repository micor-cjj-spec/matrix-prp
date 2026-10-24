"""Unsigned Linux observation orchestration; review candidate, not installed.

Reuses the reviewed HTTP/TLS/H2 workers and two-worker scheduler. The Runner has
no administrator HMAC key. A separate attestation covers the returned payload;
the local administrator bridge subsequently verifies and signs it.
"""
import copy
import datetime
from pathlib import Path
import re
import sys
import time
from guard_release_engine import GateError, digest, epoch, sha, utc
from guard_external_probe import http_probe, tls_probe, h2_probe
from guard_experimental_scheduler import schedule
from linux_dns_worker import dns_linux, validate as validate_dns

ROOT=Path(__file__).resolve().parent
PARENT='58899abe603da5b4191469b15cb8b70dc264ed9903e7549d7e45da05fa9b6011'
PHASES='e3bdcbb8cb36c0be9ddd533a836a0d56b93769a3c14aec972349c687a1170a09'
LOCAL='9dc9980766d1387c4b15e1defb873818399b45845e41df4ba5b3d34a9b6a2e41'
WORKERS={'guard_release_engine.py','guard_external_probe.py','guard_external_h2.js',
         'guard_experimental_scheduler.py','windows_dns_worker.py','linux_dns_worker.py','linux_external_collector.py'}
PUBLIC_JOB=('deployment_id','phase','nonce','manifest_sha256','source_config','target',
            'probe_sha256','issued_utc','max_seconds')
IDENTITY=PUBLIC_JOB[:7]

def public_job(root_job):
    """Never forward root-local route attestations or incidental secret fields."""
    return {name:copy.deepcopy(root_job[name]) for name in PUBLIC_JOB}

def validate(job,manifest,pin):
    if not isinstance(job,dict) or set(job)!=set(PUBLIC_JOB):raise GateError('PUBLIC_JOB_FIELDS')
    if not isinstance(pin,str) or not re.fullmatch('[0-9a-f]{64}',pin) or digest(manifest)!=pin:
        raise GateError('WORKER_MANIFEST_DRIFT')
    if manifest.get('parent_manifest_sha256')!=PARENT or digest(manifest.get('phases'))!=PHASES or digest(manifest.get('local_requests'))!=LOCAL:
        raise GateError('PARENT_SECURITY_CONTRACT_DRIFT')
    if manifest.get('max_observation_age_seconds')!=300 or type(manifest.get('production_external_concurrency')) is not int or manifest['production_external_concurrency']!=2:
        raise GateError('SECURITY_LIMIT_DRIFT')
    sources=manifest.get('worker_sources',{})
    if not isinstance(sources,dict) or set(sources)!=WORKERS:raise GateError('WORKER_SOURCE_SET')
    if any(not (ROOT/name).is_file() or (ROOT/name).is_symlink() or sha(ROOT/name)!=value for name,value in sources.items()):
        raise GateError('WORKER_SOURCE_DRIFT')
    if manifest.get('probe_sha256')!=digest(sources) or job['probe_sha256']!=digest(sources):raise GateError('WORKER_DIGEST_DRIFT')
    if job['manifest_sha256']!=pin or job['target']!=manifest['target']:raise GateError('WORKER_JOB_IDENTITY')
    if not isinstance(job['deployment_id'],str) or not re.fullmatch('[0-9a-f]{32}',job['deployment_id']):raise GateError('DEPLOYMENT_ID_INVALID')
    if not isinstance(job['nonce'],str) or not re.fullmatch('[0-9a-f]{48}',job['nonce']):raise GateError('NONCE_INVALID')
    if job['phase'] not in {'preflight','post_reload','post_rollback'} or job['source_config']!=manifest['phases'][job['phase']]['config']:
        raise GateError('WORKER_PHASE_SOURCE_MISMATCH')
    if type(job['max_seconds']) is not int or job['max_seconds']!=manifest['max_seconds'] or not 1<=job['max_seconds']<=900:
        raise GateError('WORKER_PHASE_BUDGET')
    try:
        stamp=datetime.datetime.fromisoformat(job['issued_utc'])
        if stamp.utcoffset()!=datetime.timedelta(0):raise ValueError()
        issued=epoch(job['issued_utc'])
    except (ValueError,TypeError):raise GateError('JOB_ISSUED_TIME_INVALID')
    if not issued<=time.time()+2 or time.time()>issued+job['max_seconds']:raise GateError('JOB_EXPIRED_OR_FUTURE')
    validate_dns(manifest['domains'],manifest['dns_sources'])

def collect_payload(job,manifest,pin):
    if not sys.platform.startswith('linux'):raise GateError('LINUX_COLLECTOR_REQUIRED')
    validate(job,manifest,pin)
    start=utc()
    # Fail on DNS errors before sending the much larger HTTP matrix.
    answers=dns_linux(manifest['domains'],manifest['dns_sources'])
    remaining=epoch(job['issued_utc'])+job['max_seconds']-time.time()
    if remaining<=0:raise GateError('COLLECTOR_DEADLINE')
    def probe(spec):
        if spec.get('probe')=='tls':return tls_probe(spec,False)
        if spec.get('probe')=='h2':return h2_probe(spec,False)
        return http_probe(spec,False)
    rows=schedule(manifest['phases'][job['phase']]['requests'],probe,time.monotonic()+remaining,concurrency=2)
    end=utc()
    if time.time()>epoch(job['issued_utc'])+job['max_seconds']:raise GateError('COLLECTOR_DEADLINE')
    # Do not produce an apparently usable stale batch. The root gate still
    # independently applies every timestamp and response-contract requirement.
    if any(time.time()-epoch(row['started_utc'])>300 for row in rows) or any(time.time()-epoch(row['utc'])>300 for row in answers):
        raise GateError('COLLECTOR_OBSERVATIONS_STALE')
    result={name:copy.deepcopy(job[name]) for name in IDENTITY}
    result.update(started_utc=start,ended_utc=end,observations=rows,dns=answers)
    return result
