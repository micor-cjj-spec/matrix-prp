import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { CollabError } from './core.mjs'
import { verifyTaskEvidence, verifyIntegrationRelease, verifyRequirementClose, verifyIntegrationPolicy, verifyOwnerAttestedIntegrationPolicy, hasDevAncestry } from './review-gate.mjs'
import { verifyWorkflowProvenance, isReviewLogRoute } from './review-provenance.mjs'

import {HISTORICAL_446_PREFIX,verifyHistorical446Binding,collectHistorical446} from './review-provenance.mjs'

const RECEIPT_ACCEPT_PREFIX='PRP_PREMERGE_RECEIPT_V1:'

const REPO='micor-cjj-spec/matrix-prp'
const SHA=/^[a-f0-9]{40}$/
const OWNER_ID=123868412
const ISSUE_PATH='.github/workflows/prp-collab-issue-ingress.yml'
const OWNER_NOTE='PRP_RULESET_ATTESTATION_V1:'
function check(ok,code){if(!ok)throw new CollabError(code)}
export function ghApi(route){
  if(isReviewLogRoute(route))return execFileSync(process.execPath,
    [fileURLToPath(new URL('./review-provenance.mjs',import.meta.url)),'--job-log',route],
    {encoding:'utf8',maxBuffer:4*1024*1024,timeout:35000,stdio:['ignore','pipe','pipe']})
  const json=execFileSync('gh',['api','--method','GET','--hostname','github.com',route],{encoding:'utf8',maxBuffer:5*1024*1024,timeout:30000,stdio:['ignore','pipe','pipe']})
  return JSON.parse(json)
}

