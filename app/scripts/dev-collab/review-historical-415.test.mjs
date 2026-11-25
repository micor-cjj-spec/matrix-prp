import test from 'node:test'
import assert from 'node:assert/strict'
import {verifyHistorical415Evidence} from './review-historical-415.mjs'
const H='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65',B='dc6fc41824e28c49610fba6d9858629ab0b8a34a',M='5a30345529a1d07819069822a1b90e07b5376fcc',T='d3562e3a64741b4958e078ceb57574a17084a684',TREE='0d5b95b4a9ffc116340f64e4d9945abba8270e35'
const repo='micor-cjj-spec/matrix-prp',target='integrate/REQ-20261031-001',source='review/t001-integration-scope-20261125',pin='3d3c42e5aac5ba805825da76410c181273ba90b1'
const at='2026-11-25T05:49:00Z',finish='2026-11-25T05:49:01Z',merged='2026-11-25T06:02:26Z'
const ci='.github/workflows/ci.yml',impact='.github/workflows/feature-impact.yml',contract='.github/workflows/prp-dev-collab-contract.yml'
const commit=sha=>({sha,tree:{sha:TREE},parents:[{sha:B},{sha:H}]})
function fixture(){
 const e={pr:{number:415,state:'closed',merged:true,merge_commit_sha:M,merged_at:merged,base:{ref:target,sha:B,repo:{full_name:repo}},head:{ref:source,sha:H,repo:{full_name:repo}}},
   testCommit:commit(T),mergeCommit:commit(M),integration:{name:target,protected:true,commit:{sha:M}},timeline:[{event:'merged',commit_id:M,created_at:merged}],
   workflowBlobs:Object.fromEntries([[ci,'58a471a26155f4190eaa4ff6c4cf64589c56713e'],[impact,'f5ae5ee0bec23b559448233574292759b4543661'],[contract,'c1373ee788d3469aea37624328f4e53e66a68f9c']].map(([p,s])=>[p,[s,s,s]])),
   checks:{total_count:7,check_runs:[]},runs:{},jobs:{},logs:{}}
 for(const [n,id,r,a,p,w,ref] of [
   ['backend-tests',139011091923,45556141916,3,ci,'CI','v4'],['web-build',139011138221,45556141916,3,ci,'CI','v4'],
   ['mobile-build',139011091345,45556141916,3,ci,'CI','v4'],['db-migration-integration',139011141150,45556141916,3,ci,'CI','v4'],
   ['video-db-integration',139011126055,45556141916,3,ci,'CI','v4'],['impact-report',139008538357,45556141762,1,impact,'Feature Impact Report',pin],
   ['dev-collab-contract',139008537901,45556141768,1,contract,'PRP Dev Collaboration Contract',pin]]){
   e.checks.check_runs.push({name:n,id,head_sha:H,status:'completed',conclusion:'success',app:{id:15368,slug:'github-actions'},details_url:'https://github.com/'+repo+'/actions/runs/'+r+'/job/'+id})
   e.runs[r]={id:r,path:p,name:w,event:'pull_request',head_sha:H,head_branch:source,repository:{full_name:repo},head_repository:{full_name:repo},status:'completed',conclusion:'success',run_attempt:a,created_at:at,pull_requests:[]}
   const j={name:n,id,run_id:r,run_attempt:a,head_sha:H,status:'completed',conclusion:'success',completed_at:finish,steps:[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+ref,conclusion:'success',started_at:at,completed_at:finish}]}
   const list=e.jobs[r]??={total_count:0,jobs:[]};list.jobs.push(j);list.total_count++
   e.logs[id]=["Download action repository 'actions/checkout@"+ref+"' (SHA:"+(ref==='v4'?'11d5960a326750d5838078e36cf38b85af677262':ref)+")",'##[group]Run actions/checkout@'+ref,'[command]/usr/bin/git -c protocol.version=2 fetch --depth=1 origin +'+T+':refs/remotes/pull/415/merge','[command]/usr/bin/git checkout --progress --force refs/remotes/pull/415/merge','[command]/usr/bin/git log -1 --format=%H',T,'##[group]Run node test'].map(l=>at+' '+l).join('\n')
 }
 return e
}
test('pinned historical evidence is review-only, not a state authorization',()=>{
 const out=verifyHistorical415Evidence(fixture());assert.equal(out.historicalEvidenceVerified,true);assert.equal(out.checks,7);assert.equal(out.reviewerAuthorized,undefined)
})
for(const [label,mutate] of [
 ['wrong PR',e=>e.pr.number=416],['wrong target',e=>e.pr.base.ref='dev'],['wrong repository',e=>e.pr.head.repo.full_name='other/repo'],
 ['changed base timeline',e=>e.timeline.push({event:'base_ref_changed'})],['unprotected branch',e=>e.integration.protected=false],
 ['different merge tree',e=>e.mergeCommit.tree.sha='f'.repeat(40)],['wrong synthetic parent',e=>e.testCommit.parents[1].sha='f'.repeat(40)],
 ['modified workflow',e=>e.workflowBlobs[ci][1]='f'.repeat(40)],['missing checks',e=>e.checks.total_count++],
 ['newer failed check',e=>{e.checks.check_runs.push({...e.checks.check_runs[0],id:999999999999,conclusion:'failure'});e.checks.total_count++}],
 ['wrong run',e=>e.runs[45556141916].event='workflow_dispatch'],['wrong associated PR',e=>e.runs[45556141916].pull_requests=[{number:999,head:{sha:H},base:{ref:target}}]],
 ['wrong attempt',e=>e.jobs[45556141916].jobs[0].run_attempt=1],['missing logs',e=>delete e.logs[139011091923]],
 ['wrong checkout ref',e=>e.logs[139011091923]=e.logs[139011091923].replaceAll('pull/415/merge','pull/999/merge')],
 ['wrong first action',e=>e.logs[139011091923]=at+' ##[group]Run malicious-script\n'+e.logs[139011091923]],
 ['truncated checkout log',e=>e.logs[139011091923]=e.logs[139011091923].split('\n').slice(0,-1).join('\n')],
 ['post-merge job',e=>e.jobs[45556141916].jobs[0].completed_at='2026-11-25T06:03:00Z']
]){
 test('rejects '+label,()=>{const e=fixture();mutate(e);assert.throws(()=>verifyHistorical415Evidence(e),/^Error: HISTORICAL_/)})
}

test('wrong resolved checkout v4 action is denied',()=>{const e=fixture();e.logs[139011091923]=e.logs[139011091923].replace('11d5960a326750d5838078e36cf38b85af677262','f'.repeat(40));assert.throws(()=>verifyHistorical415Evidence(e),/HISTORICAL_CHECKOUT_ACTION/)})
