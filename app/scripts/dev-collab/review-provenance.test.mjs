import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyWorkflowProvenance, readReviewJobLog, HISTORICAL_529_PREFIX, verifyHistorical529Binding, collectHistorical529, verifyHistorical529Evidence } from './review-provenance.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'
const sha='a'.repeat(40),baseRef='integrate/REQ-20261031-001',headRef='feat/REQ-20261031-001/T-001'
const repo='micor-cjj-spec/matrix-prp',number=138
const jobs=()=>({total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
 name,id:1001+i,head_sha:sha,status:'completed',conclusion:'success',app:{slug:'github-actions',id:15368},
 details_url:`https://github.com/${repo}/actions/runs/${name==='impact-report'?102:name==='dev-collab-contract'?103:101}/job/${1001+i}`
}))})
const run = (id,branch=headRef,base=baseRef)=> {
 const map={101:['CI','.github/workflows/ci.yml'],102:['Feature Impact Report','.github/workflows/feature-impact.yml'],
  103:['PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']}
 const [name,path]=map[id]
 return {id,name,path,run_attempt:2,created_at:'2026-10-31T17:00:00Z',event:'pull_request',status:'completed',conclusion:'success',head_sha:sha,
  head_branch:branch,repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},
  pull_requests:[{number,head:{sha,ref:branch},base:{ref:base}}]}
}
const list=(id,branch=headRef,base=baseRef)=>{const jobsForRun=jobs().check_runs.filter(c=>c.details_url.includes('/runs/'+id+'/')).map(c=>({name:c.name,id:c.id,run_id:id,run_attempt:1,head_sha:sha,head_branch:branch,workflow_name:run(id,branch,base).name,status:'completed',conclusion:'success',started_at:'2026-10-31T17:01:00Z',completed_at:'2026-10-31T17:59:00Z'}));return {total_count:jobsForRun.length,jobs:jobsForRun}}
const verify=(data,resolver=run,jobLoader=list,overrides={})=>verifyWorkflowProvenance(data,{sha,prNumber:number,baseRef,headRef,mergedAt:'2026-10-31T18:00:00Z',...overrides},resolver,jobLoader)
const fails=(f,code)=>assert.throws(f,e=>e.code===code)
test('requires three correct signed workflow identities and precise PR provenance',()=>{
 const r=verify(jobs());assert.deepEqual(r.workflow_runs,[101,102,103])
})
test('a same-named green check from different GitHub Actions workflow is denied',()=>{
 const x=jobs()
 x.check_runs[0].details_url=`https://github.com/${repo}/actions/runs/104/job/1001`
 fails(()=>verify(x,id=>id===104?{...run(101),name:'Fake CI',path:'.github/workflows/fake.yml'}:run(id)),
  'WRONG_CHECK_WORKFLOW_backend-tests')
})
test('a successful workflow_dispatch cannot impersonate PR checks',()=>{
 const x=jobs()
 fails(()=>verify(x,id=>id===101?{...run(id),event:'workflow_dispatch'}:run(id)),
  'WRONG_WORKFLOW_ORIGIN_backend-tests')
})
test('green checks on unrelated PR cannot pass',()=>{
 const x=jobs()
 fails(()=>verify(x,id=>({...run(id),pull_requests:[{number:999,head:{sha},base:{ref:baseRef}}]})),
  'WORKFLOW_PR_MISMATCH_backend-tests')
})
test('forged check URL or mismatched job ID is not accepted',()=>{
 const x=jobs();x.check_runs[0].details_url='https://evil.example/actions/runs/101/job/1001'
 fails(()=>verify(x),'UNTRUSTED_CHECK_DETAILS_backend-tests')
 const y=jobs();y.check_runs[0].details_url=`https://github.com/${repo}/actions/runs/101/job/9999`
 fails(()=>verify(y),'UNTRUSTED_CHECK_DETAILS_backend-tests')
})
test('a newer failed authorized check cannot be obscured by an older green one',()=>{
 const x=jobs();x.check_runs.push({...x.check_runs[0],id:9999,conclusion:'failure',
  details_url:`https://github.com/${repo}/actions/runs/101/job/9999`});x.total_count++
 fails(()=>verify(x),'CHECK_NOT_GREEN_backend-tests')
})


