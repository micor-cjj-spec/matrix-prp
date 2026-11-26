// Review-only, narrowly pinned historical evidence for PR #446.
// Never use this as an acceptance flag, generic fallback or state writer.
import {verifyInitialReviewCheckout} from './review-provenance.mjs'
const REPO='micor-cjj-spec/matrix-prp'
const BASE='5a30345529a1d07819069822a1b90e07b5376fcc'
const HEAD='216b280386120f932eee28f22448d41bcaf82dec'
const MERGE='22b477fc52e90b25663ecb911e280d2979018d53'
const TEST='1c74c4681da9497adbcde50c6f2a7f30ce08f050'
const TREE='1614c8a00cd5419e92ddf079ac4b950cd0ca3663'
const TARGET='integrate/REQ-20261031-001'
const SOURCE='task/REQ-20261031-001-T-007-security-20261125'
const PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
const CI='.github/workflows/ci.yml'
const IMPACT='.github/workflows/feature-impact.yml'
const CONTRACT='.github/workflows/prp-dev-collab-contract.yml'
const entries=[
 ['backend-tests',139647320786,45741491165,1,CI,'CI','v4'],
 ['web-build',139647320976,45741491165,1,CI,'CI','v4'],
 ['mobile-build',139647320875,45741491165,1,CI,'CI','v4'],
 ['db-migration-integration',139647321413,45741491165,1,CI,'CI','v4'],
 ['video-db-integration',139647320850,45741491165,1,CI,'CI','v4'],
 ['impact-report',139647319777,45741491122,1,IMPACT,'Feature Impact Report',PIN],
 ['dev-collab-contract',139647319523,45741491086,1,CONTRACT,'PRP Dev Collaboration Contract',PIN]
]
const blobs={
 [CI]:'58a471a26155f4190eaa4ff6c4cf64589c56713e',
 [IMPACT]:'f5ae5ee0bec23b559448233574292759b4543661',
 [CONTRACT]:'c1373ee788d3469aea37624328f4e53e66a68f9c'
}
const check=(ok,code)=>{if(!ok)throw new Error(code)}
const exact=(a,b)=>JSON.stringify(a)===JSON.stringify(b)
const date=x=>Date.parse(x)
function verifyCommit(c,sha){
 check(c?.sha===sha&&c.tree?.sha===TREE&&
   exact(c.parents?.map(p=>p.sha),[BASE,HEAD]),'HISTORICAL_COMMIT_MISMATCH')
}
export function verifyHistorical446Evidence(e){
 const p=e?.pr
 check(p?.number===446&&p.merged===true&&p.state==='closed'&&p.merge_commit_sha===MERGE&&
   p.base?.ref===TARGET&&p.base?.sha===BASE&&p.base?.repo?.full_name===REPO&&
   p.base?.repo?.id===1261866723&&p.head?.repo?.id===1261866723&&p.head?.ref===SOURCE&&p.head?.sha===HEAD&&p.head?.repo?.full_name===REPO&&
   p.merged_at==='2026-11-26T02:53:19Z','HISTORICAL_PR_MISMATCH')
 verifyCommit(e.testCommit,TEST)
 verifyCommit(e.mergeCommit,MERGE)
 check(e.integration?.name===TARGET&&e.integration.protected===true&&
   e.integration.commit?.sha===MERGE,'HISTORICAL_INTEGRATION_MISMATCH')
 check(Array.isArray(e.timeline)&&e.timeline.length>0&&e.timeline.length<100&&
   e.timeline.filter(x=>x.event==='merged').length===1&&e.timeline.some(x=>x.event==='merged'&&x.commit_id===MERGE&&x.created_at===p.merged_at)&&
   !e.timeline.some(x=>/base_ref_changed|head_ref_force_pushed|head_ref_deleted|head_ref_restored/.test(x.event)),
   'HISTORICAL_TIMELINE_MISMATCH')
 check(exact(Object.keys(e.workflowBlobs??{}).sort(),Object.keys(blobs).sort())&&
   Object.entries(blobs).every(([path,sha])=>exact(e.workflowBlobs[path],[sha,sha,sha])),
   'HISTORICAL_WORKFLOW_BLOB_MISMATCH')
 const c=e.checks
 check(Number.isInteger(c?.total_count)&&Array.isArray(c.check_runs)&&
   c.total_count===c.check_runs.length&&c.total_count<=100,'HISTORICAL_CHECKS_INCOMPLETE')
 for(const [name,id,runId,attempt,path,workflow,action] of entries){
   const jobCheck=c.check_runs.filter(j=>j.name===name&&j.app?.id===15368&&j.app?.slug==='github-actions').sort((a,b)=>b.id-a.id)[0]
   check(jobCheck?.id===id&&jobCheck.head_sha===HEAD&&jobCheck.status==='completed'&&jobCheck.conclusion==='success'&&
     jobCheck.details_url==='https://github.com/'+REPO+'/actions/runs/'+runId+'/job/'+id,'HISTORICAL_CHECK_MISMATCH')
   const run=e.runs?.[runId]
   check(run?.id===runId&&run.path===path&&run.name===workflow&&run.event==='pull_request'&&
     run.head_sha===HEAD&&run.head_branch===SOURCE&&run.repository?.full_name===REPO&&
     run.head_repository?.full_name===REPO&&run.repository?.id===1261866723&&run.head_repository?.id===1261866723&&run.status==='completed'&&run.conclusion==='success'&&
     run.run_attempt===attempt&&date(run.created_at)<date(p.merged_at)&&
     Array.isArray(run.pull_requests)&&(run.pull_requests.length===0||
       run.pull_requests.length===1&&run.pull_requests.every(q=>q.number===446&&q.head?.sha===HEAD&&q.head?.ref===SOURCE&&q.head?.repo?.id===1261866723&&q.base?.ref===TARGET&&q.base?.sha===BASE&&q.base?.repo?.id===1261866723)),
     'HISTORICAL_RUN_MISMATCH')
   const list=e.jobs?.[runId]
   check(Number.isInteger(list?.total_count)&&Array.isArray(list.jobs)&&list.total_count===list.jobs.length&&list.total_count<=100,
     'HISTORICAL_JOBS_INCOMPLETE')
   const matched=list.jobs.filter(j=>j.id===id)
   const job=matched[0]
   check(matched.length===1&&job.name===name&&job.run_id===runId&&job.run_attempt===attempt&&job.head_sha===HEAD&&
     job.status==='completed'&&job.conclusion==='success'&&job.head_branch===SOURCE&&date(job.started_at)>=date(run.created_at)&&date(job.completed_at)>=date(job.started_at)&&date(job.completed_at)<date(p.merged_at),'HISTORICAL_JOB_MISMATCH')
   check(verifyInitialReviewCheckout(e.logs?.[id],job,446,action)===TEST,'HISTORICAL_CHECKOUT_REF_OR_SHA')
 }
 return Object.freeze({historicalEvidenceVerified:true,pr:446,head:HEAD,merge:MERGE,syntheticMerge:TEST,checks:7})
}

