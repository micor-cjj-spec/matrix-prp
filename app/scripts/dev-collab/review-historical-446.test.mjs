import test from 'node:test'
import assert from 'node:assert/strict'
import {verifyHistorical446Evidence,verifyHistorical446Binding,HISTORICAL_446_PREFIX} from './review-provenance.mjs'
const H='216b280386120f932eee28f22448d41bcaf82dec',B='5a30345529a1d07819069822a1b90e07b5376fcc',M='22b477fc52e90b25663ecb911e280d2979018d53',T='1c74c4681da9497adbcde50c6f2a7f30ce08f050',TREE='1614c8a00cd5419e92ddf079ac4b950cd0ca3663'
const repo='micor-cjj-spec/matrix-prp',target='integrate/REQ-20261031-001',source='task/REQ-20261031-001-T-007-security-20261125',pin='3d3c42e5aac5ba805825da76410c181273ba90b1'
const at='2026-11-26T02:19:49Z',finish='2026-11-26T02:19:51Z',merged='2026-11-26T02:53:19Z'
const ci='.github/workflows/ci.yml',impact='.github/workflows/feature-impact.yml',contract='.github/workflows/prp-dev-collab-contract.yml'
const commit=sha=>({sha,tree:{sha:TREE},parents:[{sha:B},{sha:H}]})
function fixture(){
 const e={pr:{number:446,state:'closed',merged:true,merge_commit_sha:M,merged_at:merged,base:{ref:target,sha:B,repo:{full_name:repo,id:1261866723}},head:{ref:source,sha:H,repo:{full_name:repo,id:1261866723}}},
   testCommit:commit(T),mergeCommit:commit(M),integration:{name:target,protected:true,commit:{sha:M}},timeline:[{event:'merged',commit_id:M,created_at:merged}],
   workflowBlobs:Object.fromEntries([[ci,'58a471a26155f4190eaa4ff6c4cf64589c56713e'],[impact,'f5ae5ee0bec23b559448233574292759b4543661'],[contract,'c1373ee788d3469aea37624328f4e53e66a68f9c']].map(([p,s])=>[p,[s,s,s]])),
   checks:{total_count:7,check_runs:[]},runs:{},jobs:{},logs:{}}
 for(const [n,id,r,a,p,w,ref] of [
   ['backend-tests',139647320786,45741491165,1,ci,'CI','v4'],['web-build',139647320976,45741491165,1,ci,'CI','v4'],
   ['mobile-build',139647320875,45741491165,1,ci,'CI','v4'],['db-migration-integration',139647321413,45741491165,1,ci,'CI','v4'],
   ['video-db-integration',139647320850,45741491165,1,ci,'CI','v4'],['impact-report',139647319777,45741491122,1,impact,'Feature Impact Report',pin],
   ['dev-collab-contract',139647319523,45741491086,1,contract,'PRP Dev Collaboration Contract',pin]]){
   e.checks.check_runs.push({name:n,id,head_sha:H,status:'completed',conclusion:'success',app:{id:15368,slug:'github-actions'},details_url:'https://github.com/'+repo+'/actions/runs/'+r+'/job/'+id})
   e.runs[r]={id:r,path:p,name:w,event:'pull_request',head_sha:H,head_branch:source,repository:{full_name:repo,id:1261866723},head_repository:{full_name:repo,id:1261866723},status:'completed',conclusion:'success',run_attempt:a,created_at:at,pull_requests:[]}
   const j={name:n,id,run_id:r,run_attempt:a,head_sha:H,head_branch:source,started_at:at,status:'completed',conclusion:'success',completed_at:finish,steps:[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+ref,conclusion:'success',started_at:at,completed_at:finish}]}
   const list=e.jobs[r]??={total_count:0,jobs:[]};list.jobs.push(j);list.total_count++
   e.logs[id]=["Download action repository 'actions/checkout@"+ref+"' (SHA:"+(ref==='v4'?'11d5960a326750d5838078e36cf38b85af677262':ref)+")",'##[group]Run actions/checkout@'+ref,'[command]/usr/bin/git -c protocol.version=2 fetch --depth=1 origin +'+T+':refs/remotes/pull/446/merge','[command]/usr/bin/git checkout --progress --force refs/remotes/pull/446/merge','[command]/usr/bin/git log -1 --format=%H',T,'##[group]Run node test'].map(l=>at+' '+l).join('\n')
 }
 return e
}
test('pinned historical evidence is review-only, not a state authorization',()=>{
 const out=verifyHistorical446Evidence(fixture());assert.equal(out.historicalEvidenceVerified,true);assert.equal(out.checks,7);assert.equal(out.reviewerAuthorized,undefined)
})
for(const [label,mutate] of [
 ['wrong PR',e=>e.pr.number=416],['wrong target',e=>e.pr.base.ref='dev'],['wrong repository',e=>e.pr.head.repo.full_name='other/repo'],
 ['changed base timeline',e=>e.timeline.push({event:'base_ref_changed'})],['unprotected branch',e=>e.integration.protected=false],
 ['different merge tree',e=>e.mergeCommit.tree.sha='f'.repeat(40)],['wrong synthetic parent',e=>e.testCommit.parents[1].sha='f'.repeat(40)],
 ['modified workflow',e=>e.workflowBlobs[ci][1]='f'.repeat(40)],['missing checks',e=>e.checks.total_count++],
 ['newer failed check',e=>{e.checks.check_runs.push({...e.checks.check_runs[0],id:999999999999,conclusion:'failure'});e.checks.total_count++}],
 ['wrong run',e=>e.runs[45741491165].event='workflow_dispatch'],['wrong associated PR',e=>e.runs[45741491165].pull_requests=[{number:999,head:{sha:H},base:{ref:target}}]],
 ['wrong attempt',e=>e.jobs[45741491165].jobs[0].run_attempt=2],['missing logs',e=>delete e.logs[139647320786]],
 ['wrong checkout ref',e=>e.logs[139647320786]=e.logs[139647320786].replaceAll('pull/446/merge','pull/999/merge')],
 ['wrong first action',e=>e.logs[139647320786]=at+' ##[group]Run malicious-script\n'+e.logs[139647320786]],
 ['truncated checkout log',e=>e.logs[139647320786]=e.logs[139647320786].split('\n').slice(0,-1).join('\n')],
 ['post-merge job',e=>e.jobs[45741491165].jobs[0].completed_at='2026-11-26T02:54:00Z']
]){
 test('rejects '+label,()=>{const e=fixture();mutate(e);assert.throws(()=>verifyHistorical446Evidence(e),/HISTORICAL_|REVIEW_CHECKOUT|REVIEW_LOG_UNAVAILABLE/)})
}

