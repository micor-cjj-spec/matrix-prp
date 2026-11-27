import { CollabError } from './core.mjs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { REQUIRED_CHECKS } from './review-gate.mjs'

const REPO = 'micor-cjj-spec/matrix-prp'
const WORKFLOW_FOR_CHECK = Object.freeze({
  'backend-tests': '.github/workflows/ci.yml',
  'web-build': '.github/workflows/ci.yml',
  'mobile-build': '.github/workflows/ci.yml',
  'db-migration-integration': '.github/workflows/ci.yml',
  'video-db-integration': '.github/workflows/ci.yml',
  'impact-report': '.github/workflows/feature-impact.yml',
  'dev-collab-contract': '.github/workflows/prp-dev-collab-contract.yml'
})
const WORKFLOW_NAME = Object.freeze({
  '.github/workflows/ci.yml': 'CI',
  '.github/workflows/feature-impact.yml': 'Feature Impact Report',
  '.github/workflows/prp-dev-collab-contract.yml': 'PRP Dev Collaboration Contract'
})
const SHA=/^[a-f0-9]{40}$/
function check(ok,code){if(!ok)throw new CollabError(code)}

const LOG_LIMIT=4*1024*1024
const PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
export function isReviewLogRoute(route){
  return typeof route==='string' && /^repos\/micor-cjj-spec\/matrix-prp\/actions\/jobs\/[1-9]\d{0,15}\/logs$/.test(route)
}
// Fixed API origin, explicit one-hop HTTPS redirect, never forward credentials
// to the log storage host. Only validated Job IDs are requested by the collector.
export async function readReviewJobLog(route,{token,fetcher=fetch}={}){
  check(isReviewLogRoute(route)&&typeof token==='string'&&token.length>0,'REVIEW_LOG_REQUEST')
  const signal=AbortSignal.timeout(30000)
  let response=await fetcher('https://api.github.com/'+route,{headers:{Authorization:'Bearer '+token,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},redirect:'manual',signal})
  if([302,303,307].includes(response.status)){
    const location=response.headers.get('location')
    check(location,'REVIEW_LOG_REDIRECT')
    const u=new URL(location)
    check(u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&
      /(^|\.)(blob\.core\.windows\.net|actions\.githubusercontent\.com|githubusercontent\.com)$/.test(u.hostname),'REVIEW_LOG_REDIRECT')
    response=await fetcher(u,{redirect:'manual',signal})
  }
  check(response.ok&&response.body,'REVIEW_LOG_HTTP')
  let size=0;const parts=[]
  for await(const chunk of response.body){size+=chunk.length;check(size<=LOG_LIMIT,'REVIEW_LOG_SIZE');parts.push(Buffer.from(chunk))}
  return Buffer.concat(parts).toString('utf8')
}