/** The only trust boundary: called exclusively from the owner-initiated reviewed workflow. */
export function trustedReviewContext(snapshot,command,env,api,issueProof,receiptRuntime){
  check(env.GITHUB_ACTIONS==='true' && env.GITHUB_REF==='refs/heads/main' &&
    env.GITHUB_REPOSITORY===REPO && env.GITHUB_ACTOR==='micor-cjj-spec' &&
    env.GITHUB_REPOSITORY_OWNER==='micor-cjj-spec' && typeof env.GH_TOKEN==='string' &&
    env.GH_TOKEN.length>0,'UNTRUSTED_REVIEW_CONTEXT')
  check(command.type==='accept'||command.type==='close'||command.type==='capture_receipt','INVALID_REVIEW_ACTION')
  const manual=env.GITHUB_EVENT_NAME==='workflow_dispatch' && env.GITHUB_WORKFLOW_REF===REPO+'/.github/workflows/prp-collab-coordinator.yml@refs/heads/main'
  const issue=env.GITHUB_EVENT_NAME==='issues' && env.GITHUB_EVENT_ACTION==='opened' && env.GITHUB_WORKFLOW_REF===REPO+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'
  check(SHA.test(env.GITHUB_SHA||'') && (manual || (issue && ['accept','capture_receipt'].includes(command.type))),'UNTRUSTED_REVIEW_ENTRYPOINT')
  const root='repos/'+REPO
  const historical446=issueProof?.historical446===true
  const marked=typeof command.note==='string'&&command.note.startsWith(HISTORICAL_446_PREFIX)
  check(marked===historical446&&(!historical446||issue),'HISTORICAL_446_EXPLICIT_ISSUE_REQUIRED')
  const capture=command.type==='capture_receipt',receiptAccept=issueProof?.receiptAccept===true
  const receiptMarked=typeof command.note==='string'&&command.note.startsWith(RECEIPT_ACCEPT_PREFIX)
  check(receiptMarked===receiptAccept&&capture===(issueProof?.captureReceipt===true)&&
    (!capture&&!receiptAccept||issue&&!historical446&&(!receiptAccept||command.type==='accept')),'RECEIPT_EXPLICIT_ISSUE_REQUIRED')
  const ownerNote=historical446?command.note.slice(HISTORICAL_446_PREFIX.length):
    receiptAccept?command.note.slice(RECEIPT_ACCEPT_PREFIX.length):command.note
  const requirePolicy=()=>{
    const rule=api(root+'/rulesets/28050327')
    const noteIsOwner=typeof ownerNote==='string'&&ownerNote.startsWith(OWNER_NOTE)
    if(!noteIsOwner && issueProof===undefined)return verifyIntegrationPolicy(snapshot.requirement_id,rule)
    // Redacted evidence is supported only by the existing authenticated Issue
    // transaction, which revalidates the original event and evidence before CAS.
    // The manual coordinator lacks that final review boundary; no fallback there.
    check(issue&&['accept','capture_receipt'].includes(command.type)&&noteIsOwner&&issueProof?.actorId===OWNER_ID&&
      Number.isSafeInteger(issueProof.sourceIssue)&&issueProof.sourceIssue>0&&
      SHA.test(issueProof.stateSha||'')&&issueProof.stateSha===issueProof.expectedStateSha&&
      issueProof.expectedVersion===snapshot.version&&issueProof.note===command.note,
      'OWNER_RULESET_ISSUE_CONTEXT_REQUIRED')
    const runId=Number(env.GITHUB_RUN_ID)
    check(Number.isSafeInteger(runId)&&runId>0&&env.GITHUB_RUN_ATTEMPT==='1',
      'OWNER_RULESET_WORKFLOW_RUN')
    const run=api(root+'/actions/runs/'+runId)
    const issueTime=Date.parse(issueProof.issueCreatedAt),runTime=Date.parse(run?.created_at)
    check(run?.id===runId&&run.event==='issues'&&run.path===ISSUE_PATH&&
      run.status==='in_progress'&&run.head_branch==='main'&&run.head_sha===env.GITHUB_SHA&&
      run.run_attempt===1&&run.actor?.login===env.GITHUB_ACTOR&&
      run.actor?.login==='micor-cjj-spec'&&run.actor?.id===OWNER_ID&&
      run.repository?.full_name===REPO&&run.repository?.id===1261866723&&
      Number.isFinite(issueTime)&&Number.isFinite(runTime)&&runTime>=issueTime-30000&&
      runTime<=Date.now()+30000,
      'OWNER_RULESET_WORKFLOW_IDENTITY')
    return verifyOwnerAttestedIntegrationPolicy(snapshot.requirement_id,rule,ownerNote,{
      requestId:command.request_id,action:command.type,taskId:command.task_id??null,
      prNumber:command.pr_number,headSha:command.head_sha,stateVersion:snapshot.version,
      mainSha:env.GITHUB_SHA,stateSha:issueProof.stateSha
    },{created_at:issueProof.issueCreatedAt})
  }
  const requireMain=main=>check(main?.name==='main' && main.protected===true && main.commit?.sha===env.GITHUB_SHA,'REVIEW_MAIN_REVISION_MISMATCH')
  const loadJobs=id=>api(root+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest')
  const integrationRef='integrate/'+snapshot.requirement_id
  if(capture||receiptAccept){
    check(receiptRuntime&&typeof receiptRuntime.verifyReceiptCommand==='function'&&typeof receiptRuntime.collectReceiptEvidence==='function'&&typeof receiptRuntime.verifyReceiptAccept==='function','RECEIPT_RUNTIME_REQUIRED')
    receiptRuntime.verifyReceiptCommand(snapshot,command,issueProof)
    requireMain(api(root+'/branches/main'))
    const policy=requirePolicy()
    check(policy.ownerAttested===true,'RECEIPT_OWNER_POLICY')
    if(capture){
      const evidence=receiptRuntime.collectReceiptEvidence(snapshot,command.task_id,api)
      evidence.captureOrigin={request_id:command.request_id,source_issue:issueProof.sourceIssue,
        issue_created_at:issueProof.issueCreatedAt,run_id:Number(env.GITHUB_RUN_ID),main_sha:env.GITHUB_SHA}
      requireMain(api(root+'/branches/main'))
      requirePolicy()
      return {captureEvidenceVerified:true,evidence}
    }
    const result=receiptRuntime.verifyReceiptAccept(snapshot,command,issueProof,env.GITHUB_SHA,api)
    check(result.receiptEvidenceVerified===true&&result.checks===7,'RECEIPT_EVIDENCE_REQUIRED')
    requireMain(api(root+'/branches/main'))
    requirePolicy()
    return {reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true,ownerRulesetAttested:true,receiptEvidenceVerified:true}
  }
  if(command.type==='accept'){
    const task=snapshot.tasks.find(t=>t.task_id===command.task_id)
    check(task && task.status==='IN_REVIEW','TASK_NOT_IN_REVIEW')
    check(command.pr_number===task.pr_number && command.head_sha===task.head_sha,'REVIEW_TASK_MISMATCH')
    const pr=api(`repos/${REPO}/pulls/${task.pr_number}`)
    const branch=api(`repos/${REPO}/branches/${encodeURIComponent(integrationRef)}`)
    check(SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
    const comparison=api(`repos/${REPO}/compare/${pr.merge_commit_sha}...${branch.commit.sha}`)
    const checks=api(`repos/${REPO}/commits/${task.head_sha}/check-runs?per_page=100`)
    const files=api(`repos/${REPO}/pulls/${task.pr_number}/files?per_page=100`)
    verifyTaskEvidence(snapshot,command.task_id,{pr,branch,comparison,checks,files})
    requireMain(api(root+'/branches/main'))
    const policyProof=requirePolicy()
    if(historical446){
      verifyHistorical446Binding(snapshot,command,issueProof)
      const evidence=collectHistorical446(api,pr,branch,checks)
      check(evidence.historicalEvidenceVerified===true&&evidence.pr===446&&evidence.checks===7,'HISTORICAL_446_EVIDENCE')
      requirePolicy()
      return {reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true,ownerRulesetAttested:true,historical446Verified:true}
    }
    verifyWorkflowProvenance(checks,{sha:task.head_sha,prNumber:task.pr_number,
      baseRef:integrationRef,headRef:pr.head.ref,mergedAt:pr.merged_at},id=>api(`repos/${REPO}/actions/runs/${id}`),loadJobs)
    return {reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true,...(policyProof.ownerAttested?{ownerRulesetAttested:true}:{})}
  }
  check(Number.isInteger(command.pr_number)&&SHA.test(command.head_sha),'MISSING_INTEGRATION_PR')
  const pr=api(`repos/${REPO}/pulls/${command.pr_number}`)
  const branch=api(`repos/${REPO}/branches/main`)
  check(SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  const comparison=api(`repos/${REPO}/compare/${pr.merge_commit_sha}...${branch.commit.sha}`)
  // Require a distinct protected integration history to be included in the
  // exact dev head subsequently merged into main. No cherry-pick approximation.
  const integrationBranch=api(`repos/${REPO}/branches/${encodeURIComponent(integrationRef)}`)
  const integrationComparison=api(`repos/${REPO}/compare/${integrationBranch.commit.sha}...${command.head_sha}`)
  // Prove the tested dev PR head itself survived into the protected main
  // history, not merely that a squash PR reported "merged".
  const mainAncestryComparison=api(`repos/${REPO}/compare/${command.head_sha}...${branch.commit.sha}`)
  const checks=api(`repos/${REPO}/commits/${command.head_sha}/check-runs?per_page=100`)
  const proof={pr,branch,comparison,checks,integrationBranch,integrationComparison,mainAncestryComparison}
  const runInput={sha:command.head_sha,prNumber:command.pr_number,
    baseRef:'main',headRef:pr.head.ref,mergedAt:pr.merged_at}
  const loadRun=id=>api(root+'/actions/runs/'+id)
  // Only a fully identified squash candidate may request raw checkout evidence.
  // A missing or malformed ancestry response is not itself squash proof.
  if(!hasDevAncestry(mainAncestryComparison,command.head_sha)&&SHA.test(pr?.base?.sha||'')&&
    pr.base.ref==='main'&&pr.head.ref==='dev'&&pr.head.sha===command.head_sha&&pr.number===command.pr_number&&pr.merged===true){
    requireMain(branch)
    requirePolicy()
    const result=verifyWorkflowProvenance(checks,{...runInput,
      checkout:{baseSha:pr.base.sha,loadLog:id=>api(root+'/actions/jobs/'+id+'/logs')}},loadRun,loadJobs)
    const testSha=result.checkouts[0].sha
    const mergeCommit=api(root+'/git/commits/'+pr.merge_commit_sha)
    const testCommit=api(root+'/git/commits/'+testSha)
    const workflows=['ci.yml','feature-impact.yml','prp-dev-collab-contract.yml'].map(n=>'.github/workflows/'+n)
    const workflowBlobs=Object.fromEntries(workflows.map(path=>[path,[pr.base.sha,testSha,pr.merge_commit_sha].map(ref=>api(root+'/contents/'+path+'?ref='+ref)?.sha)]))
    proof.squashProof={mergeCommit,testCommit,checkouts:result.checkouts,workflowBlobs}
  }
  verifyIntegrationRelease(snapshot,command,proof)
  requireMain(branch)
  requirePolicy()
  if(!proof.squashProof)verifyWorkflowProvenance(checks,runInput,loadRun,loadJobs)
  verifyRequirementClose(snapshot,{
    actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true
  })
  return {reviewerAuthorized:true,acceptanceApproved:true,integrationReviewVerified:true}
}
