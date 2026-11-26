import test from 'node:test'
import assert from 'node:assert/strict'
import {pathToFileURL} from 'node:url'
import {verifyHistorical271,verifyHistorical271Binding,HISTORICAL_271_PREFIX} from './review-historical-271.mjs'
const REPO='micor-cjj-spec/matrix-prp',ROOT='repos/'+REPO,REQ='REQ-20261031-001',TARGET='integrate/'+REQ
const HEAD='48b3a69232690e7e2fb54a2d92efac02cc512c0e',BASE='3ada1c20d2b9378f8dff6e4bab9c5735d162b8b4',MERGE='3177009eeb692c766715ba0c6e1133844f469981',TEST='4e6e0a6deda745e170c89fae51a0c115621622f9',TREE='e5fb9857635bc91946ebcf6b97dececd0177e592'
const SOURCE=TARGET+'-solo-collab-only-20261122',PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
const TASKS={
 'T-002':{scopes:['.github/ISSUE_TEMPLATE/','.github/PULL_REQUEST_TEMPLATE.md'],deps:[],files:{
 '.github/ISSUE_TEMPLATE/prp-requirement.yml':'4f9d4d8e2b7a296e935504a74e935a9252841a14',
 '.github/ISSUE_TEMPLATE/prp-task.yml':'2cc7728b7979a01043d2ae486a5c4ae43d1b339f',
 '.github/PULL_REQUEST_TEMPLATE.md':'47f35bfc380fd0e26c04c7b9f0ef732222a5865a'}},
 'T-003':{scopes:['app/scripts/dev-collab/coordinator-cli.mjs','app/scripts/dev-collab/state-transaction.sh','.github/workflows/prp-collab-coordinator.yml'],deps:['T-001','T-007','T-009'],files:{
 'app/scripts/dev-collab/coordinator-cli.mjs':'9de1cd1a6fda98e5458ba3fa57adb06fdd52ad85',
 'app/scripts/dev-collab/state-transaction.sh':'bee4fa48dc1d7c90995eeb1cbdbf159618d0fa1f',
 '.github/workflows/prp-collab-coordinator.yml':'f7b503b362a066c3e5492dca37db0a8cf510cb68'}},
 'T-006':{scopes:[".github/workflows/prp-collab-board.yml",".github/workflows/prp-collab-issue-projection.yml","app/scripts/dev-collab/board-workflow.test.mjs","app/scripts/dev-collab/board.mjs","app/scripts/dev-collab/board.test.mjs","app/scripts/dev-collab/projection-cli.mjs","app/scripts/dev-collab/projection-workflow.test.mjs","app/scripts/dev-collab/projection.mjs","app/scripts/dev-collab/projection.test.mjs"],deps:['T-003'],files:{
  '.github/workflows/prp-collab-board.yml':'cd3f97a774f7667a0a9710d4ae2b713a5b636898',
  '.github/workflows/prp-collab-issue-projection.yml':'22c5a9a67c0c3bdb7045f422b8450b76628c93ba',
  'app/scripts/dev-collab/board-workflow.test.mjs':'09e15fde743f375365176c94d6363354ecc8e7a9',
  'app/scripts/dev-collab/board.mjs':'887ed40f5956823d5b1fb32cc1a247bbbfbda272',
  'app/scripts/dev-collab/board.test.mjs':'6ed38d9597f2bb0917e7ace335d728b615e60a97',
  'app/scripts/dev-collab/projection-cli.mjs':'71f5d62f17bc7f24adc8553a63184bb6592a22ad',
  'app/scripts/dev-collab/projection-workflow.test.mjs':'fc399040075ff462af960d721c88cdc2d2af1ddf',
  'app/scripts/dev-collab/projection.mjs':'39be3a16cabb57abba8820823ac008637353c3a7',
  'app/scripts/dev-collab/projection.test.mjs':'471bff463cdba97bd359e53650dc541d6a6971c6'}}
}
const CI='.github/workflows/ci.yml',CONTRACT='.github/workflows/prp-dev-collab-contract.yml',IMPACT='.github/workflows/feature-impact.yml'
const workflows={[CI]:'695b53214437053943908217ab855b069dd30a24',[IMPACT]:'ce48ed0e167509e60b04d50c4c9493a705096b52',[CONTRACT]:'b00af8f8c53ba88fa62d873d1543b0bddfe96880'}
const runs=[[44973283672,'CI',CI,2,34],[44973283492,'PRP Dev Collaboration Contract',CONTRACT,1,1],[44973284191,'Feature Impact Report',IMPACT,1,1]]
const jobs=[['backend-tests',44973283672,137075248547],['web-build',44973283672,137075225050],['mobile-build',44973283672,137075225377],['db-migration-integration',44973283672,137075224308],['video-db-integration',44973283672,137075255279],['impact-report',44973284191,137057508098],['dev-collab-contract',44973283492,137057505664]]
const repo={id:1261866723,full_name:REPO},actor='micor-cjj-spec',claim_id='11111111-1111-4111-8111-111111111111',submitId='33333333-3333-4333-8333-333333333333'
const request_id='22222222-2222-4222-8222-222222222222',version=28
const mainDefault='a'.repeat(40),integrationDefault='b'.repeat(40),stateDefault='c'.repeat(40)
export function historical271Fixture(task_id='T-003',mainSha=mainDefault,stateSha=stateDefault){
 const version=task_id==='T-006'?36:28
 const cfg=TASKS[task_id],command={type:'accept',requirement_id:REQ,task_id,worker_id:'chat-A',claim_id,request_id,pr_number:271,head_sha:HEAD,note:HISTORICAL_271_PREFIX+'PRP_RULESET_ATTESTATION_V1:{}'}
 const snapshot={schema_version:1,requirement_id:REQ,issue_number:132,title:'MVP',version,status:'ACTIVE',
  tasks:Array.from({length:9},(_,i)=>{const id='T-'+String(i+1).padStart(3,'0'),c=TASKS[id];return {task_id:id,issue_number:[133,134,135,136,137,141,142,143,146][i],title:id,status:id===task_id?'IN_REVIEW':(['T-001','T-007','T-009'].includes(id)||(task_id==='T-006'&&id==='T-003'))?'DONE':'READY',depends_on:c?.deps??[],allowed_paths:c?.scopes??[],claim:id===task_id?{claim_id,worker_id:'chat-A',actor}:null,...(id===task_id?{pr_number:271,head_sha:HEAD}:{})}}),
  processed_requests:[{request_id:submitId,fingerprint:'a'.repeat(64),actor,receipt:{type:'submit',task_id,request_id:submitId,version,status:'IN_REVIEW',replayed:false}}]}
 const proof={historical271:true,actorId:123868412,sourceIssue:999,stateSha,expectedStateSha:stateSha,expectedVersion:version,note:command.note}
 const routes={},put=(p,v)=>routes[ROOT+p]=v
 put('/branches/main',{name:'main',protected:true,commit:{sha:mainSha}})
 put('/branches/'+encodeURIComponent(TARGET),{name:TARGET,protected:true,commit:{sha:integrationDefault}})
 for(const ref of [mainSha,integrationDefault])put('/compare/'+MERGE+'...'+ref,{status:'ahead',behind_by:0,base_commit:{sha:MERGE},merge_base_commit:{sha:MERGE},commits:[]})
 put('/pulls/271',{number:271,state:'closed',merged:true,merged_at:'2026-11-22T03:07:20Z',merge_commit_sha:MERGE,user:{id:123868412},merged_by:{id:123868412},base:{ref:'main',sha:BASE,repo},head:{ref:SOURCE,sha:HEAD,repo},changed_files:70})
 const files=Object.assign({},...Object.values(TASKS).map(t=>t.files))
 put('/pulls/271/files?per_page=100',[...Object.entries(files).map(([filename,sha])=>({filename,sha,status:'added'})),...Array.from({length:70-Object.keys(files).length},(_,i)=>({filename:'other/file-'+i,sha:'d'.repeat(40),status:'modified'}))])
 for(const [path,sha] of Object.entries(files))for(const ref of [HEAD,TEST,MERGE,mainSha,integrationDefault])put('/contents/'+path+'?ref='+ref,{type:'file',path,sha})
 for(const [path,sha] of Object.entries(workflows))for(const ref of [HEAD,TEST,MERGE])put('/contents/'+path+'?ref='+ref,{type:'file',path,sha})
 put('/git/commits/'+MERGE,{sha:MERGE,tree:{sha:TREE},parents:[{sha:BASE}]})
 put('/git/commits/'+TEST,{sha:TEST,tree:{sha:TREE},parents:[{sha:BASE},{sha:HEAD}]})
 const allChecks=[]
 for(const [id,name,path,attempt,count] of runs){
  put('/actions/runs/'+id,{id,name,path,run_attempt:attempt,event:'pull_request',status:'completed',conclusion:'success',head_sha:HEAD,head_branch:SOURCE,repository:repo,head_repository:repo,created_at:'2026-11-22T01:50:00Z',updated_at:'2026-11-22T03:06:44Z',pull_requests:[]})
  const own=jobs.filter(j=>j[1]===id),entries=[...own,...Array.from({length:count-own.length},(_,i)=>['extra-'+i,id,1000+i])]
  const list=entries.map(([n,run_id,jobId])=>{
   const action=id===44973283672?'v4':PIN,resolved=action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':PIN
   allChecks.push({name:n,id:jobId,head_sha:HEAD,status:'completed',conclusion:'success',app:{id:15368,slug:'github-actions'},details_url:'https://github.com/'+REPO+'/actions/runs/'+id+'/job/'+jobId})
   put('/actions/jobs/'+jobId+'/logs',[
    "2026-11-22T02:00:00Z Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")",
    '2026-11-22T02:00:01Z ##[group]Run actions/checkout@'+action,
    '2026-11-22T02:00:02Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags origin +'+TEST+':refs/remotes/pull/271/merge',
    '2026-11-22T02:00:03Z [command]/usr/bin/git checkout --progress --force refs/remotes/pull/271/merge',
    '2026-11-22T02:00:04Z [command]/usr/bin/git log -1 --format=%H',
    '2026-11-22T02:00:05Z '+TEST,'2026-11-22T02:00:08Z ##[group]Run tests'].join('\n'))
   return {name:n,id:jobId,run_id,run_attempt:attempt,head_sha:HEAD,head_branch:SOURCE,workflow_name:name,status:'completed',conclusion:'success',started_at:'2026-11-22T01:59:59Z',completed_at:'2026-11-22T03:06:43Z',
    steps:[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+action,conclusion:'success',started_at:'2026-11-22T02:00:01Z',completed_at:'2026-11-22T02:00:06Z'}]}
  })
  put('/actions/runs/'+id+'/jobs?per_page=100&filter=latest',{total_count:count,jobs:list})
 }
 put('/commits/'+HEAD+'/check-runs?per_page=100&filter=latest',{total_count:36,check_runs:allChecks})
 put('/actions/runs/44979169937',{id:44979169937,name:'CI',path:CI,event:'push',status:'completed',conclusion:'success',head_branch:'main',head_sha:MERGE,run_attempt:3,repository:repo,head_repository:repo,created_at:'2026-11-22T03:07:23Z',updated_at:'2026-11-22T03:17:23Z'})
 put('/actions/runs/44979169937/jobs?per_page=100&filter=latest',{total_count:34,jobs:Array.from({length:34},(_,i)=>({id:2000+i,status:'completed',conclusion:'success',run_id:44979169937,head_sha:MERGE,head_branch:'main',workflow_name:'CI'}))})
 const api=key=>{assert.ok(Object.hasOwn(routes,key),'unexpected route '+key);return structuredClone(routes[key])}
 return {snapshot,command,proof,routes,api,mainSha,HEAD,request_id,claim_id}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 test('three #271 task projections verify full original CI, exact tested tree and current fifteen blobs without new PR',()=>{
  for(const task of ['T-002','T-003','T-006']){
   const f=historical271Fixture(task)
   assert.equal(verifyHistorical271(f.snapshot,f.command,f.proof,f.mainSha,f.api).task,task)
  }
 })
 test('historical #271 rejects wrong task, claim, version, scope, dependency and missing submitted evidence',()=>{
  for(const mutate of [f=>f.command.task_id='T-004',f=>f.command.claim_id='bad',f=>f.proof.expectedVersion++,f=>f.proof.stateSha='f'.repeat(40),
   f=>f.snapshot.tasks[2].allowed_paths.push('app/other.mjs'),f=>f.snapshot.tasks[6].status='READY',f=>f.snapshot.processed_requests=[]]){
   const f=historical271Fixture();mutate(f)
   assert.throws(()=>verifyHistorical271Binding(f.snapshot,f.command,f.proof))
  }
 })
 test('T-006 rejects missing T-003 completion, old revision and every changed board/projection blob',()=>{
  const f=historical271Fixture('T-006')
  f.snapshot.tasks[2].status='READY'
  assert.throws(()=>verifyHistorical271Binding(f.snapshot,f.command,f.proof),/HISTORICAL_271_SCOPE_OR_DEPENDENCY/)
  const old=historical271Fixture('T-006')
  old.snapshot.version=32;old.proof.expectedVersion=32;old.snapshot.processed_requests[0].receipt.version=32
  assert.throws(()=>verifyHistorical271Binding(old.snapshot,old.command,old.proof),/HISTORICAL_271_BINDING/)
  for(const path of Object.keys(TASKS['T-006'].files)){
   const q=historical271Fixture('T-006')
   q.routes[ROOT+'/contents/'+path+'?ref='+q.mainSha].sha='f'.repeat(40)
   assert.throws(()=>verifyHistorical271(q.snapshot,q.command,q.proof,q.mainSha,q.api),/HISTORICAL_271_BLOB_DRIFT/)
  }
 })
 test('historical #271 rejects current blob drift, ancestor loss, scope smuggling, checkout drift, failed jobs and altered trees',()=>{
  for(const mutate of [
   f=>f.routes[ROOT+'/contents/app/scripts/dev-collab/coordinator-cli.mjs?ref='+f.mainSha].sha='f'.repeat(40),
   f=>f.routes[ROOT+'/compare/'+MERGE+'...'+integrationDefault].behind_by=1,
   f=>f.routes[ROOT+'/branches/'+encodeURIComponent(TARGET)].protected=false,
   f=>f.routes[ROOT+'/pulls/271'].base.ref=TARGET,
   f=>f.routes[ROOT+'/pulls/271/files?per_page=100'][3].sha='f'.repeat(40),
   f=>f.routes[ROOT+'/actions/jobs/137075248547/logs']=f.routes[ROOT+'/actions/jobs/137075248547/logs'].replaceAll(TEST,'f'.repeat(40)),
   f=>f.routes[ROOT+'/actions/runs/44973283672/jobs?per_page=100&filter=latest'].jobs[0].conclusion='failure',
   f=>f.routes[ROOT+'/git/commits/'+TEST].tree.sha='f'.repeat(40),
   f=>f.routes[ROOT+'/actions/runs/44979169937/jobs?per_page=100&filter=latest'].jobs[0].conclusion='failure',
   f=>f.routes[ROOT+'/actions/runs/44973283492'].pull_requests=[{number:999}]
  ]){
   const f=historical271Fixture();mutate(f);assert.throws(()=>verifyHistorical271(f.snapshot,f.command,f.proof,f.mainSha,f.api))
  }
  const f=historical271Fixture('T-002');f.routes[ROOT+'/pulls/271/files?per_page=100'][6].filename='.github/ISSUE_TEMPLATE/extra.yml'
  assert.throws(()=>verifyHistorical271(f.snapshot,f.command,f.proof,f.mainSha,f.api),/HISTORICAL_271_FILE_SCOPE/)
 })
}
