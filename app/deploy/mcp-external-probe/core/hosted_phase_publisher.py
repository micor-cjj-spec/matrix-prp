"""Nonce-bound GitHub phase dispatch. No root key or production mutation.

Requires a reviewed workflow digest and immutable commit. No automatic retry
of workflow dispatch: an ambiguous POST remains an operator-visible failure.
"""
import base64
import copy
import hashlib
import json
import re
from urllib.parse import urlencode
from attested_evidence_bridge import REPO, REF, WORKFLOW, ExpectedRun, GateError, validate_metadata
from linux_external_collector import public_job


class Publisher:
    def __init__(self, api, artifacts, commit, workflow_sha256, repository_id, owner_id):
        if not re.fullmatch('[0-9a-f]{40}',commit) or not re.fullmatch('[0-9a-f]{64}',workflow_sha256):
            raise GateError('PUBLISHER_SOURCE_PIN')
        ExpectedRun(commit,1,1,repository_id,owner_id)
        self.api,self.artifacts=api,artifacts
        self.commit,self.workflow_sha256=commit,workflow_sha256
        self.repository_id,self.owner_id=repository_id,owner_id
        self.started=set()

    def start(self, root_job):
        job=public_job(root_job)
        nonce=job['nonce']
        if not re.fullmatch('[0-9a-f]{48}',nonce):raise GateError('PUBLISHER_NONCE')
        if nonce in self.started:raise GateError('PUBLISHER_ALREADY_DISPATCHED')
        prefix='repos/'+REPO+'/'
        head=self.api(prefix+'git/ref/'+REF.removeprefix('refs/'))
        if head.get('object',{}).get('sha')!=self.commit:raise GateError('PUBLISHER_BRANCH_MOVED')
        source=self.api(prefix+'contents/'+WORKFLOW+'?'+urlencode({'ref':self.commit}))
        try:
            if source.get('encoding')!='base64':raise ValueError()
            raw=base64.b64decode(source['content'],validate=False)
        except (KeyError,ValueError,TypeError):raise GateError('PUBLISHER_WORKFLOW_FORMAT') from None
        if hashlib.sha256(raw).hexdigest()!=self.workflow_sha256:raise GateError('PUBLISHER_WORKFLOW_DRIFT')
        self.started.add(nonce)
        response=self.api(prefix+'actions/workflows/381769081/dispatches',method='POST',
            body={'ref':REF.removeprefix('refs/heads/'),'inputs':{'guard_job':json.dumps(job,sort_keys=True,separators=(',',':'))}})
        if response!={'status':204}:raise GateError('PUBLISHER_DISPATCH_UNCONFIRMED')
        return {'job':copy.deepcopy(job),'run_id':None,'attempt':1}

    def poll(self, handle):
        job=handle['job'];nonce=job['nonce'];title='prp-guard-'+nonce
        if handle['run_id'] is None:
            query=urlencode({'event':'workflow_dispatch','branch':REF.removeprefix('refs/heads/'),
                             'head_sha':self.commit,'per_page':100})
            data=self.api('repos/'+REPO+'/actions/workflows/381769081/runs?'+query)
            rows=data.get('workflow_runs')
            if not isinstance(rows,list) or data.get('total_count')!=len(rows):raise GateError('PUBLISHER_RUN_LIST_INCOMPLETE')
            matches=[r for r in rows if r.get('display_title')==title]
            if not matches:return {'state':'RUNNING'}
            if len(matches)!=1:raise GateError('PUBLISHER_RUN_AMBIGUOUS')
            handle['run_id']=matches[0]['id']
        run=self.artifacts.run(handle['run_id'])
        expected=ExpectedRun(self.commit,handle['run_id'],1,self.repository_id,self.owner_id)
        # Validate identity even while queued/running, without claiming success.
        prospective=dict(run,status='completed',conclusion='success')
        stub={'id':1,'name':title,'expired':False,'workflow_run':dict(id=expected.run_id,
             repository_id=self.repository_id,head_repository_id=self.repository_id,
             head_sha=self.commit,head_branch=REF.removeprefix('refs/heads/'))}
        validate_metadata(prospective,stub,expected,nonce)
        if run.get('display_title')!=title:raise GateError('PUBLISHER_RUN_TITLE')
        if run.get('status') in {'queued','in_progress','waiting','pending','requested'}:return {'state':'RUNNING'}
        if run.get('status')!='completed':raise GateError('PUBLISHER_RUN_STATUS')
        if run.get('conclusion')!='success':return {'state':'FAILED'}
        artifacts=self.artifacts.artifacts(expected.run_id)
        selected={}
        for name in (title,title+'-bundle'):
            candidates=[a for a in artifacts if a.get('name')==name]
            if len(candidates)!=1:raise GateError('PUBLISHER_ARTIFACT_SET')
            selected[name]=candidates[0]
        artifact=selected[title]
        validate_metadata(run,artifact,expected,nonce)
        # Bundle's own subject binding is established by the pinned CLI later.
        bundle_meta=dict(selected[title+'-bundle'],name=title)
        validate_metadata(run,bundle_meta,expected,nonce)
        return {'state':'COMPLETED','run':run,'expected':expected,'artifact':artifact,
                'archive':self.artifacts.download(artifact),
                'bundle_archive':self.artifacts.download(selected[title+'-bundle'])}