// Reuse the reviewed first-checkout evidence pattern, but no historical #415
// exception, hard-coded task/PR, or inference from missing PR associations.
export function verifyInitialReviewCheckout(log,job,prNumber,action){
  check(Number.isSafeInteger(prNumber)&&prNumber>0&&(action==='v4'||action===PIN),'REVIEW_CHECKOUT_INPUT')
  check(typeof log==='string'&&Buffer.byteLength(log,'utf8')<=LOG_LIMIT,'REVIEW_LOG_UNAVAILABLE')
  const first=job.steps?.findIndex(s=>s.name==='Run actions/checkout@'+action)
  check(Number.isInteger(first)&&first>=1&&job.steps[first].conclusion==='success'&&
    job.steps.slice(0,first).every(s=>['Set up job','Initialize containers'].includes(s.name)&&s.conclusion==='success'),'REVIEW_CHECKOUT_NOT_FIRST')
  const lines=log.replace(/^\uFEFF/,'').split(/\r?\n/).map(line=>{
    const m=line.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z) (.*)$/)
    return m?{at:Date.parse(m[1]),text:m[2]}:null
  }).filter(Boolean)
  const start=lines.findIndex(l=>l.text.startsWith('##[group]Run '))
  check(start>=0&&lines[start].text==='##[group]Run actions/checkout@'+action,'REVIEW_CHECKOUT_LOG_ORDER')
  const end=lines.findIndex((l,i)=>i>start&&l.text.startsWith('##[group]Run '))
  check(end>start,'REVIEW_CHECKOUT_LOG_TRUNCATED')
  const block=lines.slice(start,end),step=job.steps[first]
  const lo=Date.parse(step.started_at),hi=Date.parse(step.completed_at)+999
  check(Number.isFinite(lo)&&Number.isFinite(hi)&&block.every(l=>l.at>=lo&&l.at<=hi),'REVIEW_CHECKOUT_TIME')
  const ref='refs/remotes/pull/'+prNumber+'/merge'
  const fetches=block.map((l,i)=>({i,l:l.text})).filter(x=>x.l.startsWith('[command]/usr/bin/git -c protocol.version=2 fetch ')&&x.l.endsWith(':'+ref))
  check(fetches.length===1,'REVIEW_CHECKOUT_REF_OR_SHA')
  const f=fetches[0].i, fetchSha=fetches[0].l.slice(-(ref.length+42),-ref.length-1)
  const co=block.findIndex(l=>l.text==='[command]/usr/bin/git checkout --progress --force '+ref)
  const hash=block.findIndex(l=>l.text==='[command]/usr/bin/git log -1 --format=%H')
  check(/^\+[a-f0-9]{40}$/.test(fetchSha)&&co>f&&hash>co&&block[hash+1]?.text===fetchSha.slice(1),'REVIEW_CHECKOUT_REF_OR_SHA')
  const resolved=action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':PIN
  check(lines.slice(0,start).some(l=>l.text.includes("Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")")),'REVIEW_CHECKOUT_ACTION')
  return fetchSha.slice(1)
}
export function verifyWorkflowProvenance(checks, {sha,prNumber,baseRef,headRef,mergedAt,checkout}, loadRun,loadJobs){
  check(SHA.test(sha) && Number.isSafeInteger(prNumber) && prNumber>0 &&
    typeof baseRef==='string' && baseRef.length>0 &&
    typeof headRef==='string' && headRef.length>0 &&
    typeof loadRun==='function' && typeof loadJobs==='function' && typeof mergedAt==='string' && Number.isFinite(Date.parse(mergedAt)),'PROVENANCE_INPUTS')
  check(checks && Number.isInteger(checks.total_count) &&
    Array.isArray(checks.check_runs) && checks.total_count===checks.check_runs.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  // A push on the same dev HEAD can publish newer check IDs than the PR
  // run. Exclude only a fully identified same-repo push from this exact
  // workflow/branch/SHA; keep every other candidate fail-closed.
  const candidates = new Map(), recent = new Map(), candidateRuns = new Map()
  for(const job of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(job?.name) || job?.app?.slug!=='github-actions') continue
    check(Number.isSafeInteger(job.id)&&job.id>0,'INVALID_CHECK_ID')
    if(!candidates.has(job.name))candidates.set(job.name,[])
    candidates.get(job.name).push(job)
  }
  const candidateRun = id => {
    if(!candidateRuns.has(id))candidateRuns.set(id,loadRun(id))
    return candidateRuns.get(id)
  }
  for(const name of REQUIRED_CHECKS){
    const list=(candidates.get(name)||[]).sort((a,b)=>b.id-a.id)
    check(list.length>0,'CHECK_MISSING_'+name)
    let selected=null, pushFallback=null
    for(const job of list){
      const match=typeof job.details_url==='string' && job.details_url.match(
        /^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
      const runId=match?Number(match[1]):null
      const validRunRef=!!match && Number(match[2])===job.id &&
        Number.isSafeInteger(runId) && runId>0
      const run=validRunRef && job.app?.id===15368 && job.head_sha===sha
        ?candidateRun(runId):null
      const expected=WORKFLOW_FOR_CHECK[name]
      const sameHeadPush=baseRef==='main' && headRef==='dev' && job.app?.id===15368 && job.head_sha===sha && validRunRef &&
        run?.id===runId && run?.event==='push' && run?.head_sha===sha &&
        run?.head_branch===headRef &&
        run?.repository?.full_name===REPO && run?.repository?.id===1261866723 &&
        run?.head_repository?.full_name===REPO && run?.head_repository?.id===1261866723 &&
        run?.path===expected && run?.name===WORKFLOW_NAME[expected]
      if(sameHeadPush){
        if(!pushFallback)pushFallback={job,runId}
        continue
      }
      selected={job,runId:validRunRef?runId:null}
      break
    }
    // If a check exists only as a push, retain it so the existing event/PR
    // provenance checks reject it rather than silently skipping the check.
    recent.set(name,selected??pushFallback)
  }
  if(checkout!==undefined)check(checkout&&baseRef==='main'&&headRef==='dev'&&SHA.test(checkout.baseSha||'')&&typeof checkout.loadLog==='function','REVIEW_CHECKOUT_INPUT')
  const seenRun = new Map(), seenJobs=new Map(), checkouts=[]
  for(const name of REQUIRED_CHECKS){
    const selected=recent.get(name)
    check(selected,'CHECK_MISSING_'+name)
    const job=selected.job
    check(job.app?.id===15368,'WRONG_CHECK_APP_'+name)
    check(job.head_sha===sha && job.status==='completed' && job.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
    const match=typeof job.details_url==='string' && job.details_url.match(
      /^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
    check(match && Number(match[2])===job.id,'UNTRUSTED_CHECK_DETAILS_'+name)
    const runId=Number(match[1])
    check(Number.isSafeInteger(runId) && runId>0,'UNTRUSTED_WORKFLOW_ID')
    if(!seenRun.has(runId)) seenRun.set(runId,candidateRuns.has(runId)?candidateRuns.get(runId):loadRun(runId))
    const run=seenRun.get(runId)
    const expected=WORKFLOW_FOR_CHECK[name]
    check(run?.id===runId && run?.path===expected && run?.name===WORKFLOW_NAME[expected],
      'WRONG_CHECK_WORKFLOW_'+name)
    check(run?.event==='pull_request' && run?.status==='completed' &&
      run?.conclusion==='success' && run?.head_sha===sha &&
      run?.head_branch===headRef &&
      run?.repository?.full_name===REPO && run?.head_repository?.full_name===REPO && run.repository.id===1261866723 && run.head_repository.id===1261866723 && Number.isSafeInteger(run.run_attempt) && run.run_attempt>0 && Number.isFinite(Date.parse(run.created_at)) && Date.parse(run.created_at)<=Date.parse(mergedAt),
      'WRONG_WORKFLOW_ORIGIN_'+name)
    const links=run?.pull_requests
    if(checkout && Array.isArray(links) && links.length===0){
      // After merge, GitHub may omit the run-level PR association. In this
      // squash-only path, the exact pull/<number>/merge checkout log below
      // binds the PR number and tested SHA; the test-commit parents bind base
      // and head. Missing or ambiguous associations still fail closed.
    }else{
      check(Array.isArray(links) && links.length===1 && links.every(pr=>
        pr.number===prNumber && pr.head?.sha===sha && pr.base?.ref===baseRef),
        'WORKFLOW_PR_MISMATCH_'+name)
      if(checkout){
        const link=links[0]
        check(link.base.sha===checkout.baseSha&&link.head.ref===headRef&&link.base.repo?.id===1261866723&&link.head.repo?.id===1261866723,'WORKFLOW_CHECKOUT_PR_BASE_MISMATCH_'+name)
      }
    }
    if(!seenJobs.has(runId))seenJobs.set(runId,loadJobs(runId))
    const listing=seenJobs.get(runId)
    check(Number.isSafeInteger(listing?.total_count) && listing.total_count<=100 && Array.isArray(listing.jobs) && listing.jobs.length===listing.total_count,'INCOMPLETE_WORKFLOW_JOBS_'+name)
    const matches=listing.jobs.filter(j=>j?.name===name)
    check(matches.length===1 && listing.jobs.filter(j=>j?.id===job.id).length===1,'AMBIGUOUS_WORKFLOW_JOB_'+name)
    const actual=matches[0]
    check(actual.id===job.id && actual.run_id===runId && actual.head_sha===sha && actual.head_branch===headRef && actual.workflow_name===run.name && Number.isSafeInteger(actual.run_attempt) && actual.run_attempt>=1 && actual.run_attempt<=run.run_attempt && actual.status==='completed' && actual.conclusion==='success','WORKFLOW_JOB_MISMATCH_'+name)
    // A successful preserved job from an earlier attempt is valid only when
    // present in the latest jobs list. Reject post-merge reruns as evidence.
    const started=Date.parse(actual.started_at), completed=Date.parse(actual.completed_at)
    check(Number.isFinite(started)&&Number.isFinite(completed)&&started>=Date.parse(run.created_at)&&completed>=started&&completed<=Date.parse(mergedAt),'WORKFLOW_JOB_TIME_MISMATCH_'+name)
    if(checkout)checkouts.push({name,jobId:actual.id,sha:verifyInitialReviewCheckout(checkout.loadLog(actual.id),actual,prNumber,expected==='.github/workflows/ci.yml'?'v4':PIN)})
  }
  if(checkout)check(checkouts.every(x=>x.sha===checkouts[0].sha),'REVIEW_CHECKOUT_TREE_DIVERGED')
  return Object.freeze({verified:true,workflow_runs:[...seenRun.keys()].sort((a,b)=>a-b),...(checkout?{checkouts}: {})})
}

if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try{
    check(process.argv.length===4&&process.argv[2]==='--job-log','REVIEW_LOG_REQUEST')
    process.stdout.write(await readReviewJobLog(process.argv[3],{token:process.env.GH_TOKEN}))
  }catch(e){
    console.error('Review log unavailable: '+(/^REVIEW_[A-Z_]+$/.test(e?.code)?e.code:'API_OR_EVIDENCE_ERROR'))
    process.exitCode=1
  }
}

// Narrow historical #446 recovery reuses the existing checkout verifier; no generic fallback.
export const {HISTORICAL_446_PREFIX,verifyHistorical446Binding,collectHistorical446,verifyHistorical446Evidence}=(()=>{
// Review-only, narrowly pinned historical evidence for PR #446.
// Never use this as an acceptance flag, generic fallback or state writer.
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
function verifyHistorical446Evidence(e){
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

const HISTORICAL_446_PREFIX='PRP_HISTORICAL_446_V1:'
// One-shot recovery; not a backdated premerge receipt.
function verifyHistorical446Binding(snapshot,command,proof){
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
function collectHistorical446(api,pr,branch,checks){
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

 return {HISTORICAL_446_PREFIX,verifyHistorical446Binding,collectHistorical446,verifyHistorical446Evidence}
})()
