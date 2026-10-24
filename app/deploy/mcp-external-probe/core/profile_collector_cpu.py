"""Linux hosted-Runner allocation benchmark, no sockets or PRP requests.

Reused contexts here are a measurement comparison, NOT a TLS probe adapter.
No security or handshake equivalence is claimed by this allocation benchmark.
"""
import concurrent.futures
import json
import platform
import socket
import ssl
import statistics
import subprocess
import sys
import threading
import time


def measure(reuse):
    local=threading.local();lock=threading.Lock();created=0;active=0;peak=0
    def one(_):
        nonlocal created,active,peak
        start=time.perf_counter()
        with lock:active+=1;peak=max(peak,active)
        try:
            context=getattr(local,'context',None) if reuse else None
            if context is None:
                context=ssl.create_default_context()
                assert context.cert_store_stats()['x509_ca']>0
                with lock:created+=1
                if reuse:local.context=context
            context.check_hostname=True
            context.verify_mode=ssl.CERT_REQUIRED
            context.set_alpn_protocols(['http/1.1'])
            assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
            return time.perf_counter()-start
        finally:
            with lock:active-=1
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:times=list(pool.map(one,range(642)))
    return {'wall_seconds':round(time.perf_counter()-start,6),'operations':len(times),
            'contexts_created':created,'peak_workers':peak,'median_seconds':round(statistics.median(times),6),
            'maximum_seconds':round(max(times),6)}


def main():
    assert sys.platform.startswith('linux')
    def forbidden_socket(*args,**kwargs):raise RuntimeError('NETWORK_FORBIDDEN_IN_CPU_PROFILE')
    socket.socket=forbidden_socket
    fresh=measure(False);reused=measure(True)
    starts=[]
    for _ in range(14):
        start=time.perf_counter()
        subprocess.run(['node','-e',''],capture_output=True,check=True,timeout=5)
        starts.append(time.perf_counter()-start)
    report={'kind':'COLLECTOR_CPU_ALLOCATION_PROFILE_ONLY','production_requests':0,'warp_used':False,
        'tls_handshakes_performed':0,'production_acceptance':False,'python_version':platform.python_version(),
        'openssl_version':ssl.OPENSSL_VERSION,'fresh_contexts':fresh,'thread_local_allocation_comparison':reused,
        'node_empty_processes':{'count':14,'total_seconds':round(sum(starts),6),'median_seconds':round(statistics.median(starts),6)},
        'context_wall_difference_seconds':round(fresh['wall_seconds']-reused['wall_seconds'],6),
        'comparison_is_not_a_security_validated_cache':True}
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
