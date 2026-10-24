"""Separate candidate entrypoint; the existing collector is not switched.

Nine source files must be explicitly bound by a newly reviewed manifest.
Reuses the existing validation, DNS, scheduler and 300-second rejection logic.
"""
import importlib.util
from pathlib import Path
from guard_release_engine import GateError,digest,sha
from phase_tls_context_cache import load_probes

ROOT=Path(__file__).resolve().parent
WORKERS={'guard_release_engine.py','guard_external_probe.py','guard_external_h2.js',
    'guard_experimental_scheduler.py','windows_dns_worker.py','linux_dns_worker.py',
    'linux_external_collector.py','phase_tls_context_cache.py','cached_linux_collector.py'}


def collect_payload(job,manifest,pin):
    if digest(manifest)!=pin or job.get('manifest_sha256')!=pin:
        raise GateError('CACHED_COLLECTOR_MANIFEST_DRIFT')
    sources=manifest.get('worker_sources',{})
    if set(sources)!=WORKERS:raise GateError('CACHED_COLLECTOR_SOURCE_SET')
    if manifest.get('probe_sha256')!=digest(sources) or job.get('probe_sha256')!=digest(sources):
        raise GateError('CACHED_COLLECTOR_DIGEST')
    for name,wanted in sources.items():
        path=ROOT/name
        if path.is_symlink() or not path.is_file() or sha(path)!=wanted:
            raise GateError('CACHED_COLLECTOR_SOURCE_DRIFT')
    spec=importlib.util.spec_from_file_location('_prp_cached_phase_collector',ROOT/'linux_external_collector.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    # A private module instance: no mutation of imported production/default code.
    collector.WORKERS=set(WORKERS)
    collector.validate(job,manifest,pin)
    probes=load_probes(ROOT/'guard_external_probe.py')
    collector.http_probe=probes.http_probe
    collector.tls_probe=probes.tls_probe
    return collector.collect_payload(job,manifest,pin)
