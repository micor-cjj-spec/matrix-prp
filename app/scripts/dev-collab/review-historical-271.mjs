// Narrow historical reuse of the already-landed #271 bootstrap; no generic fallback.
import {CollabError,validateSnapshot} from './core.mjs'
import {REQUIRED_CHECKS,hasDevAncestry,verifySquashRelease} from './review-gate.mjs'
import {verifyInitialReviewCheckout} from './review-provenance.mjs'

export const HISTORICAL_271_PREFIX='PRP_HISTORICAL_271_V1:'
const REPO='micor-cjj-spec/matrix-prp',ROOT='repos/'+REPO,REPO_ID=1261866723,OWNER_ID=123868412
const REQ='REQ-20261031-001',TARGET='integrate/'+REQ
const HEAD='48b3a69232690e7e2fb54a2d92efac02cc512c0e',BASE='3ada1c20d2b9378f8dff6e4bab9c5735d162b8b4'
const MERGE='3177009eeb692c766715ba0c6e1133844f469981',TEST='4e6e0a6deda745e170c89fae51a0c115621622f9'
const TREE='e5fb9857635bc91946ebcf6b97dececd0177e592',MERGED_AT='2026-11-22T03:07:20Z'
const SOURCE=TARGET+'-solo-collab-only-20261122',PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
const SHA=/^[a-f0-9]{40}$/,UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
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
const WORKFLOW_BLOBS={
 [CI]:'695b53214437053943908217ab855b069dd30a24',
 [IMPACT]:'ce48ed0e167509e60b04d50c4c9493a705096b52',
 [CONTRACT]:'b00af8f8c53ba88fa62d873d1543b0bddfe96880'}
const RUNS={
 44973283672:{name:'CI',path:CI,attempt:2,count:34},
 44973283492:{name:'PRP Dev Collaboration Contract',path:CONTRACT,attempt:1,count:1},
 44973284191:{name:'Feature Impact Report',path:IMPACT,attempt:1,count:1}}
const JOBS={
 'backend-tests':[44973283672,137075248547],
 'web-build':[44973283672,137075225050],
 'mobile-build':[44973283672,137075225377],
 'db-migration-integration':[44973283672,137075224308],
 'video-db-integration':[44973283672,137075255279],
 'impact-report':[44973284191,137057508098],
 'dev-collab-contract':[44973283492,137057505664]}
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const time=v=>typeof v==='string'?Date.parse(v):NaN
const repo=v=>v?.id===REPO_ID&&v.full_name===REPO
const equalSet=(a,b)=>Array.isArray(a)&&a.length===b.length&&new Set(a).size===a.length&&a.every(x=>b.includes(x))
const complete=(v,key,count)=>v?.total_count===count&&Array.isArray(v[key])&&v[key].length===count
const green=j=>j?.status==='completed'&&j.conclusion==='success'

export function verifyHistorical271Binding(snapshot,command,proof){
 validateSnapshot(snapshot)
 const t=snapshot.tasks.find(x=>x.task_id===command.task_id),cfg=Object.hasOwn(TASKS,command.task_id)?TASKS[command.task_id]:null
 check(cfg&&proof?.historical271===true&&proof.actorId===OWNER_ID&&Number.isSafeInteger(proof.sourceIssue)&&proof.sourceIssue>0&&
  SHA.test(proof.stateSha||'')&&proof.stateSha===proof.expectedStateSha&&proof.expectedVersion===snapshot.version&&snapshot.version>=(command.task_id==='T-006'?33:25)&&
  snapshot.requirement_id===REQ&&snapshot.status==='ACTIVE'&&command.type==='accept'&&command.requirement_id===REQ&&
  UUID.test(command.request_id)&&command.note===proof.note&&command.note?.startsWith(HISTORICAL_271_PREFIX)&&
  command.pr_number===271&&command.head_sha===HEAD&&t?.status==='IN_REVIEW'&&t.pr_number===271&&t.head_sha===HEAD&&
  t.claim?.actor==='micor-cjj-spec'&&t.claim.claim_id===command.claim_id&&t.claim.worker_id===command.worker_id,
  'HISTORICAL_271_BINDING')
 check(equalSet(t.allowed_paths,cfg.scopes)&&equalSet(t.depends_on,cfg.deps)&&cfg.deps.every(id=>snapshot.tasks.some(x=>x.task_id===id&&x.status==='DONE')),'HISTORICAL_271_SCOPE_OR_DEPENDENCY')
 const last=snapshot.processed_requests.filter(x=>x.receipt.task_id===t.task_id).at(-1)
 check(last?.actor===t.claim.actor&&last.receipt.type==='submit'&&last.receipt.status==='IN_REVIEW'&&
  last.receipt.request_id===last.request_id&&last.receipt.version>=25&&last.receipt.version<=snapshot.version,'HISTORICAL_271_SUBMIT')
 return cfg
}

