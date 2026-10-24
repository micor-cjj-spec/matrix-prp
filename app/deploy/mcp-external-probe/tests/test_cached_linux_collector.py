"""Composed collector fixtures; public requests and provenance are not tested."""
import copy,json
from pathlib import Path
import ssl,sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError,EvidenceGate,digest,sha,utc,sign
import linux_external_collector as default
import cached_linux_collector as cached


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);here=Path(__file__).resolve().parent;base=here.parent/'release-v4'
        for name in cached.WORKERS:
            source=here/name if (here/name).is_file() else base/name
            (self.root/name).write_bytes(source.read_bytes())
        self.manifest=json.loads((base/'manifest.candidate.json').read_text())
        self.manifest['parent_manifest_sha256']=default.PARENT
        self.manifest['worker_sources']={n:sha(self.root/n) for n in sorted(cached.WORKERS)}
        self.manifest['probe_sha256']=digest(self.manifest['worker_sources']);self.pin=digest(self.manifest)
        self.job=dict(deployment_id='a'*32,phase='preflight',nonce='b'*48,manifest_sha256=self.pin,
            probe_sha256=self.manifest['probe_sha256'],source_config=self.manifest['phases']['preflight']['config'],
            target=self.manifest['target'],issued_utc=utc(),max_seconds=900)

    def collect(self,bad=False):
        def dns(domains,sources):return [dict(host=h,source=s,utc=utc(),query_ok=True,a=['207.57.123.94'],aaaa=[]) for h in domains for s in sources]
        def probe(spec,isolated):
            self.assertFalse(isolated)
            row=copy.deepcopy(spec);row.update(started_utc=utc(),ended_utc=utc(),error=None,chain_verified=True,san_verified=spec.get('san_required',True))
            if bad:row['status']=500
            return row
        def schedule(requests,fn,deadline,concurrency):
            self.assertEqual(concurrency,2)
            return [dict(fn(spec),request_id=name) for name,spec in requests.items()]
        with patch.object(cached,'ROOT',self.root),patch.object(default.sys,'platform','linux'),patch('linux_dns_worker.dns_linux',side_effect=dns),patch('guard_experimental_scheduler.schedule',side_effect=schedule),patch.object(cached,'load_probes',return_value=SimpleNamespace(http_probe=probe,tls_probe=probe)):
            return cached.collect_payload(self.job,self.manifest,self.pin)

    def test_original_gate_accepts_only_complete_correct_fixture(self):
        payload=self.collect();self.assertEqual(len(payload['observations']),20)
        key=b'isolated-not-production';job=dict(self.job,route_proofs=self.manifest['phases']['preflight']['local_route_proofs'])
        self.assertTrue(EvidenceGate(self.manifest,self.pin,key).verify(sign(payload,key),job)['accepted'])

    def test_wrong_response_still_refused_by_original_gate(self):
        payload=self.collect(bad=True);key=b'isolated-not-production'
        job=dict(self.job,route_proofs=self.manifest['phases']['preflight']['local_route_proofs'])
        with self.assertRaises(GateError):EvidenceGate(self.manifest,self.pin,key).verify(sign(payload,key),job)

    def test_cache_source_drift_refused_before_loader_or_network(self):
        (self.root/'phase_tls_context_cache.py').write_text('drift')
        with patch.object(cached,'ROOT',self.root),patch.object(cached,'load_probes') as loader:
            with self.assertRaises(GateError):cached.collect_payload(self.job,self.manifest,self.pin)
            loader.assert_not_called()

    def test_default_collector_and_ssl_are_not_changed(self):
        workers=set(default.WORKERS);probe=default.http_probe;factory=ssl.create_default_context
        self.collect()
        self.assertEqual(default.WORKERS,workers);self.assertIs(default.http_probe,probe)
        self.assertIs(ssl.create_default_context,factory)

if __name__=='__main__':unittest.main()