test('wrong resolved checkout v4 action is denied',()=>{const e=fixture();e.logs[139647320786]=e.logs[139647320786].replace('11d5960a326750d5838078e36cf38b85af677262','f'.repeat(40));assert.throws(()=>verifyHistorical446Evidence(e),/REVIEW_CHECKOUT_ACTION/)})

test('historical #446 binding requires original claim/start and latest exact submit',()=>{
 const claim={claim_id:'17b0fda3-e220-4fbb-bc15-c6ef23c9f786',worker_id:'chat_t007_security_20261125',actor:'micor-cjj-spec',generation:1}
 const command={type:'accept',requirement_id:'REQ-20261031-001',task_id:'T-007',pr_number:446,head_sha:H,worker_id:claim.worker_id,claim_id:claim.claim_id,note:HISTORICAL_446_PREFIX+'proof'}
 const receipt=(id,type,version,extra={})=>({request_id:id,actor:claim.actor,receipt:{task_id:'T-007',type,version,...extra}})
 const s={requirement_id:command.requirement_id,status:'ACTIVE',version:20,tasks:[{task_id:'T-007',status:'IN_REVIEW',claim,pr_number:446,head_sha:H}],processed_requests:[receipt('a29d43a7-8a75-4c4d-8c50-8e8fba613ad0','claim',18,{claim_id:claim.claim_id}),receipt('3f1ab2c9-136b-4cda-a4d0-73a3c72803dc','start',19),receipt('submit','submit',20,{status:'IN_REVIEW'})]}
 assert.equal(verifyHistorical446Binding(s,command,{historical446:true}),true)
 for(const bad of [{...command,task_id:'T-001'},{...command,pr_number:415},{...command,head_sha:B},{...command,claim_id:'wrong'},{...command,note:'proof'}])assert.throws(()=>verifyHistorical446Binding(s,bad,{historical446:true}),/HISTORICAL_446_BINDING/)
 assert.throws(()=>verifyHistorical446Binding(s,command,{}),/HISTORICAL_446_BINDING/)
 s.tasks[0].claim.generation=2
 assert.throws(()=>verifyHistorical446Binding(s,command,{historical446:true}),/HISTORICAL_446_BINDING/)
})