export function verifyHistorical271(snapshot,command,proof,mainSha,api){
 const cfg=verifyHistorical271Binding(snapshot,command,proof)
 const get=p=>api(ROOT+p)
 const main=get('/branches/main'),integration=get('/branches/'+encodeURIComponent(TARGET))
 check(SHA.test(mainSha)&&main?.name==='main'&&main.protected===true&&main.commit?.sha===mainSha&&
  integration?.name===TARGET&&integration.protected===true&&SHA.test(integration.commit?.sha||''),'HISTORICAL_271_PROTECTED_REFS')
 for(const ref of [mainSha,integration.commit.sha])
  check(hasDevAncestry(get('/compare/'+MERGE+'...'+ref),MERGE),'HISTORICAL_271_ANCESTRY')
 const p=get('/pulls/271')
 check(p?.number===271&&p.state==='closed'&&p.merged===true&&p.merged_at===MERGED_AT&&p.merge_commit_sha===MERGE&&
  p.user?.id===OWNER_ID&&p.merged_by?.id===OWNER_ID&&p.base?.ref==='main'&&p.base.sha===BASE&&repo(p.base.repo)&&
  p.head?.ref===SOURCE&&p.head.sha===HEAD&&repo(p.head.repo)&&p.changed_files===70,'HISTORICAL_271_PR')
 const files=get('/pulls/271/files?per_page=100')
 check(Array.isArray(files)&&files.length===70&&new Set(files.map(f=>f.filename)).size===70&&
  files.every(f=>typeof f.filename==='string'&&f.status!=='renamed'),'HISTORICAL_271_FILE_LIST')
 // Project only the exact reviewed task paths from the bootstrap; never pass the
 // multi-task PR to the ordinary task scope verifier or allow additional paths.
 const inScope=path=>cfg.scopes.some(s=>s.endsWith('/')?path.startsWith(s):path===s)
 const selected=files.filter(f=>inScope(f.filename))
 check(equalSet(selected.map(f=>f.filename),Object.keys(cfg.files))&&
  selected.every(f=>f.status==='added'&&f.sha===cfg.files[f.filename]),'HISTORICAL_271_FILE_SCOPE')
 const blob=(path,ref,expected)=>{
  const v=get('/contents/'+path+'?ref='+ref)
  check(v?.type==='file'&&v.path===path&&v.sha===expected,'HISTORICAL_271_BLOB_DRIFT')
  return v.sha
 }
 for(const [path,sha] of Object.entries(cfg.files))
  for(const ref of [HEAD,TEST,MERGE,mainSha,integration.commit.sha])blob(path,ref,sha)
 const checks=get('/commits/'+HEAD+'/check-runs?per_page=100&filter=latest')
 check(complete(checks,'check_runs',36)&&checks.check_runs.every(c=>green(c)&&c.head_sha===HEAD&&c.app?.id===15368&&c.app?.slug==='github-actions'),'HISTORICAL_271_CHECKS')
 const listings={}
 for(const [key,spec] of Object.entries(RUNS)){
  const id=Number(key),run=get('/actions/runs/'+id)
  check(run?.id===id&&run.name===spec.name&&run.path===spec.path&&run.run_attempt===spec.attempt&&
   run.event==='pull_request'&&green(run)&&run.head_sha===HEAD&&run.head_branch===SOURCE&&repo(run.repository)&&repo(run.head_repository)&&
   time(run.created_at)<=time(run.updated_at)&&time(run.updated_at)<time(MERGED_AT)&&Array.isArray(run.pull_requests)&&
   (run.pull_requests.length===0||run.pull_requests.length===1&&run.pull_requests.every(q=>q.number===271&&q.head?.sha===HEAD&&q.head?.ref===SOURCE&&q.head?.repo?.id===REPO_ID&&q.base?.ref==='main'&&q.base?.sha===BASE&&q.base?.repo?.id===REPO_ID)),
   'HISTORICAL_271_RUN')
  const list=get('/actions/runs/'+id+'/jobs?per_page=100&filter=latest')
  check(complete(list,'jobs',spec.count)&&list.jobs.every(j=>green(j)&&j.run_id===id&&j.head_sha===HEAD&&j.run_attempt===spec.attempt&&
   j.head_branch===SOURCE&&j.workflow_name===spec.name&&time(j.started_at)>=time(run.created_at)&&time(j.started_at)<=time(j.completed_at)&&time(j.completed_at)<time(MERGED_AT)),'HISTORICAL_271_JOBS')
  listings[id]=list.jobs
 }
 const checkouts=REQUIRED_CHECKS.map(name=>{
  const [runId,jobId]=JOBS[name],matches=checks.check_runs.filter(c=>c.name===name)
  check(matches.length===1&&matches[0].id===jobId&&matches[0].details_url==='https://github.com/'+REPO+'/actions/runs/'+runId+'/job/'+jobId,'HISTORICAL_271_CHECK_ID')
  const jobs=listings[runId].filter(j=>j.name===name)
  check(jobs.length===1&&jobs[0].id===jobId,'HISTORICAL_271_JOB_ID')
  const sha=verifyInitialReviewCheckout(get('/actions/jobs/'+jobId+'/logs'),jobs[0],271,runId===44973283672?'v4':PIN)
  check(sha===TEST,'HISTORICAL_271_CHECKOUT')
  return {name,jobId,sha}
 })
 const mergeCommit=get('/git/commits/'+MERGE),testCommit=get('/git/commits/'+TEST)
 check(testCommit?.sha===TEST&&mergeCommit?.tree?.sha===TREE,'HISTORICAL_271_TREE')
 const workflowBlobs=Object.fromEntries(Object.entries(WORKFLOW_BLOBS).map(([path,sha])=>[path,[HEAD,TEST,MERGE].map(ref=>blob(path,ref,sha))]))
 // #271 introduced these workflows; compare tested head, synthetic and actual
 // squash, not the pre-bootstrap base which legitimately lacked/changed them.
 verifySquashRelease(p,command,{mergeCommit,testCommit,checkouts,workflowBlobs})
 const post=get('/actions/runs/44979169937')
 check(post?.id===44979169937&&post.name==='CI'&&post.path===CI&&post.event==='push'&&green(post)&&
  post.head_branch==='main'&&post.head_sha===MERGE&&post.run_attempt===3&&repo(post.repository)&&repo(post.head_repository)&&
  time(post.created_at)>time(MERGED_AT)&&time(post.created_at)<=time(post.updated_at),'HISTORICAL_271_POST_RUN')
 const postJobs=get('/actions/runs/44979169937/jobs?per_page=100&filter=latest')
 check(complete(postJobs,'jobs',34)&&postJobs.jobs.every(j=>green(j)&&j.run_id===post.id&&j.head_sha===MERGE&&j.head_branch==='main'&&j.workflow_name==='CI'),'HISTORICAL_271_POST_JOBS')
 return Object.freeze({historical271Verified:true,pr:271,head:HEAD,merge:MERGE,task:command.task_id,checks:7})
}
