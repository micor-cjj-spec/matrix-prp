"""Synthetic trusted-reader snapshots; not server end-to-end evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError, digest, utc
from trusted_phase_context import bind_context, accept_with_trusted_reader


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((Path(__file__).resolve().parent.parent/'release-v4/manifest.candidate.json').read_text())
        self.pin=digest(self.manifest)
        self.job=dict(deployment_id='a'*32,phase='post_reload',nonce='b'*48,
                      manifest_sha256=self.pin,source_config=self.manifest['phases']['post_reload']['config'],
                      target=self.manifest['target'],probe_sha256=self.manifest['probe_sha256'],issued_utc=utc(),max_seconds=900)
        self.observed=dict(active_job=copy.deepcopy(self.job),deployment_id='a'*32,owner_alive=True,
                           state='COLLECT_EXTERNAL_EVIDENCE',source_config=copy.deepcopy(self.job['source_config']),
                           reviewed_sources=copy.deepcopy(self.manifest['reviewed_sources']),
                           local_attestation=dict(deployment_id='a'*32,phase='post_reload',verified_observations=346))

    def test_exact_reviewed_proofs_and_detached_result(self):
        result=bind_context(self.job,self.manifest,self.pin,self.observed)
        self.assertEqual(result['route_proofs'],self.manifest['phases']['post_reload']['local_route_proofs'])
        result['route_proofs'].clear()
        self.assertTrue(self.manifest['phases']['post_reload']['local_route_proofs'])

    def test_missing_or_changed_trusted_context_rejected(self):
        for field,value in [('owner_alive',False),('deployment_id','other'),('state','ACCEPT'),
                            ('source_config',{}),('reviewed_sources',{}),('active_job',{}),('local_attestation',{})]:
            with self.subTest(field=field):
                observed=copy.deepcopy(self.observed);observed[field]=value
                with self.assertRaises(GateError):bind_context(self.job,self.manifest,self.pin,observed)

    def test_uploaded_route_proof_cannot_override_reviewed_context(self):
        job=dict(self.job,route_proofs={'forged':{'passed':True}})
        result=bind_context(job,self.manifest,self.pin,self.observed)
        self.assertNotIn('forged',result['route_proofs'])

    def test_modified_manifest_rejected(self):
        self.manifest['phases']['post_reload']['local_route_proofs']={}
        with self.assertRaises(GateError):bind_context(self.job,self.manifest,self.pin,self.observed)

    def test_bridge_reads_current_context_and_preserves_local_only_key(self):
        reader=Mock(return_value=self.observed)
        with patch('attested_evidence_bridge.accept_attested',return_value={'fixture':True}) as verify:
            result=accept_with_trusted_reader(None,None,None,None,None,self.job,
                        self.manifest,self.pin,b'x'*32,'cli','pin',reader)
            self.assertEqual(result,{'fixture':True})
            reader.assert_called_once_with()
            self.assertIn('route_proofs',verify.call_args.args[5])
            self.assertEqual(verify.call_args.args[8],b'x'*32)

    def test_missing_context_stops_before_attestation_or_signing(self):
        with patch('attested_evidence_bridge.accept_attested') as verify:
            with self.assertRaises(GateError):
                accept_with_trusted_reader(None,None,None,None,None,self.job,
                    self.manifest,self.pin,b'x'*32,'cli','pin',lambda:{})
            verify.assert_not_called()


if __name__=='__main__':unittest.main()
