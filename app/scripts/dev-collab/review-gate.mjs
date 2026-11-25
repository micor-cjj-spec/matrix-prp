import { CollabError, validateSnapshot } from './core.mjs'
import { createHash } from 'node:crypto'

const SHA=/^[a-f0-9]{40}$/
export const REQUIRED_CHECKS=Object.freeze([
  'backend-tests', 'web-build', 'mobile-build', 'db-migration-integration',
  'video-db-integration', 'impact-report', 'dev-collab-contract'
])

function check(ok,code){ if(!ok) throw new CollabError(code) }
function exactIso(s){ return typeof s==='string' && Number.isFinite(Date.parse(s)) }

// Full owner-observed policy for the existing integration ref. A drift or a
// redacted bypass list is a blocker, never grounds to request administration write.
const INTEGRATION_POLICY={
  "id": 28050327,
  "name": "protect-collab-integration",
  "target": "branch",
  "source_type": "Repository",
  "source": "micor-cjj-spec/matrix-prp",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "refs/heads/integrate/REQ-20261031-001"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": false,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
        "required_status_checks": [
          {
            "context": "backend-tests",
            "integration_id": 15368
          },
          {
            "context": "web-build",
            "integration_id": 15368
          },
          {
            "context": "mobile-build",
            "integration_id": 15368
          },
          {
            "context": "db-migration-integration",
            "integration_id": 15368
          },
          {
            "context": "video-db-integration",
            "integration_id": 15368
          },
          {
            "context": "impact-report",
            "integration_id": 15368
          },
          {
            "context": "dev-collab-contract",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c",
  "created_at": "2026-11-25T05:47:06.929Z",
  "updated_at": "2026-11-25T05:47:07.076Z",
  "bypass_actors": []
}
const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v)
const digest=v=>createHash('sha256').update(canonical(v)).digest('hex')
const OWNER_RULESET_PREFIX='PRP_RULESET_ATTESTATION_V1:'
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const TASK_ID=/^T-[0-9]{3}$/
const normalizeTime=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Date(v).toISOString():null
function verifyPolicySnapshot(requirementId,rule,bypassActors){
  check(requirementId==='REQ-20261031-001','INTEGRATION_POLICY_NOT_REGISTERED')
  check(Array.isArray(bypassActors)&&bypassActors.length===0,'INTEGRATION_POLICY_BYPASS_UNVERIFIED')
  check(Object.keys(rule).every(k=>Object.hasOwn(INTEGRATION_POLICY,k)||k==='current_user_can_bypass'||k==='_links'),'INTEGRATION_POLICY_UNKNOWN_FIELDS')
  const actual=Object.fromEntries(Object.keys(INTEGRATION_POLICY).map(k=>[
    k,k==='bypass_actors'?bypassActors:k.endsWith('_at')&&exactIso(rule[k])?new Date(rule[k]).toISOString():rule[k]
  ]))
  check(canonical(actual)===canonical(INTEGRATION_POLICY),'INTEGRATION_POLICY_DRIFT')
  return Object.freeze({verified:true,rule_id:rule.id,revision:actual.updated_at})
}
export function verifyIntegrationPolicy(requirementId,rule){
  check(rule&&Array.isArray(rule.bypass_actors)&&rule.current_user_can_bypass==='never','INTEGRATION_POLICY_BYPASS_UNVERIFIED')
  return verifyPolicySnapshot(requirementId,rule,rule.bypass_actors)
}

/**
 * Create the compact note payload for a human owner who has just fetched the
 * complete Ruleset response in an owner-authorized context. This is a claim by
 * the authenticated workflow dispatcher, not a cryptographic signature.
 * Never build it from the redacted GITHUB_TOKEN response.
 */
export function buildOwnerRulesetAttestation(rule,binding){
  const allowed=['requestId','action','requirementId','taskId','prNumber','headSha','stateVersion','mainSha','observedAt']
  check(binding&&typeof binding==='object'&&!Array.isArray(binding)&&
    Object.keys(binding).every(k=>allowed.includes(k))&&
    ['requestId','action','requirementId','taskId','prNumber','headSha','stateVersion','mainSha'].every(k=>Object.hasOwn(binding,k)),
    'OWNER_RULESET_ATTESTATION_INPUT')
  check(rule&&Array.isArray(rule.bypass_actors),'OWNER_RULESET_FULL_EVIDENCE_REQUIRED')
  verifyPolicySnapshot(binding.requirementId,rule,rule.bypass_actors)
  const observedAt=normalizeTime(binding.observedAt??new Date().toISOString())
  check(observedAt,'OWNER_RULESET_ATTESTATION_TIME')
  check(UUID.test(binding.requestId)&&['accept','close'].includes(binding.action)&&
    binding.requirementId==='REQ-20261031-001'&&
    (binding.action==='accept'?TASK_ID.test(binding.taskId):binding.taskId===null)&&
    Number.isSafeInteger(binding.prNumber)&&binding.prNumber>0&&
    SHA.test(binding.headSha)&&Number.isSafeInteger(binding.stateVersion)&&binding.stateVersion>=1&&
    SHA.test(binding.mainSha),'OWNER_RULESET_ATTESTATION_BINDING')
  const body={
    schema_version:1,request_id:binding.requestId,action:binding.action,
    requirement_id:binding.requirementId,task_id:binding.taskId,
    pr_number:binding.prNumber,head_sha:binding.headSha,state_version:binding.stateVersion,
    expected_main_sha:binding.mainSha,ruleset_id:INTEGRATION_POLICY.id,
    rule_updated_at:normalizeTime(rule.updated_at),observed_at:observedAt,
    bypass_actors:rule.bypass_actors,policy_sha256:digest(INTEGRATION_POLICY)
  }
  check(body.rule_updated_at&&body.bypass_actors.length===0,'OWNER_RULESET_ATTESTATION_POLICY')
  const note=OWNER_RULESET_PREFIX+JSON.stringify(body)
  check(note.length<=2048,'OWNER_RULESET_ATTESTATION_SIZE')
  return note
}

/** Verify a fresh, owner-authenticated workflow_dispatch attestation when GitHub
 * redacts bypass_actors from the read-only runtime token. */
export function verifyOwnerAttestedIntegrationPolicy(requirementId,rule,note,binding,workflowRun,now=Date.now()){
  check(rule&&!Object.hasOwn(rule,'bypass_actors')&&rule.current_user_can_bypass==='never',
    'INTEGRATION_POLICY_BYPASS_UNVERIFIED')
  check(typeof note==='string'&&note.length<=2048&&note.startsWith(OWNER_RULESET_PREFIX),
    'OWNER_RULESET_ATTESTATION_REQUIRED')
  const raw=note.slice(OWNER_RULESET_PREFIX.length)
  let a
  try{a=JSON.parse(raw)}catch{throw new CollabError('OWNER_RULESET_ATTESTATION_JSON')}
  const keys=['schema_version','request_id','action','requirement_id','task_id','pr_number','head_sha',
    'state_version','expected_main_sha','ruleset_id','rule_updated_at','observed_at','bypass_actors','policy_sha256']
  check(a&&typeof a==='object'&&!Array.isArray(a)&&Object.keys(a).length===keys.length&&
    keys.every(k=>Object.hasOwn(a,k))&&JSON.stringify(a)===raw,'OWNER_RULESET_ATTESTATION_FIELDS')
  check(a.schema_version===1&&UUID.test(a.request_id)&&
    ['accept','close'].includes(a.action)&&a.requirement_id===requirementId&&
    (a.action==='accept'?TASK_ID.test(a.task_id):a.task_id===null)&&Number.isSafeInteger(a.pr_number)&&a.pr_number>0&&
    SHA.test(a.head_sha)&&Number.isSafeInteger(a.state_version)&&a.state_version>=1&&
    SHA.test(a.expected_main_sha)&&a.ruleset_id===INTEGRATION_POLICY.id&&
    normalizeTime(a.rule_updated_at)===normalizeTime(rule.updated_at)&&
    normalizeTime(a.observed_at)===a.observed_at&&Array.isArray(a.bypass_actors)&&a.bypass_actors.length===0&&
    a.policy_sha256===digest(INTEGRATION_POLICY),'OWNER_RULESET_ATTESTATION_POLICY')
  check(a.request_id===binding?.requestId&&a.action===binding?.action&&
    a.requirement_id===requirementId&&a.task_id===(binding?.taskId??null)&&
    a.pr_number===binding?.prNumber&&a.head_sha===binding?.headSha&&
    a.state_version===binding?.stateVersion&&a.expected_main_sha===binding?.mainSha,
    'OWNER_RULESET_ATTESTATION_BINDING')
  const created=Date.parse(workflowRun?.created_at),observed=Date.parse(a.observed_at)
  check(Number.isFinite(created)&&Number.isFinite(observed)&&
    observed<=created+30000&&created-observed<=300000&&
    now>=observed-30000&&now-observed<=600000,
    'OWNER_RULESET_ATTESTATION_EXPIRED')
  verifyPolicySnapshot(requirementId,{...rule,bypass_actors:a.bypass_actors},a.bypass_actors)
  return Object.freeze({verified:true,rule_id:rule.id,revision:normalizeTime(rule.updated_at),
    ownerAttested:true,observed_at:a.observed_at})
}

/**
 * Evidence verification is deliberately read-only. It cannot transition a task or
 * authorize deployment. Future acceptance mutations must re-fetch the evidence
 * under the reviewed workflow immediately before their atomic state update.
 */
export function verifyTaskEvidence(snapshot,taskId,evidence){
  validateSnapshot(snapshot)
  check(snapshot.status==='ACTIVE','REQUIREMENT_NOT_ACTIVE')
  const task=snapshot.tasks.find(t=>t.task_id===taskId)
  check(task,'UNKNOWN_TASK')
  check(task.status==='IN_REVIEW','TASK_NOT_IN_REVIEW')
  check(Number.isInteger(task.pr_number)&&task.pr_number>0&&SHA.test(task.head_sha),'MISSING_TASK_PR_EVIDENCE')
  check(evidence && typeof evidence==='object','MISSING_EVIDENCE')
  const {pr,branch,comparison,checks,files}=evidence
  const target='integrate/'+snapshot.requirement_id
  check(pr?.number===task.pr_number && pr?.head?.sha===task.head_sha,'WRONG_PR_OR_HEAD')
  verifyTaskChangedFiles(task,pr,files)
  check(pr?.base?.ref===target && pr?.base?.repo?.full_name==='micor-cjj-spec/matrix-prp','WRONG_INTEGRATION_BASE')
  check(pr?.head?.repo?.full_name==='micor-cjj-spec/matrix-prp','FOREIGN_HEAD_REPOSITORY')
  check(pr?.merged===true && exactIso(pr?.merged_at) && SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  check(branch?.name===target && branch?.protected===true && SHA.test(branch?.commit?.sha),'UNPROTECTED_INTEGRATION_BRANCH')
  check(comparison?.status==='ahead'||comparison?.status==='identical','MERGE_NOT_ON_BASE')
  check(Number.isInteger(comparison.behind_by)&&comparison.behind_by===0,'MERGE_NOT_ON_BASE')
  check(comparison.base_commit?.sha===pr.merge_commit_sha &&
    comparison.merge_base_commit?.sha===pr.merge_commit_sha &&
    comparison.commits!==undefined,'COMPARE_PROVENANCE_MISMATCH')
  check(checks && Number.isInteger(checks.total_count) && checks.total_count===checks.check_runs?.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  verifyCheckSet(checks,task.head_sha)
  return Object.freeze({
    task_id:taskId, pr_number:task.pr_number, head_sha:task.head_sha,
    integration_sha:branch.commit.sha, merge_commit_sha:pr.merge_commit_sha,
    checks:REQUIRED_CHECKS.length, verified:true
  })
}

const CRITICAL_WORKFLOWS = new Set([
  '.github/workflows/ci.yml',
  '.github/workflows/feature-impact.yml',
  '.github/workflows/prp-dev-collab-contract.yml'
])
const filePath = s => typeof s==='string' && s.length>0 &&
  !s.startsWith('/') && !s.includes('\\') && !s.split('/').includes('..')
function withinScope(file,scopes){
  return scopes.some(s=>s===file || (s.endsWith('/') && file.startsWith(s)))
}
export function verifyTaskChangedFiles(task,pr,files){
  check(Number.isInteger(pr?.changed_files) && pr.changed_files>0 &&
    pr.changed_files<=100 && Array.isArray(files) && files.length===pr.changed_files,
    'INCOMPLETE_PR_FILE_LIST')
  check(Array.isArray(task?.allowed_paths) && task.allowed_paths.length>0,'TASK_HAS_NO_WRITE_SCOPE')
  const seen=new Set()
  for(const file of files){
    const name=file?.filename
    check(filePath(name) && !seen.has(name),'INVALID_OR_DUPLICATE_PR_FILE')
    seen.add(name)
    check(!CRITICAL_WORKFLOWS.has(name),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
    check(withinScope(name,task.allowed_paths),'TASK_FILE_OUTSIDE_SCOPE')
    if(file.status==='renamed'){
      check(!CRITICAL_WORKFLOWS.has(file.previous_filename),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
      check(filePath(file.previous_filename) && withinScope(file.previous_filename,task.allowed_paths),
        'RENAME_SOURCE_OUTSIDE_SCOPE')
    }
  }
  return Object.freeze({verified:true,files:seen.size})
}

function verifyCheckSet(checks,sha){
  check(checks && Number.isInteger(checks.total_count) &&
    Array.isArray(checks.check_runs) &&
    checks.total_count === checks.check_runs.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  const evidenceMap=new Map()
  for(const run of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(run?.name) || run?.app?.slug!=='github-actions')continue
    const previous=evidenceMap.get(run.name)
    check(Number.isSafeInteger(run.id) && run.id>0,'INVALID_CHECK_ID')
    if(!previous||run.id>previous.id) {
      evidenceMap.set(run.name,run)
    }
  }
  for(const name of REQUIRED_CHECKS){
    const run=evidenceMap.get(name)
    check(run,'CHECK_MISSING_'+name)
    check(run.head_sha===sha&&run.status==='completed'&&run.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
  }
  return true
}

export function verifyRequirementClose(snapshot, acceptance){
  validateSnapshot(snapshot)
  check(snapshot.status==='ACTIVE','REQUIREMENT_NOT_ACTIVE')
  check(snapshot.tasks.every(t=>t.status==='DONE'),'INCOMPLETE_REQUIREMENT')
  check(acceptance?.actorIsRepositoryOwner===true,'OWNER_APPROVAL_REQUIRED')
  check(acceptance?.explicitAcceptance===true,'EXPLICIT_ACCEPTANCE_REQUIRED')
  check(acceptance?.integrationReviewVerified===true,'INTEGRATION_REVIEW_REQUIRED')
  return Object.freeze({requirement_id:snapshot.requirement_id,ready_to_close:true,version:snapshot.version})
}


// A squash result need not contain the dev commit in its ancestry. It must
// contain the exact tree that all seven trusted jobs actually checked out.
export function hasDevAncestry(comparison,sha){
  return (comparison?.status==='ahead'||comparison?.status==='identical') &&
    comparison.behind_by===0 && comparison.base_commit?.sha===sha &&
    comparison.merge_base_commit?.sha===sha && Array.isArray(comparison.commits)
}
export function verifySquashRelease(pr,command,evidence){
  const {mergeCommit,testCommit,checkouts,workflowBlobs}=evidence??{}
  const base=pr?.base?.sha, head=command.head_sha
  check(SHA.test(base||'') && base!==head && pr?.base?.repo?.id===1261866723 &&
    pr?.head?.repo?.id===1261866723,'SQUASH_PR_BINDING')
  check(mergeCommit?.sha===pr.merge_commit_sha && mergeCommit.sha!==head &&
    Array.isArray(mergeCommit.parents) && mergeCommit.parents.length===1 &&
    mergeCommit.parents[0]?.sha===base && SHA.test(mergeCommit.tree?.sha||''),'SQUASH_COMMIT_BINDING')
  check(SHA.test(testCommit?.sha||'') && testCommit.sha!==mergeCommit.sha &&
    testCommit.sha!==head && testCommit.sha!==base &&
    Array.isArray(testCommit.parents) && testCommit.parents.length===2 &&
    testCommit.parents[0]?.sha===base && testCommit.parents[1]?.sha===head &&
    testCommit.tree?.sha===mergeCommit.tree.sha,'SQUASH_TEST_TREE_MISMATCH')
  check(Array.isArray(checkouts) && checkouts.length===REQUIRED_CHECKS.length &&
    new Set(checkouts.map(x=>x?.name)).size===REQUIRED_CHECKS.length &&
    new Set(checkouts.map(x=>x?.jobId)).size===REQUIRED_CHECKS.length &&
    checkouts.every(x=>REQUIRED_CHECKS.includes(x?.name)&&Number.isSafeInteger(x.jobId)&&
      x.jobId>0&&x.sha===testCommit.sha),'SQUASH_CHECKOUT_SET_MISMATCH')
  check(workflowBlobs && Object.keys(workflowBlobs).length===CRITICAL_WORKFLOWS.size &&
    [...CRITICAL_WORKFLOWS].every(path=>{
      const b=workflowBlobs[path]
      return Array.isArray(b)&&b.length===3&&SHA.test(b[0]||'')&&b.every(x=>x===b[0])
    }),'SQUASH_WORKFLOW_BLOB_MISMATCH')
  return Object.freeze({verified:true,test_sha:testCommit.sha,tree_sha:testCommit.tree.sha})
}

/**
 * Final close is allowed only after a same-repo dev -> main PR has merged.
 * Every accepted task must already have landed in the protected integration
 * history, which must be an ancestor of the exact tested dev PR head.
 * Read-only proof; this function NEVER writes the state or grants release.
 */
export function verifyIntegrationRelease(snapshot,command,proof){
  validateSnapshot(snapshot)
  check(snapshot.tasks.every(t=>t.status==='DONE'),'INCOMPLETE_REQUIREMENT')
  check(Number.isInteger(command.pr_number) && SHA.test(command.head_sha),'MISSING_INTEGRATION_PR')
  const {pr,branch,comparison,checks,integrationBranch,integrationComparison,
    mainAncestryComparison,squashProof}=proof ?? {}
  const repo='micor-cjj-spec/matrix-prp'
  const integration='integrate/'+snapshot.requirement_id
  check(pr?.number===command.pr_number && pr?.head?.sha===command.head_sha,'WRONG_PR_OR_HEAD')
  check(pr?.head?.ref==='dev' && pr?.head?.repo?.full_name===repo &&
        pr?.base?.ref==='main' && pr?.base?.repo?.full_name===repo,
        'WRONG_MAIN_RELEASE_TARGET')
  check(pr?.merged===true && exactIso(pr?.merged_at) &&
        SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  check(branch?.name==='main' && branch?.protected===true &&
        SHA.test(branch?.commit?.sha),'MAIN_NOT_PROTECTED')
  check((comparison?.status==='ahead'||comparison?.status==='identical') &&
        comparison.behind_by===0 &&
        comparison.base_commit?.sha===pr.merge_commit_sha &&
        comparison.merge_base_commit?.sha===pr.merge_commit_sha &&
        Array.isArray(comparison.commits),'MERGE_NOT_ON_BASE')
  // Preserve the existing ancestry proof. A legitimate squash needs a separate
  // exact tested-tree proof, never an assumption from a merged PR or green checks.
  if(!hasDevAncestry(mainAncestryComparison,command.head_sha)){
    check(squashProof,'DEV_HEAD_NOT_IN_MAIN_ANCESTRY')
    check(['behind','diverged'].includes(mainAncestryComparison?.status) &&
      Number.isInteger(mainAncestryComparison.behind_by) && mainAncestryComparison.behind_by>0 &&
      mainAncestryComparison.base_commit?.sha===command.head_sha &&
      SHA.test(mainAncestryComparison.merge_base_commit?.sha||'') &&
      Array.isArray(mainAncestryComparison.commits),'SQUASH_ANCESTRY_EVIDENCE_INVALID')
    verifySquashRelease(pr,command,squashProof)
  }
  check(integrationBranch?.name===integration &&
        integrationBranch?.protected===true &&
        SHA.test(integrationBranch?.commit?.sha),'INTEGRATION_BRANCH_NOT_PROTECTED')
  check((integrationComparison?.status==='ahead' ||
         integrationComparison?.status==='identical') &&
        integrationComparison.behind_by===0 &&
        integrationComparison.base_commit?.sha===integrationBranch.commit.sha &&
        integrationComparison.merge_base_commit?.sha===integrationBranch.commit.sha &&
        Array.isArray(integrationComparison.commits),
        'INTEGRATION_NOT_IN_DEV_ANCESTRY')
  verifyCheckSet(checks,command.head_sha)
  return Object.freeze({integration_pr:command.pr_number,verified:true,
    main_sha:branch.commit.sha,dev_head_sha:command.head_sha,
    accepted_integration_sha:integrationBranch.commit.sha})
}
