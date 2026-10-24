"""Offline policy/regression tests. Mocked CLI is NOT real signature proof."""
import copy
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'release-v4'))
import attested_evidence_bridge as bridge
from guard_release_engine import digest,utc
import test_guard_release_engine as fixtures

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.expected=bridge.ExpectedRun('a'*40,11,1,123,456)
        self.nonce='b'*48
        self.run=dict(id=11,run_attempt=1,workflow_id=381769081,head_sha='a'*40,
            head_branch=bridge.REF.removeprefix('refs/heads/'),event='workflow_dispatch',
            status='completed',conclusion='success',path=bridge.WORKFLOW,
            repository={'id':123,'full_name':bridge.REPO,'owner':{'id':456}},
            head_repository={'id':123,'full_name':bridge.REPO})
        self.artifact=dict(id=12,name='prp-guard-'+self.nonce,expired=False,
            workflow_run={'id':11,'repository_id':123,'head_repository_id':123,
                          'head_sha':'a'*40,'head_branch':bridge.REF.removeprefix('refs/heads/')})

    def archive(self,raw=b'{}',name='observations.json'):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(name,raw)
        data=out.getvalue();self.artifact['digest']='sha256:'+hashlib.sha256(data).hexdigest();return data

    def statement(self,raw):
        e=self.expected
        return {'_type':'https://in-toto.io/Statement/v1','predicateType':'https://slsa.dev/provenance/v1',
            'subject':[{'name':'observations.json','digest':{'sha256':hashlib.sha256(raw).hexdigest()}}],
            'predicate':{'buildDefinition':{'buildType':'https://actions.github.io/buildtypes/workflow/v1',
            'externalParameters':{'workflow':{'ref':bridge.REF,'repository':'https://github.com/'+bridge.REPO,'path':bridge.WORKFLOW}},
            'internalParameters':{'github':{'event_name':'workflow_dispatch','repository_id':'123','repository_owner_id':'456','runner_environment':'github-hosted'}},
            'resolvedDependencies':[{'uri':'git+https://github.com/'+bridge.REPO+'@'+bridge.REF,'digest':{'gitCommit':e.commit}}]},
            'runDetails':{'builder':{'id':'https://github.com/'+bridge.REPO+'/'+bridge.WORKFLOW+'@'+bridge.REF},
                          'metadata':{'invocationId':'https://github.com/'+bridge.REPO+'/actions/runs/11/attempts/1'}}}}

    def test_wrong_run_commit_attempt_and_event_rejected(self):
        bridge.validate_metadata(self.run,self.artifact,self.expected,self.nonce)
        for key,value in [('id',12),('run_attempt',2),('head_sha','c'*40),('event','pull_request'),('conclusion','failure'),('path','other.yml')]:
            with self.subTest(key=key):
                run=copy.deepcopy(self.run);run[key]=value
                with self.assertRaises(bridge.GateError):bridge.validate_metadata(run,self.artifact,self.expected,self.nonce)

    def test_fork_or_renamed_repository_id_rejected(self):
        run=copy.deepcopy(self.run);run['head_repository']['id']=999
        with self.assertRaises(bridge.GateError):bridge.validate_metadata(run,self.artifact,self.expected,self.nonce)

    def test_cached_artifact_and_wrong_nonce_rejected(self):
        for key,value in [('expired',True),('name','prp-guard-'+'c'*48)]:
            artifact=copy.deepcopy(self.artifact);artifact[key]=value
            with self.assertRaises(bridge.GateError):bridge.validate_metadata(self.run,artifact,self.expected,self.nonce)

    def test_modified_archive_rejected(self):
        data=self.archive()
        with self.assertRaises(bridge.GateError):bridge.payload_from_archive(data+b'changed',self.artifact)

    def test_paths_and_extra_files_not_extracted(self):
        for name in ['../observations.json','/observations.json','other.json']:
            data=self.archive(name=name)
            with self.assertRaises(bridge.GateError):bridge.payload_from_archive(data,self.artifact)

    def test_duplicate_json_keys_rejected(self):
        data=self.archive(b'{"nonce":"first","nonce":"second"}')
        with self.assertRaises(bridge.GateError):bridge.payload_from_archive(data,self.artifact)

    def test_valid_archive_and_statement_policy(self):
        data=self.archive();raw,payload=bridge.payload_from_archive(data,self.artifact)
        self.assertEqual(payload,{})
        bridge.validate_statement(self.statement(raw),raw,self.expected)

    def test_wrong_statement_subject_run_or_runner_rejected(self):
        raw=b'{}'
        for kind in ['subject','attempt','runner','commit','repository','runner_environment','build_type']:
            with self.subTest(kind=kind):
                s=self.statement(raw)
                if kind=='subject':s['subject'][0]['digest']['sha256']='0'*64
                if kind=='attempt':s['predicate']['runDetails']['metadata']['invocationId']+='0'
                if kind=='runner':s['predicate']['runDetails']['builder']['id']='https://github.com/actions/runner/self-hosted'
                if kind=='commit':s['predicate']['buildDefinition']['resolvedDependencies'][0]['digest']['gitCommit']='c'*40
                if kind=='repository':s['predicate']['buildDefinition']['internalParameters']['github']['repository_id']='999'
                if kind=='runner_environment':s['predicate']['buildDefinition']['internalParameters']['github']['runner_environment']='self-hosted'
                if kind=='build_type':s['predicate']['buildDefinition']['buildType']='https://evil.invalid/buildtype'
                with self.assertRaises(bridge.GateError):bridge.validate_statement(s,raw,self.expected)

    def test_unpinned_verifier_never_executes(self):
        with patch.object(bridge.subprocess,'run') as run:
            with self.assertRaises(bridge.GateError):bridge.verify_cli(b'{}',b'{}',self.expected,'missing-gh.exe','0'*64)
            run.assert_not_called()

    def test_signature_rejection_never_exports_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            cli=pathlib.Path(directory)/'gh';cli.write_bytes(b'unit-test-placeholder-not-executable')
            pin=hashlib.sha256(cli.read_bytes()).hexdigest()
            p=subprocess.CompletedProcess([],1,stdout=b'',stderr=b'SECRET-CANARY')
            with patch.object(bridge.subprocess,'run',return_value=p):
                with self.assertRaises(bridge.GateError) as exc:bridge.verify_cli(b'{}',b'{}',self.expected,cli,pin)
            self.assertNotIn('SECRET',str(exc.exception))

    def test_verifier_has_exact_policy_and_no_session_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            cli=pathlib.Path(directory)/'gh';cli.write_bytes(b'unit-test-placeholder-not-executable')
            pin=hashlib.sha256(cli.read_bytes()).hexdigest();raw=b'{}'
            output=json.dumps([{'verificationResult':{'statement':self.statement(raw)}}]).encode()
            with patch.dict(bridge.os.environ,{'GH_TOKEN':'SECRET-CANARY','PRP_SESSION_KEY':'SECRET-CANARY'}),patch.object(bridge.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=output,stderr=b'')) as run:
                bridge.verify_cli(raw,b'{}',self.expected,cli,pin)
            args=run.call_args.args[0];env=run.call_args.kwargs['env']
            self.assertIn('--deny-self-hosted-runners',args)
            self.assertEqual(args[args.index('--source-digest')+1],self.expected.commit)
            self.assertNotIn('--signer-workflow',args) # mutually exclusive with exact certificate identity
            self.assertEqual(args[args.index('--cert-identity')+1],'https://github.com/'+bridge.REPO+'/'+bridge.WORKFLOW+'@'+bridge.REF)
            self.assertNotIn('GH_TOKEN',env);self.assertNotIn('PRP_SESSION_KEY',env)

    def test_original_gate_still_rejects_bad_response_even_with_provenance_mocked(self):
        fixture=fixtures.ReleaseTests('test_accept');fixture.setUp();self.addCleanup(fixture.tearDown)
        job=dict(deployment_id='offline-bridge-fixture',phase='preflight',nonce=self.nonce,
            manifest_sha256=digest(fixture.manifest),source_config=fixture.old,target=fixture.manifest['target'],
            probe_sha256=fixture.manifest['probe_sha256'],issued_utc=utc(),max_seconds=30,route_proofs={})
        payload=fixture.provider(job)['payload'];payload['observations'][0].update(status=500,passed=True)
        data=self.archive(json.dumps(payload).encode())
        with patch.object(bridge,'verify_cli'):
            with self.assertRaisesRegex(bridge.GateError,'RESPONSE_CONTRACT'):
                bridge.accept_attested(self.run,self.artifact,data,b'{}',self.expected,job,fixture.manifest,
                    digest(fixture.manifest),fixture.keys,'unused','unused')

    def test_mocked_provenance_cannot_override_nonce_or_freshness(self):
        fixture=fixtures.ReleaseTests('test_accept');fixture.setUp();self.addCleanup(fixture.tearDown)
        job=dict(deployment_id='offline-bridge-fixture',phase='preflight',nonce=self.nonce,
            manifest_sha256=digest(fixture.manifest),source_config=fixture.old,target=fixture.manifest['target'],
            probe_sha256=fixture.manifest['probe_sha256'],issued_utc=utc(),max_seconds=30,route_proofs={})
        original=fixture.provider(job)['payload']
        for change in [{'nonce':'c'*48},{'started_utc':'2000-01-01T00:00:00+00:00'}]:
            payload=copy.deepcopy(original);payload.update(change);data=self.archive(json.dumps(payload).encode())
            with patch.object(bridge,'verify_cli'):
                with self.assertRaises(bridge.GateError):
                    bridge.accept_attested(self.run,self.artifact,data,b'{}',self.expected,job,fixture.manifest,
                        digest(fixture.manifest),fixture.keys,'unused','unused')

if __name__=='__main__':unittest.main()