export const HISTORICAL_446_PREFIX='PRP_HISTORICAL_446_V1:'
// One-shot recovery; not a backdated premerge receipt.
export function verifyHistorical446Binding(snapshot,command,proof){
 const t=snapshot.tasks.find(x=>x.task_id==='T-007')
 const records=snapshot.processed_requests.filter(x=>x.receipt.task_id==='T-007')
 const start=records.find(x=>x.request_id==='3f1ab2c9-136b-4cda-a4d0-73a3c72803dc')
 const claim=records.find(x=>x.request_id==='a29d43a7-8a75-4c4d-8c50-8e8fba613ad0')
 const last=records.at(-1)
 check(proof?.historical446===true&&snapshot.requirement_id==='REQ-20261031-001'&&snapshot.status==='ACTIVE'&&
   command.type==='accept'&&command.requirement_id===snapshot.requirement_id&&command.task_id==='T-007'&&command.pr_number===446&&command.head_sha===HEAD&&
   t?.status==='IN_REVIEW'&&t.pr_number===446&&t.head_sha===HEAD&&t.claim?.actor==='micor-cjj-spec'&&
   t.claim?.worker_id==='chat_t007_security_20261125'&&t.claim?.generation===1&&command.worker_id===t.claim.worker_id&&command.claim_id===t.claim.claim_id&&
   claim?.actor===t.claim.actor&&claim.receipt?.type==='claim'&&claim.receipt?.version===18&&claim.receipt?.claim_id===t.claim.claim_id&&
   start?.actor===t.claim.actor&&start.receipt?.type==='start'&&start.receipt?.version===19&&
   last?.actor===t.claim.actor&&last.receipt?.type==='submit'&&last.receipt?.status==='IN_REVIEW'&&last.receipt?.version>19&&last.receipt?.version<=snapshot.version&&
   typeof command.note==='string'&&command.note.startsWith(HISTORICAL_446_PREFIX),
   'HISTORICAL_446_BINDING')
 return true
}
// Fixed GET routes only. Existing Issue CAS repeats the entire review.
export function collectHistorical446(api,pr,branch,checks){
 const root='repos/'+REPO
 const get=p=>api(root+p)
 const runIds=[45741491165,45741491122,45741491086]
 const obj=(keys,fn)=>Object.fromEntries(keys.map(k=>[k,fn(k)]))
 const timeline=get('/issues/446/timeline?per_page=100&page=1')
 const page2=get('/issues/446/timeline?per_page=100&page=2')
 check(Array.isArray(page2)&&page2.length===0,'HISTORICAL_TIMELINE_INCOMPLETE')
 return verifyHistorical446Evidence({pr,integration:branch,checks,timeline,
   testCommit:get('/git/commits/'+TEST),mergeCommit:get('/git/commits/'+MERGE),
   runs:obj(runIds,id=>get('/actions/runs/'+id)),
   jobs:obj(runIds,id=>get('/actions/runs/'+id+'/jobs?per_page=100&filter=latest')),
   logs:obj(entries.map(x=>x[1]),id=>get('/actions/jobs/'+id+'/logs')),
   workflowBlobs:obj(Object.keys(blobs),path=>[BASE,TEST,MERGE].map(ref=>get('/contents/'+path+'?ref='+ref)?.sha))
 })
}
