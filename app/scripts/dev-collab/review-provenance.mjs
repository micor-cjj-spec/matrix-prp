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
  const recent = new Map()
  for(const job of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(job?.name) || job?.app?.slug!=='github-actions') continue
    check(Number.isSafeInteger(job.id)&&job.id>0,'INVALID_CHECK_ID')
    const old=recent.get(job.name)
    if(!old || job.id>old.id)recent.set(job.name,job)
  }
  if(checkout!==undefined)check(checkout&&baseRef==='main'&&headRef==='dev'&&SHA.test(checkout.baseSha||'')&&typeof checkout.loadLog==='function','REVIEW_CHECKOUT_INPUT')
  const seenRun = new Map(), seenJobs=new Map(), checkouts=[]
  for(const name of REQUIRED_CHECKS){
    const job=recent.get(name)
    check(job,'CHECK_MISSING_'+name)
    check(job.app?.id===15368,'WRONG_CHECK_APP_'+name)
    check(job.head_sha===sha && job.status==='completed' && job.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
    const match=typeof job.details_url==='string' && job.details_url.match(
      /^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
    check(match && Number(match[2])===job.id,'UNTRUSTED_CHECK_DETAILS_'+name)
    const runId=Number(match[1])
    check(Number.isSafeInteger(runId) && runId>0,'UNTRUSTED_WORKFLOW_ID')
    if(!seenRun.has(runId)) seenRun.set(runId,loadRun(runId))
    const run=seenRun.get(runId)
    const expected=WORKFLOW_FOR_CHECK[name]
    check(run?.id===runId && run?.path===expected && run?.name===WORKFLOW_NAME[expected],
      'WRONG_CHECK_WORKFLOW_'+name)
    check(run?.event==='pull_request' && run?.status==='completed' &&
      run?.conclusion==='success' && run?.head_sha===sha &&
      run?.head_branch===headRef &&
      run?.repository?.full_name===REPO && run?.head_repository?.full_name===REPO && run.repository.id===1261866723 && run.head_repository.id===1261866723 && Number.isSafeInteger(run.run_attempt) && run.run_attempt>0 && Number.isFinite(Date.parse(run.created_at)) && Date.parse(run.created_at)<=Date.parse(mergedAt),
      'WRONG_WORKFLOW_ORIGIN_'+name)
    check(Array.isArray(run?.pull_requests) && run.pull_requests.length===1 && run.pull_requests.every(pr=>
      pr.number===prNumber && pr.head?.sha===sha && pr.base?.ref===baseRef),
      'WORKFLOW_PR_MISMATCH_'+name)
    if(checkout){
      const link=run.pull_requests[0]
      check(link.base.sha===checkout.baseSha&&link.head.ref===headRef&&link.base.repo?.id===1261866723&&link.head.repo?.id===1261866723,'WORKFLOW_CHECKOUT_PR_BASE_MISMATCH_'+name)
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
