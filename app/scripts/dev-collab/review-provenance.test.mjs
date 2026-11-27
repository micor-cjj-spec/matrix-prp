import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyWorkflowProvenance, readReviewJobLog } from './review-provenance.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'
const sha='a'.repeat(40),baseRef='integrate/REQ-20261031-001',headRef='feat/REQ-20261031-001/T-001'
const repo='micor-cjj-spec/matrix-prp',number=138
const jobs=()=>({total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
 name,id:1001+i,head_sha:sha,status:'completed',conclusion:'success',app:{slug:'github-actions',id:15368},
 details_url:`https://github.com/${repo}/actions/runs/${name==='impact-report'?102:name==='dev-collab-contract'?103:101}/job/${1001+i}`
}))})
const run = (id,branch=headRef)=> {
 const map={101:['CI','.github/workflows/ci.yml'],102:['Feature Impact Report','.github/workflows/feature-impact.yml'],
  103:['PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']}
 const [name,path]=map[id]
 return {id,name,path,run_attempt:2,created_at:'2026-10-31T17:00:00Z',event:'pull_request',status:'completed',conclusion:'success',head_sha:sha,
  head_branch:branch,repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},
  pull_requests:[{number,head:{sha,ref:branch},base:{ref:baseRef}}]}
}
const list=(id,branch=headRef)=>{const jobsForRun=jobs().check_runs.filter(c=>c.details_url.includes('/runs/'+id+'/')).map(c=>({name:c.name,id:c.id,run_id:id,run_attempt:1,head_sha:sha,head_branch:branch,workflow_name:run(id,branch).name,status:'completed',conclusion:'success',started_at:'2026-10-31T17:01:00Z',completed_at:'2026-10-31T17:59:00Z'}));return {total_count:jobsForRun.length,jobs:jobsForRun}}
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
 const pushRun={...run(101,'dev'),id:104,event:'push',pull_requests:[]}
 const result=verify(x,id=>id===104?pushRun:run(id,'dev'),id=>list(id,'dev'),{headRef:'dev'})
 assert.deepEqual(result.workflow_runs,[101,102,103])
})
test('same-HEAD dev push checks alone remain rejected as non-PR evidence',()=>{
 const x=jobs()
 const backend=x.check_runs[0]
 x.check_runs=x.check_runs.filter(c=>c.name!=='backend-tests')
 x.check_runs.push({...backend,id:9999,
  details_url:'https://github.com/'+repo+'/actions/runs/104/job/9999'})
 x.total_count=x.check_runs.length
 const pushRun={...run(101,'dev'),id:104,event:'push',pull_requests:[]}
 fails(()=>verify(x,id=>id===104?pushRun:run(id,'dev'),id=>list(id,'dev'),{headRef:'dev'}),'WRONG_WORKFLOW_ORIGIN_backend-tests')
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
