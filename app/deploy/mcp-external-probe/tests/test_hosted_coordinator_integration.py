"""Real coordinator/inbox/file adapter, simulated hosted observations.

No GitHub, SSH, Nginx, WARP or cryptographic provenance claim. The unchanged
root EvidenceGate and actual temporary file backup/restore are exercised.
"""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import Coordinator,DirectoryInbox,EvidenceGate,digest,save,sign,sha
from hosted_transaction_watcher import Watcher
import test_guard_release_engine as fixtures


class IntegrationTests(unittest.TestCase):
    def run_case(self,fail_phases):
        fixture=fixtures.ReleaseTests('test_accept');fixture.setUp();self.addCleanup(fixture.tearDown)
        manifest=fixture.manifest;manifest['probe_sha256']='c'*64
        pin=digest(manifest);root=fixture.root/'transaction';inbox=root/'inbox'
        inbox.mkdir(parents=True)
        jobs=[];submitted=[]
        class Publisher:
            def start(self,job):
                jobs.append(copy.deepcopy(job));return copy.deepcopy(job)
            def poll(self,job):
                payload=fixture.provider(job)['payload']
                if job['phase'] in fail_phases:payload['observations'][0]['status']=500
                return {'state':'COMPLETED','payload':payload}
        def verify(result,job,key):
            envelope=sign(result['payload'],key)
            trusted=dict(job,route_proofs=fixture.proofs[job['phase']])
            EvidenceGate(manifest,pin,key).verify(envelope,trusted)
            return envelope
        def submit(job,envelope):
            submitted.append(copy.deepcopy(envelope))
            save(inbox/(job['deployment_id']+'.'+job['phase']+'.'+job['nonce']+'.json'),envelope)
        watcher=Watcher(Publisher(),verify,submit,pin)
        receiver=DirectoryInbox(inbox)
        def collect(job):
            state={'preflight':'PREFLIGHT','post_reload':'COLLECT_EXTERNAL_EVIDENCE','post_rollback':'POST_ROLLBACK'}[job['phase']]
            snapshot={'state':state,'job':job}
            self.assertEqual(watcher.step(snapshot),'STARTED')
            self.assertEqual(watcher.step(snapshot,fixture.keys),'SUBMITTED')
            return receiver(job)
        coordinator=Coordinator(fixture.a,root,EvidenceGate(manifest,pin,fixture.keys),collect,source_proofs=fixture.proofs)
        result=coordinator.run()
        self.assertEqual(len({j['nonce'] for j in jobs}),len(jobs))
        self.assertTrue(all('route_proofs' not in j and 'key' not in j for j in jobs))
        return fixture,result,jobs,submitted

    def test_all_valid_observations_accepted_by_original_root_gate(self):
        fixture,result,jobs,_=self.run_case(set())
        self.assertEqual(result['state'],'ACCEPT')
        self.assertEqual([j['phase'] for j in jobs],['preflight','post_reload'])
        self.assertEqual(fixture.reloads,[False])

    def test_bad_post_reload_observation_restores_files_and_fresh_rollback(self):
        fixture,result,jobs,submitted=self.run_case({'post_reload'})
        self.assertEqual(result['state'],'ROLLED_BACK')
        self.assertEqual([j['phase'] for j in jobs],['preflight','post_reload','post_rollback'])
        self.assertEqual(submitted[1]['payload']['observations'],[])
        self.assertEqual({n:sha(p) for n,p in fixture.live.items()},fixture.old)
        self.assertEqual(fixture.reloads,[False,True])

    def test_failed_rollback_acceptance_requires_recovery(self):
        _,result,_,_=self.run_case({'post_reload','post_rollback'})
        self.assertEqual(result['state'],'RECOVERY_REQUIRED')
        self.assertFalse(result['restored'])


if __name__=='__main__':unittest.main()