test('a newer same-HEAD dev push check cannot shadow the exact PR check',()=>{
 const x=jobs()
 x.check_runs.push({...x.check_runs[0],id:9999,
  details_url:'https://github.com/'+repo+'/actions/runs/104/job/9999'})
 x.total_count++
 const pushRun={...run(101,'dev','main'),id:104,event:'push',pull_requests:[]}
 const result=verify(x,id=>id===104?pushRun:run(id,'dev','main'),id=>list(id,'dev','main'),{headRef:'dev',baseRef:'main'})
 assert.deepEqual(result.workflow_runs,[101,102,103])
})
test('same-HEAD dev push checks alone remain rejected as non-PR evidence',()=>{
 const x=jobs()
 const backend=x.check_runs[0]
 x.check_runs=x.check_runs.filter(c=>c.name!=='backend-tests')
 x.check_runs.push({...backend,id:9999,
  details_url:'https://github.com/'+repo+'/actions/runs/104/job/9999'})
 x.total_count=x.check_runs.length
 const pushRun={...run(101,'dev','main'),id:104,event:'push',pull_requests:[]}
 fails(()=>verify(x,id=>id===104?pushRun:run(id,'dev','main'),id=>list(id,'dev','main'),{headRef:'dev',baseRef:'main'}),'WRONG_WORKFLOW_ORIGIN_backend-tests')
})
test('same-HEAD non-dev push checks are not excluded from task-branch provenance',()=>{
 const x=jobs()
 x.check_runs.push({...x.check_runs[0],id:9999,
  details_url:'https://github.com/'+repo+'/actions/runs/104/job/9999'})
 x.total_count++
 const pushRun={...run(101),id:104,event:'push',pull_requests:[]}
 fails(()=>verify(x,id=>id===104?pushRun:run(id)),'WRONG_WORKFLOW_ORIGIN_backend-tests')
})
test('redacted or multiple PR associations never authorize ordinary provenance',()=>{
 for(const pr of [[],[{number,head:{sha},base:{ref:baseRef}},{number:999,head:{sha},base:{ref:baseRef}}]])fails(()=>verify(jobs(),id=>({...run(id),pull_requests:pr})),'WORKFLOW_PR_MISMATCH_backend-tests')
})
test('latest workflow jobs must bind exact check ID, workflow, repo, SHA and attempt',()=>{
 for(const mutate of [j=>j.run_id=999,j=>j.head_sha='b'.repeat(40),j=>j.workflow_name='Fake',j=>j.run_attempt=3,j=>j.run_attempt=0,j=>j.conclusion='failure',j=>j.head_branch='other']){
  fails(()=>verify(jobs(),run,id=>{const l=list(id);if(id===101)mutate(l.jobs[0]);return l}), 'WORKFLOW_JOB_MISMATCH_backend-tests')
 }
 fails(()=>verify(jobs(),run,id=>{const l=list(id);l.jobs[0].id=999;return l}),'AMBIGUOUS_WORKFLOW_JOB_backend-tests')
 const bad=jobs();bad.check_runs[0].app.id=1;fails(()=>verify(bad),'WRONG_CHECK_APP_backend-tests')
})
test('job-list omissions, duplicate names and post-merge reruns fail closed',()=>{
 fails(()=>verify(jobs(),run,id=>{const l=list(id);l.total_count++;return l}),'INCOMPLETE_WORKFLOW_JOBS_backend-tests')
 fails(()=>verify(jobs(),run,id=>{const l=list(id);l.jobs.push({...l.jobs[0],id:999});l.total_count++;return l}),'AMBIGUOUS_WORKFLOW_JOB_backend-tests')
 fails(()=>verify(jobs(),run,id=>{const l=list(id);l.jobs[0].completed_at='2026-10-31T18:01:00Z';return l}),'WORKFLOW_JOB_TIME_MISMATCH_backend-tests')
})

test('log download accepts only validated repository route, strips authorization on redirect',async()=>{
 const route='repos/micor-cjj-spec/matrix-prp/actions/jobs/123/logs'
 const calls=[]
 const log=await readReviewJobLog(route,{token:'synthetic',fetcher:async (url,opts)=>{
   calls.push({url:String(url),opts})
   if(calls.length===1)return new Response(null,{status:302,headers:{location:'https://logs.blob.core.windows.net/archive?signature=synthetic'}})
   return new Response('checkout log')
 }})
 assert.equal(log,'checkout log')
 assert.equal(calls[0].opts.headers.Authorization,'Bearer synthetic')
 assert.equal(calls[1].opts.headers,undefined);assert.equal(calls[1].opts.redirect,'manual')
 await assert.rejects(readReviewJobLog('repos/evil/repo/actions/jobs/123/logs',{token:'synthetic',fetcher:()=>{throw Error('unexpected fetch')}}),e=>e.code==='REVIEW_LOG_REQUEST')
 await assert.rejects(readReviewJobLog(route,{token:'synthetic',fetcher:async()=>new Response(null,{status:302,headers:{location:'https://evil.example/log'}})}),e=>e.code==='REVIEW_LOG_REDIRECT')
})


