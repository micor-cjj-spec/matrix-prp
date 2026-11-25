// Review-only, narrowly pinned historical evidence for PR #415.
// Never use this as an acceptance flag, generic fallback or state writer.
const REPO='micor-cjj-spec/matrix-prp'
const BASE='dc6fc41824e28c49610fba6d9858629ab0b8a34a'
const HEAD='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65'
const MERGE='5a30345529a1d07819069822a1b90e07b5376fcc'
const TEST='d3562e3a64741b4958e078ceb57574a17084a684'
const TREE='0d5b95b4a9ffc116340f64e4d9945abba8270e35'
const TARGET='integrate/REQ-20261031-001'
const SOURCE='review/t001-integration-scope-20261125'
const PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
const CI='.github/workflows/ci.yml'
const IMPACT='.github/workflows/feature-impact.yml'
const CONTRACT='.github/workflows/prp-dev-collab-contract.yml'
const entries=[
 ['backend-tests',139011091923,45556141916,3,CI,'CI','v4'],
 ['web-build',139011138221,45556141916,3,CI,'CI','v4'],
 ['mobile-build',139011091345,45556141916,3,CI,'CI','v4'],
 ['db-migration-integration',139011141150,45556141916,3,CI,'CI','v4'],
 ['video-db-integration',139011126055,45556141916,3,CI,'CI','v4'],
 ['impact-report',139008538357,45556141762,1,IMPACT,'Feature Impact Report',PIN],
 ['dev-collab-contract',139008537901,45556141768,1,CONTRACT,'PRP Dev Collaboration Contract',PIN]
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
function verifyInitialCheckout(log,job,action){
 check(typeof log==='string'&&log.length<=4*1024*1024,'HISTORICAL_LOG_UNAVAILABLE')
 const first=job.steps?.findIndex(s=>s.name==='Run actions/checkout@'+action)
 check(Number.isInteger(first)&&first>=1&&job.steps[first].conclusion==='success'&&
   job.steps.slice(0,first).every(s=>['Set up job','Initialize containers'].includes(s.name)&&s.conclusion==='success'),
   'HISTORICAL_CHECKOUT_NOT_FIRST')
 const lines=log.replace(/^\uFEFF/,'').split(/\r?\n/).map(line=>{
   const m=line.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z) (.*)$/)
   return m?{at:date(m[1]),text:m[2]}:null
 }).filter(Boolean)
 const start=lines.findIndex(l=>l.text.startsWith('##[group]Run '))
 check(start>=0&&lines[start].text==='##[group]Run actions/checkout@'+action,'HISTORICAL_CHECKOUT_LOG_ORDER')
 const end=lines.findIndex((l,i)=>i>start&&l.text.startsWith('##[group]Run '))
 check(end>start,'HISTORICAL_CHECKOUT_LOG_TRUNCATED')
 const block=lines.slice(start,end)
 const step=job.steps[first]
 const lo=date(step.started_at),hi=date(step.completed_at)+999
 check(Number.isFinite(lo)&&Number.isFinite(hi)&&block.every(l=>l.at>=lo&&l.at<=hi),
   'HISTORICAL_CHECKOUT_TIME')
 const f=block.findIndex(l=>l.text.startsWith('[command]/usr/bin/git -c protocol.version=2 fetch ')&&
   l.text.endsWith('+'+TEST+':refs/remotes/pull/415/merge'))
 const co=block.findIndex(l=>l.text==='[command]/usr/bin/git checkout --progress --force refs/remotes/pull/415/merge')
 const hash=block.findIndex(l=>l.text==='[command]/usr/bin/git log -1 --format=%H')
 check(f>=0&&co>f&&hash>co&&block[hash+1]?.text===TEST,'HISTORICAL_CHECKOUT_REF_OR_SHA')
 if(action===PIN)check(lines.slice(0,start).some(l=>l.text.includes("Download action repository 'actions/checkout@"+PIN+"' (SHA:"+PIN+")")),'HISTORICAL_CHECKOUT_ACTION')
}
export function verifyHistorical415Evidence(e){
 const p=e?.pr
 check(p?.number===415&&p.merged===true&&p.state==='closed'&&p.merge_commit_sha===MERGE&&
   p.base?.ref===TARGET&&p.base?.sha===BASE&&p.base?.repo?.full_name===REPO&&
   p.head?.ref===SOURCE&&p.head?.sha===HEAD&&p.head?.repo?.full_name===REPO&&
   p.merged_at==='2026-11-25T06:02:26Z','HISTORICAL_PR_MISMATCH')
 verifyCommit(e.testCommit,TEST)
 verifyCommit(e.mergeCommit,MERGE)
 check(e.integration?.name===TARGET&&e.integration.protected===true&&
   e.integration.commit?.sha===MERGE,'HISTORICAL_INTEGRATION_MISMATCH')
 check(Array.isArray(e.timeline)&&e.timeline.length>0&&e.timeline.length<100&&
   e.timeline.some(x=>x.event==='merged'&&x.commit_id===MERGE&&x.created_at===p.merged_at)&&
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
     run.head_repository?.full_name===REPO&&run.status==='completed'&&run.conclusion==='success'&&
     run.run_attempt===attempt&&date(run.created_at)<date(p.merged_at)&&
     Array.isArray(run.pull_requests)&&(run.pull_requests.length===0||
       run.pull_requests.every(q=>q.number===415&&q.head?.sha===HEAD&&q.base?.ref===TARGET)),
     'HISTORICAL_RUN_MISMATCH')
   const list=e.jobs?.[runId]
   check(Number.isInteger(list?.total_count)&&Array.isArray(list.jobs)&&list.total_count===list.jobs.length&&list.total_count<=100,
     'HISTORICAL_JOBS_INCOMPLETE')
   const matched=list.jobs.filter(j=>j.id===id)
   const job=matched[0]
   check(matched.length===1&&job.name===name&&job.run_id===runId&&job.run_attempt===attempt&&job.head_sha===HEAD&&
     job.status==='completed'&&job.conclusion==='success'&&date(job.completed_at)<date(p.merged_at),'HISTORICAL_JOB_MISMATCH')
   verifyInitialCheckout(e.logs?.[id],job,action)
 }
 return Object.freeze({historicalEvidenceVerified:true,pr:415,head:HEAD,merge:MERGE,syntheticMerge:TEST,checks:7})
}
