import test from 'node:test'
import assert from 'node:assert/strict'
import {capturePremergeReceipt,verifyPersistedPremergeReceipt} from './review-receipt.mjs'
import {REQUIRED_CHECKS} from './review-gate.mjs'
const H='a'.repeat(40),B='b'.repeat(40),T='c'.repeat(40),M='d'.repeat(40),TREE='e'.repeat(40),S='f'.repeat(40)
const R={id:1261866723,full_name:'micor-cjj-spec/matrix-prp'},target='integrate/REQ-20261031-001',head='feat/t001',req='REQ-20261031-001',task='T-001'
const request='22222222-2222-4222-8222-222222222222',claim='11111111-1111-4111-8111-111111111111'
const ci='.github/workflows/ci.yml',impact='.github/workflows/feature-impact.yml',contract='.github/workflows/prp-dev-collab-contract.yml'
const completed='2026-11-25T06:00:00Z',captured='2026-11-25T06:01:00Z',merged='2026-11-25T06:02:00Z'
const make=()=>({schema_version:1,requirement_id:req,issue_number:132,status:'ACTIVE',version:3,title:'MVP',tasks:[{task_id:task,issue_number:133,title:'Core',status:'IN_REVIEW',claim:{claim_id:claim,worker_id:'chat-A',actor:'micor-cjj-spec',generation:1},depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],pr_number:138,head_sha:H}],processed_requests:[{request_id:request,fingerprint:'a'.repeat(64),actor:'micor-cjj-spec',receipt:{type:'submit',task_id:task,request_id:request,version:3,status:'IN_REVIEW'}}]})
const commit=sha=>({sha,tree:{sha:TREE},parents:[{sha:B},{sha:H}]})
function pre(){
 const e={pr:{number:138,state:'open',merged:false,draft:false,mergeable:true,merge_commit_sha:T,changed_files:1,base:{ref:target,sha:B,repo:R},head:{ref:head,sha:H,repo:R}},
   branch:{name:target,protected:true,commit:{sha:B}},testCommit:commit(T),files:[{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}],
   workflowBlobs:Object.fromEntries([ci,impact,contract].map(p=>[p,[S,S]])),checks:{total_count:7,check_runs:[]},runs:{},jobs:{}}
 REQUIRED_CHECKS.forEach((name,i)=>{
   const id=i+100,runId=name==='impact-report'?2:name==='dev-collab-contract'?3:1,path=runId===1?ci:runId===2?impact:contract
   const workflow=runId===1?'CI':runId===2?'Feature Impact Report':'PRP Dev Collaboration Contract'
   e.checks.check_runs.push({id,name,head_sha:H,status:'completed',conclusion:'success',app:{id:15368,slug:'github-actions'},details_url:'https://github.com/'+R.full_name+'/actions/runs/'+runId+'/job/'+id})
   e.runs[runId]={id:runId,path,name:workflow,event:'pull_request',status:'completed',conclusion:'success',head_sha:H,head_branch:head,repository:R,head_repository:R,run_attempt:1,created_at:'2026-11-25T05:59:00Z',pull_requests:[{number:138,head:{sha:H,repo:{id:R.id}},base:{ref:target,sha:B,repo:{id:R.id}}}]}
   const list=e.jobs[runId]??={total_count:0,jobs:[]};list.jobs.push({id,name,run_id:runId,run_attempt:1,head_sha:H,head_branch:head,workflow_name:workflow,status:'completed',conclusion:'success',started_at:'2026-11-25T05:59:10Z',completed_at:completed});list.total_count++
 })
 return e
}
function post(){
 const e=pre();e.pr={...e.pr,state:'closed',merged:true,merged_at:merged,merge_commit_sha:M};e.branch.commit.sha=M;e.actualMergeCommit=commit(M)
 e.comparison={status:'identical',behind_by:0,base_commit:{sha:M},merge_base_commit:{sha:M},commits:[]}
 Object.values(e.runs).forEach(r=>r.pull_requests=[])
 return e
}
const policy=()=>({
  "id": 28050327,
  "name": "protect-collab-integration",
  "target": "branch",
  "source_type": "Repository",
  "source": "micor-cjj-spec/matrix-prp",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "refs/heads/integrate/REQ-20261031-001"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": false,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
        "required_status_checks": [
          {
            "context": "backend-tests",
            "integration_id": 15368
          },
          {
            "context": "web-build",
            "integration_id": 15368
          },
          {
            "context": "mobile-build",
            "integration_id": 15368
          },
          {
            "context": "db-migration-integration",
            "integration_id": 15368
          },
          {
            "context": "video-db-integration",
            "integration_id": 15368
          },
          {
            "context": "impact-report",
            "integration_id": 15368
          },
          {
            "context": "dev-collab-contract",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c",
  "created_at": "2026-11-25T05:47:06.929Z",
  "updated_at": "2026-11-25T05:47:07.076Z",
  "bypass_actors": [],
  "current_user_can_bypass": "never"
})

import {buildOwnerRulesetAttestation} from './review-gate.mjs'
import {collectReceiptEvidence,verifyReceiptOrigin,loadProtectedReceipt,verifyReceiptAccept,verifyReceiptCommand,submittedReceiptPath,receiptAppendMarker} from './review-receipt-runtime.mjs'
const root='repos/'+R.full_name,main='1'.repeat(40),append='2'.repeat(40),stateHead='3'.repeat(40),blob='4'.repeat(40)
const captureRequest='33333333-3333-4333-8333-333333333333',acceptRequest='44444444-4444-4444-8444-444444444444'
const issueTime='2026-11-25T06:00:30Z',runStart='2026-11-25T06:00:31Z',stepStart='2026-11-25T06:00:45Z',stepEnd='2026-11-25T06:01:20Z'
const origin={request_id:captureRequest,source_issue:999,issue_created_at:issueTime,run_id:9001,main_sha:main}
const captureBody=()=>({schema_version:1,action:'capture_receipt',request_id:captureRequest,requirement_id:req,task_id:task,worker_id:'chat-A',
 claim_id:claim,expected_version:3,expected_state_sha:S,pr_number:138,head_sha:H,
 policy_attestation:buildOwnerRulesetAttestation(policy(),{requestId:captureRequest,action:'capture_receipt',requirementId:req,taskId:task,prNumber:138,headSha:H,stateVersion:3,mainSha:main,stateSha:S,observedAt:issueTime})})
function checkoutFixture(j){
 const action=j.workflow_name==='CI'?'v4':'3d3c42e5aac5ba805825da76410c181273ba90b1'
 const resolved=action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':action
 j.steps=[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+action,conclusion:'success',started_at:'2026-11-25T05:59:15Z',completed_at:'2026-11-25T05:59:20Z'}]
 return [
  "2026-11-25T05:59:14Z Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")",
  '2026-11-25T05:59:15Z ##[group]Run actions/checkout@'+action,
  '2026-11-25T05:59:16Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags origin +'+T+':refs/remotes/pull/138/merge',
  '2026-11-25T05:59:17Z [command]/usr/bin/git checkout --progress --force refs/remotes/pull/138/merge',
  '2026-11-25T05:59:18Z [command]/usr/bin/git log -1 --format=%H','2026-11-25T05:59:19Z '+T,
  '2026-11-25T05:59:21Z ##[group]Run tests'].join('\n')
}
function routesFor(e){
 const routes={
  [root+'/pulls/138']:e.pr,[root+'/branches/'+encodeURIComponent(target)]:e.branch,
  [root+'/pulls/138/files?per_page=100']:e.files,[root+'/commits/'+H+'/check-runs?per_page=100&filter=latest']:e.checks,
  [root+'/git/commits/'+T]:e.testCommit,[root+'/git/commits/'+M]:e.actualMergeCommit,
  [root+'/compare/'+M+'...'+M]:e.comparison
 }
 for(const [id,r] of Object.entries(e.runs)){routes[root+'/actions/runs/'+id]=r;routes[root+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest']=e.jobs[id]}
 for(const list of Object.values(e.jobs))for(const j of list.jobs)routes[root+'/actions/jobs/'+j.id+'/logs']=checkoutFixture(j)
 for(const p of [ci,impact,contract])for(const ref of [B,T,M])routes[root+'/contents/'+p+'?ref='+ref]={sha:S}
 return routes
}
const mock=routes=>route=>{if(!Object.hasOwn(routes,route))throw Error('missing fixture '+route);return structuredClone(routes[route])}
function storedFixture(){
 const s=make(),e=collectReceiptEvidence(s,task,mock(routesFor(pre())))
 e.captureOrigin=origin
 return capturePremergeReceipt(s,task,e,{stateSha:S,capturedAt:captured})
}
function content(path,bytes,sha=blob){return {type:'file',path,sha,encoding:'base64',size:Buffer.byteLength(bytes),content:Buffer.from(bytes).toString('base64')}}
function originRoutes(stored){
 const path=submittedReceiptPath(make(),task),bytes=JSON.stringify(stored,null,2)+'\n'
 const cmp=(a,b)=>({status:a===b?'identical':'ahead',ahead_by:a===b?0:1,behind_by:0,base_commit:{sha:a},merge_base_commit:{sha:a},commits:[]})
 const routes=routesFor(post())
 Object.assign(routes,{
  [root+'/contents/'+path+'?ref='+stateHead]:content(path,bytes),
  [root+'/contents/'+path+'?ref='+append]:content(path,bytes),
  [root+'/commits?sha='+stateHead+'&path='+encodeURIComponent(path)+'&per_page=100']:[{sha:append}],
  [root+'/git/commits/'+append]:{sha:append,parents:[{sha:S}]},
  [root+'/compare/'+S+'...'+append]:{...cmp(S,append),files:[{filename:path,status:'added'}]},
  [root+'/compare/'+append+'...'+stateHead]:cmp(append,stateHead),
  [root+'/compare/'+main+'...'+main]:cmp(main,main),
  [root+'/contents/requirements/'+req+'.json?ref='+S]:content('requirements/'+req+'.json',JSON.stringify(make())),
  [root+'/issues/999']:{number:999,user:{id:123868412,login:'micor-cjj-spec'},author_association:'OWNER',title:'[PRP-COLLAB-REQUEST]',created_at:issueTime,body:JSON.stringify(captureBody())},
  [root+'/rulesets/28050327']:policy(),
  [root+'/actions/runs/9001']:{id:9001,event:'issues',path:'.github/workflows/prp-collab-issue-ingress.yml',head_branch:'main',head_sha:main,run_attempt:1,actor:{id:123868412,login:'micor-cjj-spec'},repository:R,status:'completed',conclusion:'success',created_at:runStart,updated_at:'2026-11-25T06:01:40Z'},
  [root+'/actions/runs/9001/jobs?per_page=100&filter=latest']:{total_count:1,jobs:[{id:8001,run_id:9001,run_attempt:1,name:'apply-owner-request',head_sha:main,status:'completed',conclusion:'success',completed_at:'2026-11-25T06:01:39Z',steps:[{name:'Execute one strict Git CAS transaction',conclusion:'success',started_at:stepStart,completed_at:stepEnd}]}]},
  [root+'/actions/jobs/8001/logs']:'2026-11-25T06:01:19Z '+receiptAppendMarker(999,append,stored.digest)
 })
 for(const p of ['.github/workflows/prp-collab-issue-ingress.yml','app/scripts/dev-collab/review-receipt-runtime.mjs','app/scripts/dev-collab/issue-transaction.mjs'])routes[root+'/contents/'+p+'?ref='+main]={sha:blob}
 return routes
}
const command={type:'accept',requirement_id:req,task_id:task,request_id:acceptRequest,worker_id:'chat-A',claim_id:claim,pr_number:138,head_sha:H}
const proof={actorId:123868412,sourceIssue:1000,expectedVersion:3,stateSha:stateHead,expectedStateSha:stateHead}
test('collector binds all seven actual first checkouts to synthetic tree before capture',()=>{
 const s=make(),routes=routesFor(pre()),e=collectReceiptEvidence(s,task,mock(routes))
 assert.equal(capturePremergeReceipt(s,task,e,{stateSha:S,capturedAt:captured}).body.checks.length,7)
 routes[root+'/actions/jobs/100/logs']=routes[root+'/actions/jobs/100/logs'].replaceAll(T,S)
 assert.throws(()=>collectReceiptEvidence(s,task,mock(routes)),/RECEIPT_TESTED_TREE_MISMATCH/)
})
test('stored receipt origin and postmerge acceptance verify exact protected append and actual tested tree',()=>{
 const stored=storedFixture(),routes=originRoutes(stored)
 assert.equal(loadProtectedReceipt(make(),task,stateHead,mock(routes)).digest,stored.digest)
 assert.equal(verifyReceiptOrigin(make(),task,stateHead,main,stored,mock(routes),merged).receiptOriginVerified,true)
 assert.equal(verifyReceiptAccept(make(),command,proof,main,mock(routes)).receiptEvidenceVerified,true)
})
test('receipt origin rejects digest-only trust, late run, multiple file changes and wrong owner request',()=>{
 const stored=storedFixture()
 for(const change of [
  r=>r[root+'/actions/jobs/8001/logs']='2026-11-25T06:01:19Z forged',
  r=>r[root+'/actions/runs/9001'].updated_at='2026-11-25T06:03:00Z',
  r=>r[root+'/compare/'+S+'...'+append].files.push({filename:'other',status:'modified'}),
  r=>r[root+'/issues/999'].user.id=1,
  r=>r[root+'/git/commits/'+append].parents.push({sha:B}),
  r=>r[root+'/compare/'+append+'...'+stateHead].behind_by=1,
  r=>r[root+'/actions/jobs/100/logs']=r[root+'/actions/jobs/100/logs'].replaceAll(T,S)
 ]){const routes=originRoutes(stored);change(routes);assert.throws(()=>verifyReceiptAccept(make(),command,proof,main,mock(routes)))}
 assert.throws(()=>verifyReceiptCommand(make(),{...command,claim_id:captureRequest},proof),/RECEIPT_COMMAND_BINDING/)
})