const h529={
 base:'edd6d76b6c803ea5734f40fc1350ea3b29018562',
 head:'4397169413cd1c43844c7ac21fddc3016e5dfcba',
 merge:'c567761ee555e8d4ec9fa120468a74d8dae97fa8',
 test:'ed2952343acf7c3f151b4380589dcda60ac5fa18',
 tree:'1f9721e95c1d4d3029ae1b8c4c18efbdce551a0a',
 mergedAt:'2026-11-27T10:48:31Z',
 ci:'.github/workflows/ci.yml',
 impact:'.github/workflows/feature-impact.yml',
 contract:'.github/workflows/prp-dev-collab-contract.yml'
}
const h529Entries=[
 {name:'backend-tests',id:140448213160,run:45980919751,attempt:2,path:h529.ci,workflow:'CI',action:'v4',stepStart:'2026-11-27T10:19:24Z',stepEnd:'2026-11-27T10:19:26Z',jobStart:'2026-11-27T10:19:23Z',jobEnd:'2026-11-27T10:20:42Z',download:'2026-11-27T10:19:24.0091664Z',group:'2026-11-27T10:19:24.4924058Z',fetch:'2026-11-27T10:19:24.9833520Z',checkout:'2026-11-27T10:19:25.4299167Z',hash:'2026-11-27T10:19:26.0691903Z',output:'2026-11-27T10:19:26.0718311Z',end:'2026-11-27T10:19:26.1131081Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge'},
 {name:'web-build',id:140448215660,run:45980919751,attempt:2,path:h529.ci,workflow:'CI',action:'v4',stepStart:'2026-11-27T10:18:50Z',stepEnd:'2026-11-27T10:18:51Z',jobStart:'2026-11-27T10:18:49Z',jobEnd:'2026-11-27T10:19:25Z',download:'2026-11-27T10:18:50.0352659Z',group:'2026-11-27T10:18:50.4722269Z',fetch:'2026-11-27T10:18:50.7858363Z',checkout:'2026-11-27T10:18:51.4565032Z',hash:'2026-11-27T10:18:51.6036618Z',output:'2026-11-27T10:18:51.6057749Z',end:'2026-11-27T10:18:51.6454560Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge'},
 {name:'mobile-build',id:140448203693,run:45980919751,attempt:2,path:h529.ci,workflow:'CI',action:'v4',stepStart:'2026-11-27T10:18:55Z',stepEnd:'2026-11-27T10:18:57Z',jobStart:'2026-11-27T10:18:54Z',jobEnd:'2026-11-27T10:19:22Z',download:'2026-11-27T10:18:55.4348197Z',group:'2026-11-27T10:18:55.7828039Z',fetch:'2026-11-27T10:18:56.1770937Z',checkout:'2026-11-27T10:18:56.7210578Z',hash:'2026-11-27T10:18:57.2346294Z',output:'2026-11-27T10:18:57.2365003Z',end:'2026-11-27T10:18:57.2786540Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge'},
 {name:'db-migration-integration',id:140448233338,run:45980919751,attempt:2,path:h529.ci,workflow:'CI',action:'v4',stepStart:'2026-11-27T10:20:26Z',stepEnd:'2026-11-27T10:20:29Z',jobStart:'2026-11-27T10:19:59Z',jobEnd:'2026-11-27T10:21:11Z',download:'2026-11-27T10:20:00.3963452Z',group:'2026-11-27T10:20:26.9063294Z',fetch:'2026-11-27T10:20:27.7491797Z',checkout:'2026-11-27T10:20:28.4760842Z',hash:'2026-11-27T10:20:29.0848424Z',output:'2026-11-27T10:20:29.0866823Z',end:'2026-11-27T10:20:29.1066883Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge',initialize:true},
 {name:'video-db-integration',id:140448231019,run:45980919751,attempt:2,path:h529.ci,workflow:'CI',action:'v4',stepStart:'2026-11-27T10:20:15Z',stepEnd:'2026-11-27T10:20:16Z',jobStart:'2026-11-27T10:19:49Z',jobEnd:'2026-11-27T10:21:31Z',download:'2026-11-27T10:19:50.3793635Z',group:'2026-11-27T10:20:15.0969494Z',fetch:'2026-11-27T10:20:15.5897155Z',checkout:'2026-11-27T10:20:16.0187320Z',hash:'2026-11-27T10:20:16.6683517Z',output:'2026-11-27T10:20:16.6719472Z',end:'2026-11-27T10:20:16.7041731Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge',initialize:true},
 {name:'impact-report',id:140444287659,run:45980919689,attempt:1,path:h529.impact,workflow:'Feature Impact Report',action:'3d3c42e5aac5ba805825da76410c181273ba90b1',stepStart:'2026-11-27T10:18:26Z',stepEnd:'2026-11-27T10:18:28Z',jobStart:'2026-11-27T10:18:25Z',jobEnd:'2026-11-27T10:18:34Z',download:'2026-11-27T10:18:26.1803172Z',group:'2026-11-27T10:18:26.7013943Z',fetch:'2026-11-27T10:18:27.1345047Z',checkout:'2026-11-27T10:18:27.9961586Z',hash:'2026-11-27T10:18:28.4876845Z',output:'2026-11-27T10:18:28.4904067Z',end:'2026-11-27T10:18:28.6368037Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules origin +refs/heads/*:refs/remotes/origin/* +refs/tags/*:refs/tags/* +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge'},
 {name:'dev-collab-contract',id:140444288158,run:45980919800,attempt:1,path:h529.contract,workflow:'PRP Dev Collaboration Contract',action:'3d3c42e5aac5ba805825da76410c181273ba90b1',stepStart:'2026-11-27T10:18:16Z',stepEnd:'2026-11-27T10:18:22Z',jobStart:'2026-11-27T10:18:14Z',jobEnd:'2026-11-27T10:18:58Z',download:'2026-11-27T10:18:15.2535956Z',group:'2026-11-27T10:18:16.8028226Z',fetch:'2026-11-27T10:18:20.6465127Z',checkout:'2026-11-27T10:18:21.5855906Z',hash:'2026-11-27T10:18:22.5165062Z',output:'2026-11-27T10:18:22.5184596Z',end:'2026-11-27T10:18:22.6225395Z',fetchLine:'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=2 origin +ed2952343acf7c3f151b4380589dcda60ac5fa18:refs/remotes/pull/529/merge'}
]
const h529Files=[
 ['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md','added'],
 ['app/docs/dev-collab/OPERATIONS.md','modified'],
 ['app/scripts/dev-collab/core.mjs','modified'],
 ['app/scripts/dev-collab/core.test.mjs','modified'],
 ['app/scripts/dev-collab/integration-ci-boundary.test.mjs','modified'],
 ['app/scripts/dev-collab/recovery.mjs','modified'],
 ['app/scripts/dev-collab/recovery.test.mjs','modified']
]
const h529BlobMap={
 '.github/workflows/ci.yml':'2e8ded58e20cf540c033365ed266d0e2045309b6',
 '.github/workflows/feature-impact.yml':'5a64a9e728f4bb6dd0fc91bb0393b2cca74ae302',
 '.github/workflows/prp-dev-collab-contract.yml':'c1373ee788d3469aea37624328f4e53e66a68f9c'
}
function h529Log(x){
 const resolved=x.action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':x.action
 return [
  x.download+" Download action repository 'actions/checkout@"+x.action+"' (SHA:"+resolved+")",
  x.group+" ##[group]Run actions/checkout@"+x.action,
  x.fetch+" "+x.fetchLine,
  x.checkout+" [command]/usr/bin/git checkout --progress --force refs/remotes/pull/529/merge",
  x.hash+" [command]/usr/bin/git log -1 --format=%H",
  x.output+" "+h529.test,
  x.end+" ##[group]Run "+(x.name==='impact-report'?'actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1':x.name==='dev-collab-contract'?'actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1':'next-step')
 ].join('\n')
}
function h529Fixture(){
 const runs={
  45980919751:{id:45980919751,name:'CI',path:h529.ci,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:2,created_at:'2026-11-27T10:18:02Z',repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},pull_requests:[]},
  45980919689:{id:45980919689,name:'Feature Impact Report',path:h529.impact,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:1,created_at:'2026-11-27T10:18:02Z',repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},pull_requests:[]},
  45980919800:{id:45980919800,name:'PRP Dev Collaboration Contract',path:h529.contract,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:1,created_at:'2026-11-27T10:18:02Z',repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},pull_requests:[]}
 }
 const jobs={},logs={},checkRuns=[]
 for(const x of h529Entries){
  const steps=[{name:'Set up job',conclusion:'success'}]
  if(x.initialize)steps.push({name:'Initialize containers',conclusion:'success'})
  steps.push({name:'Run actions/checkout@'+x.action,conclusion:'success',started_at:x.stepStart,completed_at:x.stepEnd})
  const job={name:x.name,id:x.id,run_id:x.run,run_attempt:x.attempt,head_sha:h529.head,head_branch:'dev',workflow_name:x.workflow,status:'completed',conclusion:'success',started_at:x.jobStart,completed_at:x.jobEnd,steps}
  if(!jobs[x.run])jobs[x.run]={total_count:0,jobs:[]}
  jobs[x.run].jobs.push(job);jobs[x.run].total_count++
  logs[x.id]=h529Log(x)
  checkRuns.push({name:x.name,id:x.id,head_sha:h529.head,status:'completed',conclusion:'success',app:{slug:'github-actions',id:15368},details_url:'https://github.com/'+repo+'/actions/runs/'+x.run+'/job/'+x.id,started_at:x.jobStart,completed_at:x.jobEnd})
 }
 return {
  pr:{number:529,state:'closed',merged:true,draft:false,merge_commit_sha:h529.merge,merged_at:h529.mergedAt,changed_files:7,
   base:{ref:'main',sha:h529.base,repo:{full_name:repo,id:1261866723}},
   head:{ref:'dev',sha:h529.head,repo:{full_name:repo,id:1261866723}}},
  main:{name:'main',protected:true,commit:{sha:'f283f77684e6ca247ea41b25864a3829e407dc5d'}},
  mainAncestryComparison:{status:'diverged',behind_by:63,base_commit:{sha:h529.head},merge_base_commit:{sha:h529.base},commits:[{sha:h529.merge}]},
  timeline:[{event:'merged',commit_id:h529.merge,created_at:h529.mergedAt}],
  files:h529Files.map(([filename,status])=>({filename,status})),
  checks:{total_count:checkRuns.length,check_runs:checkRuns},
  testCommit:{sha:h529.test,tree:{sha:h529.tree},parents:[{sha:h529.base},{sha:h529.head}]},
  mergeCommit:{sha:h529.merge,tree:{sha:h529.tree},parents:[{sha:h529.base}]},
  runs,jobs,logs,
  workflowBlobs:Object.fromEntries(Object.entries(h529BlobMap).map(([path,sha])=>[path,[sha,sha,sha]]))
 }
}
test('historical #529 exact seven-job squash evidence accepts empty run PR associations only for the pinned PR',()=>{
 const e=h529Fixture()
 const result=verifyHistorical529Evidence(e)
 assert.equal(result.historical529Verified,true)
 assert.equal(result.pr,529)
 assert.equal(result.checks,7)
 assert.equal(result.squashProof.checkouts.length,7)
 assert.ok(result.squashProof.checkouts.every(x=>x.sha===h529.test))
})
test('historical #529 also accepts one exact PR association but rejects multiple associations',()=>{
 const e=h529Fixture()
 const exact={number:529,head:{sha:h529.head,ref:'dev',repo:{id:1261866723}},
  base:{ref:'main',sha:h529.base,repo:{id:1261866723}}}
 e.runs[45980919751].pull_requests=[exact]
 assert.equal(verifyHistorical529Evidence(e).historical529Verified,true)
 e.runs[45980919751].pull_requests=[exact,exact]
 assert.throws(()=>verifyHistorical529Evidence(e),/HISTORICAL_529_RUN_MISMATCH/)
})
test('historical #529 binding is one-shot and requires the exact V49 completed task ledger',()=>{
 const snapshot={requirement_id:'REQ-20261031-001',version:49,status:'ACTIVE',
  tasks:Array.from({length:9},(_,i)=>({task_id:'T-'+String(i+1).padStart(3,'0'),status:'DONE'}))}
 const command={type:'close',pr_number:529,head_sha:h529.head,note:HISTORICAL_529_PREFIX}
 assert.equal(verifyHistorical529Binding(snapshot,command),true)
 for(const [s,c] of [
  [{...snapshot,version:50},command],
  [{...snapshot,tasks:snapshot.tasks.map((t,i)=>i===8?{...t,status:'IN_REVIEW'}:t)},command],
  [snapshot,{...command,pr_number:528}],
  [snapshot,{...command,head_sha:'f'.repeat(40)}],
  [snapshot,{...command,note:HISTORICAL_529_PREFIX+'extra'}]
 ])assert.throws(()=>verifyHistorical529Binding(s,c),/HISTORICAL_529_BINDING/)
})
test('historical #529 rejects changed PR identity, ambiguous association, wrong job, checkout, tree, files or workflow blobs',()=>{
 const mutations=[
  [e=>e.pr.head.sha='f'.repeat(40),'HISTORICAL_529_PR_MISMATCH'],
  [e=>e.runs[45980919751].pull_requests=[{number:528,head:{sha:h529.head,ref:'dev',repo:{id:1261866723}},base:{ref:'main',sha:h529.base,repo:{id:1261866723}}}],'HISTORICAL_529_RUN_MISMATCH'],
  [e=>e.jobs[45980919751].jobs[0].run_attempt=1,'HISTORICAL_529_JOB_MISMATCH'],
  [e=>e.logs[140448213160]=e.logs[140448213160].replace('pull/529/merge','pull/528/merge'),'REVIEW_CHECKOUT_REF_OR_SHA'],
  [e=>e.testCommit.tree.sha='2'.repeat(40),'HISTORICAL_529_COMMIT_MISMATCH'],
  [e=>e.files.push({filename:'unexpected.txt',status:'added'}),'HISTORICAL_529_FILES_MISMATCH'],
  [e=>e.workflowBlobs[h529.ci][2]='3'.repeat(40),'HISTORICAL_529_WORKFLOW_BLOB_MISMATCH'],
  [e=>e.timeline[0].commit_id='4'.repeat(40),'HISTORICAL_529_TIMELINE_MISMATCH'],
  [e=>e.mainAncestryComparison.merge_base_commit.sha='4'.repeat(40),'HISTORICAL_529_ANCESTRY_MISMATCH'],
  [e=>delete e.runs[45980919751].pull_requests,'HISTORICAL_529_RUN_MISMATCH']
 ]
 for(const [mutate,code] of mutations){const e=h529Fixture();mutate(e);assert.throws(()=>verifyHistorical529Evidence(e),x=>x.message===code||x.code===code)}
})
test('historical #529 collector reads only pinned GET evidence and reuses the seven checkout logs',()=>{
 const e=h529Fixture(),routes=[]
 const api=route=>{
  routes.push(route)
  if(route.endsWith('/issues/529/timeline?per_page=100&page=1'))return e.timeline
  if(route.endsWith('/issues/529/timeline?per_page=100&page=2'))return []
  if(route.endsWith('/pulls/529/files?per_page=100'))return e.files
  if(route.endsWith('/git/commits/'+h529.test))return e.testCommit
  if(route.endsWith('/git/commits/'+h529.merge))return e.mergeCommit
  if(route.includes('/actions/runs/')&&route.includes('/jobs?'))return e.jobs[Number(route.match(/\/runs\/(\d+)\/jobs/)[1])]
  if(route.includes('/actions/runs/'))return e.runs[Number(route.split('/').at(-1))]
  if(route.includes('/actions/jobs/'))return e.logs[Number(route.match(/\/jobs\/(\d+)\/logs/)[1])]
  if(route.includes('/contents/')){
   const path=route.match(/\/contents\/(.+)\?ref=/)[1]
   const ref=route.split('?ref=')[1]
   return {sha:e.workflowBlobs[path][[h529.base,h529.test,h529.merge].indexOf(ref)]}
  }
  throw Error('unexpected route '+route)
 }
 const result=collectHistorical529(api,e.pr,e.main,e.checks,e.mainAncestryComparison)
 assert.equal(result.historical529Verified,true)
 assert.equal(routes.filter(x=>x.endsWith('/logs')).length,7)
 assert.ok(routes.every(x=>x.startsWith('repos/'+repo+'/')))
})
