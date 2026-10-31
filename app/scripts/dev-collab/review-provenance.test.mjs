import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyWorkflowProvenance } from './review-provenance.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'
const sha='a'.repeat(40),baseRef='integrate/REQ-20261031-001',headRef='feat/REQ-20261031-001/T-001'
const repo='micor-cjj-spec/matrix-prp',number=138
const jobs=()=>({total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
 name,id:1001+i,head_sha:sha,status:'completed',conclusion:'success',app:{slug:'github-actions'},
 details_url:`https://github.com/${repo}/actions/runs/${name==='impact-report'?102:name==='dev-collab-contract'?103:101}/job/${1001+i}`
}))})
const run = (id)=> {
 const map={101:['CI','.github/workflows/ci.yml'],102:['Feature Impact Report','.github/workflows/feature-impact.yml'],
  103:['PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']}
 const [name,path]=map[id]
 return {name,path,event:'pull_request',status:'completed',conclusion:'success',head_sha:sha,
  head_branch:headRef,repository:{full_name:repo},head_repository:{full_name:repo},
  pull_requests:[{number,head:{sha},base:{ref:baseRef}}]}
}
const verify=(data,resolver=run)=>verifyWorkflowProvenance(data,{sha,prNumber:number,baseRef,headRef},resolver)
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
