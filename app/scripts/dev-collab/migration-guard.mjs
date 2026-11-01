import {readFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {resolve} from 'node:path'
import {verifyScopeMigrationProposal,SCOPE_MIGRATION_FILES} from './bootstrap-audit.mjs'
import {verifyStateBranchRuleset} from './state-rule-policy.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const STATE='prp-collab-state'
const PROPOSAL='proposal/prp-collab-state-scope-20261101'
const FILE='requirements/REQ-20261031-001.json'
const SHA=/^[a-f0-9]{40}$/
const OWNER='micor-cjj-spec'
const OWNER_ID=123868412
const FIELDS=['task_id','issue_number','title','status','depends_on','allowed_paths','claim']
const TITLES={
 'T-006':'只读任务看板与 Issue 投影',
 'T-007':'可信验收与 GitHub App 安全验证',
 'T-008':'CAS 并发及工作流边界测试',
 'T-009':'GPT 会话任务恢复、持久化断点与授权接管'
}
const ISSUE={'T-006':141,'T-007':142,'T-008':143,'T-009':146}
const DEPS={
 'T-006':['T-003'],
 'T-007':['T-003'],
 'T-008':['T-003','T-007','T-009'],
 'T-009':['T-003','T-007']
}
function requireRule(ok,code){if(!ok)throw new Error('MIGRATION_'+code)}

function verifyIndependentProposalReview(pr,reviews,proposalSha){
  requireRule(Array.isArray(reviews)&&reviews.length<100,'REVIEW_PAGINATION_INCOMPLETE')
  const latest=new Map()
  for(const review of reviews){
    const login=review?.user?.login
    const userId=review?.user?.id
    const submittedAt=Date.parse(review?.submitted_at)
    if(typeof login!=='string'||login.length===0||review?.user?.type!=='User'||
       !['COLLABORATOR','MEMBER'].includes(review?.author_association)||
       !Number.isSafeInteger(userId)||userId<=0||!Number.isFinite(submittedAt))continue
    const id=Number.isSafeInteger(review.id)?review.id:0
    const previous=latest.get(userId)
    if(!previous||submittedAt>previous.submittedAt||
       (submittedAt===previous.submittedAt&&id>previous.id)){
      latest.set(userId,{login,userId,state:review.state,
        commitId:review.commit_id,submittedAt,id})
    }
  }
  const independent=[...latest.values()].filter(r=>
    r.login!==OWNER&&r.userId!==OWNER_ID&&
    r.login!==pr?.user?.login&&r.userId!==pr?.user?.id)
  requireRule(!independent.some(r=>
    r.state==='CHANGES_REQUESTED'&&r.commitId===proposalSha),
    'INDEPENDENT_REVIEW_CHANGES_REQUESTED')
  const approved=independent.find(r=>
    r.state==='APPROVED'&&r.commitId===proposalSha)
  requireRule(approved,'INDEPENDENT_REVIEW_REQUIRED')
  return Object.freeze({reviewer:approved.login,commit_id:proposalSha})
}
function keys(x){return Object.keys(x).sort().join('\n')}
function same(x,y){return JSON.stringify(x)===JSON.stringify(y)}

/** Exact V0-to-V1 delta: no secret fields or retrospective task approvals. */
export function verifyExactTaskDelta(before,after){
  verifyScopeMigrationProposal(before,after)
  requireRule(keys(before)===keys(after),'TOP_LEVEL_FIELD_CHANGE')
  for(let i=0;i<5;i++)
    requireRule(keys(before.tasks[i])===keys(after.tasks[i]),'HISTORIC_FIELD_CHANGE')
  const expected=JSON.parse(JSON.stringify(before))
  expected.version=1
  expected.updated_at=after.updated_at
  expected.tasks[4].allowed_paths=['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']
  expected.tasks[4].depends_on=['T-001','T-002','T-003','T-004','T-006','T-007','T-008','T-009']
  for(const id of ['T-006','T-007','T-008','T-009']){
    const t=after.tasks.find(x=>x.task_id===id)
    requireRule(keys(t)===FIELDS.slice().sort().join('\n'),'NEW_TASK_FIELDS')
    expected.tasks.push({task_id:id,issue_number:ISSUE[id],title:TITLES[id],
      status:'READY',depends_on:DEPS[id],allowed_paths:SCOPE_MIGRATION_FILES[id],claim:null})
  }
  requireRule(same(expected,after),'UNAPPROVED_TASK_DELTA')
  return {strict_delta_valid:true,task_count:after.tasks.length,
    from_version:before.version,to_version:after.version,changed_state_file:FILE}
}

/** Read-only attestation; never authorizes merge, task acceptance or deployment. */
export function verifyMigrationEvidence(input){
  const {before,after,pr,prFiles,reviews,rule,appId,ruleId,
    stateSha,proposalSha,mode,approvalPhrase,appInstallation}=input
  requireRule(mode==='verify'||mode==='apply','MODE')
  requireRule(SHA.test(stateSha)&&SHA.test(proposalSha)&&stateSha!==proposalSha,'SHA')
  requireRule(pr?.number===144 && pr?.state==='open' &&
    pr?.base?.ref===STATE && pr?.head?.ref===PROPOSAL &&
    pr?.base?.repo?.full_name===REPO && pr?.head?.repo?.full_name===REPO &&
    pr?.head?.sha===proposalSha &&
    pr?.user?.login===OWNER && pr?.user?.id===OWNER_ID,'PROPOSAL_PR_IDENTITY')
  requireRule(pr.changed_files===1 && Array.isArray(prFiles) &&
    prFiles.length===1 && prFiles[0]?.filename===FILE &&
    prFiles[0]?.status==='modified','PROPOSAL_FILES')
  requireRule(Number.isSafeInteger(ruleId)&&ruleId>0&&rule?.id===ruleId,'RULESET_ID')
  const rulePolicy=verifyStateBranchRuleset(rule,appId)
  const delta=verifyExactTaskDelta(before,after)
  if(mode==='apply'){
    requireRule(pr.draft===false,'PROPOSAL_STILL_DRAFT')
    requireRule(approvalPhrase==='APPLY-REQ-20261031-001-V1','EXPLICIT_OWNER_APPROVAL')
    requireRule(appInstallation?.total_count===1 &&
      appInstallation?.repositories?.length===1 &&
      appInstallation.repositories[0]?.full_name===REPO,'APP_INSTALLATION_SCOPE')
  }
  const independentReview=mode==='apply'
    ? verifyIndependentProposalReview(pr,reviews,proposalSha) : null
  return {status:mode==='apply'?'APP_WRITE_PRECONDITIONS_OBSERVED':'READ_ONLY_PRECHECK_PASSED',
    mode,expected_state_sha:stateSha,expected_proposal_sha:proposalSha,
    proposal_pr:144,rule_id:ruleId,...delta,
    designated_app_bypass_verified:rulePolicy.appCanBypass,
    bypass_actor_list_visible:rulePolicy.bypassActorsVerified,
    independent_review_verified:independentReview!==null,
    independent_reviewer:independentReview?.reviewer??null,
    state_write_authorized_by_this_report:false,production_deploy_authorized:false}
}

if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try{
    if(process.argv.length!==9)throw new Error('MIGRATION_EXPECTED_SEVEN_FILES')
    const [oldFile,newFile,prFile,filesFile,ruleFile,reviewsFile,appReposFile]=process.argv.slice(2)
    const read=p=>JSON.parse(readFileSync(p,'utf8'))
    const e=process.env
    const report=verifyMigrationEvidence({
      before:read(oldFile),after:read(newFile),pr:read(prFile),prFiles:read(filesFile),
      reviews:read(reviewsFile),rule:read(ruleFile),appInstallation:appReposFile==='-'?null:read(appReposFile),
      appId:Number(e.COLLAB_APP_ID),ruleId:Number(e.COLLAB_RULESET_ID),
      stateSha:e.COLLAB_EXPECTED_STATE_SHA,proposalSha:e.COLLAB_EXPECTED_PROPOSAL_SHA,
      mode:e.COLLAB_MIGRATION_MODE,approvalPhrase:e.COLLAB_APPROVAL_PHRASE})
    process.stdout.write(JSON.stringify(report,null,2)+'\n')
  }catch(e){
    console.error('PRP_MIGRATION_GUARD_ERROR='+(e?.code||e?.message||'FAILED'))
    process.exitCode=1
  }
}
