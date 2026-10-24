"""Offline dispatch/discovery tests. Never dispatches a real GitHub job."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError
from hosted_phase_publisher import Publisher
import test_attested_evidence_bridge as fixtures


class PublisherTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.BridgeTests();fixture.setUp()
        self.run=fixture.run;self.artifact=fixture.artifact
        self.nonce=fixture.nonce;self.run['display_title']='prp-guard-'+self.nonce
        self.job=dict(deployment_id='e'*32,phase='preflight',nonce=self.nonce,
                      manifest_sha256='f'*64,source_config={},target={},probe_sha256='c'*64,
                      issued_utc='fixture',max_seconds=900)
        self.api=Mock();self.transport=Mock();self.transport.run.return_value=copy.deepcopy(self.run)
        self.raw=b'reviewed workflow fixture'
        self.publisher=Publisher(self.api,self.transport,'a'*40,hashlib.sha256(self.raw).hexdigest(),123,456,warp_authorized=True)

    def start(self):
        self.api.side_effect=[{'object':{'sha':'a'*40}},
            {'encoding':'base64','content':base64.b64encode(self.raw).decode()},{'status':204}]
        return self.publisher.start(dict(self.job,session_key='DO_NOT_FORWARD',route_proofs={'private':True}))

    def test_dispatch_strips_private_fields_and_is_once_only(self):
        self.start()
        body=self.api.call_args.kwargs['body']
        self.assertEqual(json.loads(body['inputs']['guard_job']),self.job)
        self.assertIs(body['inputs']['warp_authorized'],True)
        with self.assertRaises(GateError):self.publisher.start(self.job)
        self.assertEqual(self.api.call_count,3)

    def test_moved_branch_prevents_dispatch(self):
        self.api.return_value={'object':{'sha':'d'*40}}
        with self.assertRaises(GateError):self.publisher.start(self.job)
        self.api.assert_called_once()

    def test_default_has_no_registration_authority(self):
        publisher=Publisher(self.api,self.transport,'a'*40,hashlib.sha256(self.raw).hexdigest(),123,456)
        with self.assertRaises(GateError):publisher.start(self.job)
        self.api.assert_not_called()

    def test_workflow_drift_prevents_dispatch(self):
        self.api.side_effect=[{'object':{'sha':'a'*40}},{'encoding':'base64','content':'eA=='}]
        with self.assertRaises(GateError):self.publisher.start(self.job)
        self.assertEqual(self.api.call_count,2)

    def test_ambiguous_dispatch_not_repeated(self):
        self.api.side_effect=[{'object':{'sha':'a'*40}},
            {'encoding':'base64','content':base64.b64encode(self.raw).decode()},TimeoutError()]
        with self.assertRaises(TimeoutError):self.publisher.start(self.job)
        with self.assertRaises(GateError):self.publisher.start(self.job)
        self.assertEqual(self.api.call_count,3)

    def test_poll_discovers_exact_nonce_and_downloads_only_matching_artifacts(self):
        handle=self.start()
        self.api.side_effect=None
        self.api.return_value={'total_count':1,'workflow_runs':[self.run]}
        bundle=copy.deepcopy(self.artifact);bundle.update(id=13,name=self.artifact['name']+'-bundle')
        self.transport.artifacts.return_value=[self.artifact,bundle]
        self.transport.download.side_effect=[b'archive',b'bundle']
        result=self.publisher.poll(handle)
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(result['expected'].run_id,11)
        self.assertEqual(result['bundle_archive'],b'bundle')

    def test_duplicate_nonce_runs_rejected(self):
        handle=self.start();self.api.side_effect=None
        self.api.return_value={'total_count':2,'workflow_runs':[self.run,self.run]}
        with self.assertRaises(GateError):self.publisher.poll(handle)
        self.transport.run.assert_not_called()

    def test_running_poll_reuses_run_id(self):
        handle=self.start();handle['run_id']=11
        self.transport.run.return_value=dict(self.run,status='in_progress',conclusion=None)
        for _ in range(2):self.assertEqual(self.publisher.poll(handle),{'state':'RUNNING'})
        self.assertEqual(self.api.call_count,3)
        self.transport.download.assert_not_called()

    def test_rerun_attempt_rejected(self):
        handle=self.start();handle['run_id']=11
        self.transport.run.return_value=dict(self.run,run_attempt=2)
        with self.assertRaises(GateError):self.publisher.poll(handle)

    def test_failed_run_is_not_security_acceptance(self):
        handle=self.start();handle['run_id']=11
        self.transport.run.return_value=dict(self.run,conclusion='failure')
        self.assertEqual(self.publisher.poll(handle),{'state':'FAILED'})
        self.transport.download.assert_not_called()


if __name__=='__main__':unittest.main()
