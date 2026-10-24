"""Offline orchestration fixtures; no real network or root signing key."""
import copy
import datetime
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'release-v4'))
import linux_external_collector as collector
from guard_release_engine import digest,sha,utc,sign,EvidenceGate

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        for name in collector.WORKERS:(self.root/name).write_text('OFFLINE TEST STUB '+name)
        p=pathlib.Path(__file__).resolve().parent.parent/'release-v4/manifest.candidate.json'
        self.manifest=json.loads(p.read_text());self.manifest['parent_manifest_sha256']=collector.PARENT
        self.manifest['worker_sources']={n:sha(self.root/n) for n in collector.WORKERS}
        self.manifest['probe_sha256']=digest(self.manifest['worker_sources']);self.pin=digest(self.manifest)
        self.job=dict(deployment_id='a'*32,phase='preflight',nonce='b'*48,manifest_sha256=self.pin,
            source_config=self.manifest['phases']['preflight']['config'],target=self.manifest['target'],
            probe_sha256=self.manifest['probe_sha256'],issued_utc=utc(),max_seconds=900)

    def test_root_local_private_fields_not_forwarded(self):
        root=dict(self.job,route_proofs={'private':'local-only'},session_key='SECRET')
        public=collector.public_job(root)
        self.assertEqual(set(public),set(collector.PUBLIC_JOB));self.assertNotIn('SECRET',json.dumps(public))

    def test_source_drift_rejected_before_any_probe(self):
        (self.root/'guard_external_probe.py').write_text('changed')
        with patch.object(collector,'ROOT',self.root),patch.object(collector,'dns_linux') as dns:
            with self.assertRaises(collector.GateError):collector.validate(self.job,self.manifest,self.pin)
            dns.assert_not_called()

    def test_phase_contract_cannot_be_reduced(self):
        manifest=copy.deepcopy(self.manifest);manifest['phases']['post_reload']['requests'].popitem()
        pin=digest(manifest);job=dict(self.job,manifest_sha256=pin)
        with patch.object(collector,'ROOT',self.root):
            with self.assertRaisesRegex(collector.GateError,'PARENT_SECURITY_CONTRACT_DRIFT'):collector.validate(job,manifest,pin)

    def test_concurrency_limit_cannot_be_increased(self):
        manifest=copy.deepcopy(self.manifest);manifest['production_external_concurrency']=3;pin=digest(manifest)
        with patch.object(collector,'ROOT',self.root):
            with self.assertRaises(collector.GateError):collector.validate(dict(self.job,manifest_sha256=pin),manifest,pin)

    def test_secret_fields_wrong_phase_or_expired_job_rejected(self):
        for change in [{'session_key':'SECRET'},{'source_config':{}},{'nonce':'cached'},
                       {'issued_utc':'2000-01-01T00:00:00+00:00'},{'issued_utc':'2026-10-24T00:00:00'}]:
            with patch.object(collector,'ROOT',self.root):
                with self.assertRaises(collector.GateError):collector.validate(dict(self.job,**change),self.manifest,self.pin)

    def test_unsigned_payload_still_passes_original_gate_only_for_correct_fixture(self):
        def dns(domains,sources):return [{'host':h,'source':s,'utc':utc(),'query_ok':True,'a':['207.57.123.94'],'aaaa':[]} for h in domains for s in sources]
        def probe(spec,isolated):
            self.assertFalse(isolated);row=copy.deepcopy(spec)
            row.update(started_utc=utc(),ended_utc=utc(),error=None,chain_verified=True,san_verified=spec.get('san_required',True))
            return row
        def schedule(requests,fn,deadline,concurrency):
            self.assertEqual(concurrency,2)
            return [dict(fn(spec),request_id=ident) for ident,spec in requests.items()]
        with patch.object(collector.sys,'platform','linux'),patch.object(collector,'ROOT',self.root),patch.object(collector,'dns_linux',side_effect=dns),patch.object(collector,'schedule',side_effect=schedule),patch.object(collector,'http_probe',side_effect=probe),patch.object(collector,'tls_probe',side_effect=probe):
            payload=collector.collect_payload(self.job,self.manifest,self.pin)
        self.assertEqual(len(payload['observations']),20);self.assertNotIn('mac',payload)
        root_job=dict(self.job,route_proofs=self.manifest['phases']['preflight']['local_route_proofs'])
        key=b'ISOLATED-UNIT-KEY-NOT-PRODUCTION'
        self.assertTrue(EvidenceGate(self.manifest,self.pin,key).verify(sign(payload,key),root_job)['accepted'])

    def test_dns_failure_never_runs_http_matrix(self):
        with patch.object(collector.sys,'platform','linux'),patch.object(collector,'ROOT',self.root),patch.object(collector,'dns_linux',side_effect=collector.GateError('DNS_FAILED')),patch.object(collector,'schedule') as schedule:
            with self.assertRaises(collector.GateError):collector.collect_payload(self.job,self.manifest,self.pin)
            schedule.assert_not_called()

if __name__=='__main__':unittest.main()
