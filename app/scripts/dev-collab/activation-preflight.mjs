import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
/**
 * Read-only preflight for the ChatGPT Issue-driven no-click controller.
 * A pass means prerequisites are observable, NEVER authorization to mutate,
 * merge, accept a task or deploy.
 */
import { execFileSync } from 'node:child_process'
import { verifyStateBranchRuleset } from './state-rule-policy.mjs'
import { validateSnapshot, requireMigratedLiveState } from './core.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const REF='prp-collab-state'
const REQ='REQ-20261031-001'
const ENV_NAME='prp-collab-automation'
const MAIN_RULESET_ID=24968649
const EXPECTED_APP_ID=5561446
const STATE_RULESET_ID=26294671
const SHA=/^[a-f0-9]{40}$/
// Reviewed V1 seed (V10/V17 definition equality), never a pin on the live version.
const V1_TASK_DEFINITIONS=[
  {
    "task_id": "T-001",
    "issue_number": 133,
    "title": "任务状态模型、依赖校验与并发安全核心",
    "depends_on": [],
    "allowed_paths": [
      "app/scripts/dev-collab/core.mjs",
      "app/scripts/dev-collab/core.test.mjs"
    ]
  },
  {
    "task_id": "T-002",
    "issue_number": 134,
    "title": "GitHub 需求与任务模板、PR 规范",
    "depends_on": [],
    "allowed_paths": [
      ".github/ISSUE_TEMPLATE/",
      ".github/PULL_REQUEST_TEMPLATE.md"
    ]
  },
  {
    "task_id": "T-003",
    "issue_number": 135,
    "title": "共享状态协调器与 GitHub Actions",
    "depends_on": [
      "T-001",
      "T-007",
      "T-009"
    ],
    "allowed_paths": [
      "app/scripts/dev-collab/coordinator-cli.mjs",
      "app/scripts/dev-collab/state-transaction.sh",
      ".github/workflows/prp-collab-coordinator.yml"
    ]
  },
  {
    "task_id": "T-004",
    "issue_number": 136,
    "title": "验收、安全回归和跨会话操作手册",
    "depends_on": [
      "T-001",
      "T-003"
    ],
    "allowed_paths": [
      "app/scripts/dev-collab/coordinator-cli.test.mjs",
      "app/docs/dev-collab/"
    ]
  },
  {
    "task_id": "T-005",
    "issue_number": 137,
    "title": "集成审查与端到端验收",
    "depends_on": [
      "T-001",
      "T-002",
      "T-003",
      "T-004",
      "T-006",
      "T-007",
      "T-008",
      "T-009"
    ],
    "allowed_paths": [
      "app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md"
    ]
  },
  {
    "task_id": "T-006",
    "issue_number": 141,
    "title": "只读任务看板与 Issue 投影",
    "depends_on": [
      "T-003"
    ],
    "allowed_paths": [
      ".github/workflows/prp-collab-board.yml",
      ".github/workflows/prp-collab-issue-projection.yml",
      "app/scripts/dev-collab/board-workflow.test.mjs",
      "app/scripts/dev-collab/board.mjs",
      "app/scripts/dev-collab/board.test.mjs",
      "app/scripts/dev-collab/projection-cli.mjs",
      "app/scripts/dev-collab/projection-workflow.test.mjs",
      "app/scripts/dev-collab/projection.mjs",
      "app/scripts/dev-collab/projection.test.mjs"
    ]
  },
  {
    "task_id": "T-007",
    "issue_number": 142,
    "title": "可信验收与 GitHub App 安全验证",
    "depends_on": [
      "T-001"
    ],
    "allowed_paths": [
      "app/scripts/dev-collab/activation-preflight.mjs",
      "app/scripts/dev-collab/activation-preflight.test.mjs",
      "app/scripts/dev-collab/bootstrap-audit.mjs",
      "app/scripts/dev-collab/bootstrap-audit.test.mjs",
      "app/scripts/dev-collab/review-context.mjs",
      "app/scripts/dev-collab/review-context.test.mjs",
      "app/scripts/dev-collab/review-gate.mjs",
      "app/scripts/dev-collab/review-gate.test.mjs",
      "app/scripts/dev-collab/review-provenance.mjs",
      "app/scripts/dev-collab/review-provenance.test.mjs",
      "app/scripts/dev-collab/state-rule-policy.mjs",
      "app/scripts/dev-collab/state-rule-policy.test.mjs"
    ]
  },
  {
    "task_id": "T-008",
    "issue_number": 143,
    "title": "CAS 并发及工作流边界测试",
    "depends_on": [
      "T-003",
      "T-007",
      "T-009"
    ],
    "allowed_paths": [
      "app/scripts/dev-collab/git-cas.test.mjs",
      "app/scripts/dev-collab/git-transaction.test.mjs",
      "app/scripts/dev-collab/integration-ci-boundary.test.mjs",
      "app/scripts/dev-collab/workflow-boundary.test.mjs",
      "app/scripts/dev-collab/workflow-contract.test.mjs"
    ]
  },
  {
    "task_id": "T-009",
    "issue_number": 146,
    "title": "GPT 会话任务恢复、持久化断点与授权接管",
    "depends_on": [
      "T-001",
      "T-007"
    ],
    "allowed_paths": [
      "app/scripts/dev-collab/checkpoint-recovery.test.mjs",
      "app/scripts/dev-collab/recovery-auth.mjs",
      "app/scripts/dev-collab/recovery.mjs",
      "app/scripts/dev-collab/recovery.test.mjs"
    ]
  }
]
function hasExactV1Definitions(snapshot){
  return snapshot.tasks.length===V1_TASK_DEFINITIONS.length && V1_TASK_DEFINITIONS.every(expected=>{
    const t=snapshot.tasks.find(x=>x.task_id===expected.task_id)
    return t?.issue_number===expected.issue_number && t.title===expected.title &&
      JSON.stringify(t.depends_on)===JSON.stringify(expected.depends_on) &&
      JSON.stringify(t.allowed_paths)===JSON.stringify(expected.allowed_paths)
  })
}

function api(path,token) {
  const options={encoding:'utf8',maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']}
  if(token) options.env={...process.env,GH_TOKEN:token}
  return JSON.parse(execFileSync('gh',['api','repos/'+REPO+'/'+path],options))
}
function get(path,token) {
  try { return {data:api(path,token)} }
  catch { return {error:'API_UNAVAILABLE_OR_ACCESS_DENIED'} }
}
function check(value,code,blocks) {if(!value)blocks.push(code)}
function names(collection,key) {
  return Array.isArray(collection?.[key])?collection[key].map(x=>x?.name):[]
}
export function evaluateActivationEvidence(data, options={}) {
  // Preserve the original one-shot V0 migration gate; V1 checks are read-only.
  const phase=options?.phase??'bootstrap_v0'
  const blockers=[]
  check(phase==='bootstrap_v0'||phase==='active_v1',
    'UNKNOWN_PREFLIGHT_PHASE',blockers)
  const {main,stateBranch,rule,appRule,mainRule,appId,rulesetId,
    environment,branchPolicies,environmentSecrets,environmentVariables,snapshot,
    headSha,installationRepos,publicationHold}=data??{}

  check(main?.name==='main'&&main?.protected===true,'MAIN_NOT_PROTECTED',blockers)
  check(mainRule?.id===MAIN_RULESET_ID&&mainRule?.target==='branch'&&
    mainRule?.enforcement==='active','MAIN_RULESET_NOT_ACTIVE',blockers)
  const mainRefs=mainRule?.conditions?.ref_name
  check(Array.isArray(mainRefs?.include)&&mainRefs.include.length===1&&
    mainRefs.include[0]==='~DEFAULT_BRANCH'&&
    Array.isArray(mainRefs.exclude)&&mainRefs.exclude.length===0,
    'MAIN_RULESET_TARGET_NOT_EXACT',blockers)
  const mainTypes=new Set((mainRule?.rules??[]).map(x=>x?.type))
  check(['deletion','non_fast_forward','pull_request','required_status_checks']
    .every(x=>mainTypes.has(x)),'MAIN_RULESET_GUARDS_MISSING',blockers)
  const requiredRule=mainRule?.rules?.find(x=>x?.type==='required_status_checks')?.parameters
  const requiredChecks=requiredRule?.required_status_checks
  const expectedChecks=['backend-tests','web-build','mobile-build',
    'db-migration-integration','video-db-integration','impact-report']
  check(requiredRule?.strict_required_status_checks_policy===true &&
    Array.isArray(requiredChecks) && requiredChecks.length===expectedChecks.length &&
    expectedChecks.every(context=>requiredChecks.some(x=>
      x?.context===context && x?.integration_id===15368)),
    'MAIN_REQUIRED_CHECKS_NOT_EXACT',blockers)
  check(Array.isArray(mainRule?.bypass_actors)&&mainRule.bypass_actors.length===0,
    'MAIN_BYPASS_ACTORS_NOT_EMPTY_OR_VISIBLE',blockers)

  check(stateBranch?.name===REF&&stateBranch?.protected===true,
    'STATE_BRANCH_UNPROTECTED',blockers)
  check(SHA.test(headSha||'')&&stateBranch?.commit?.sha===headSha,
    'STATE_REF_UNVERIFIED',blockers)
  if(phase==='bootstrap_v0'){
    check(headSha==='062036f7021e215ffbfdcbf5689d207a0549b68b',
      'STATE_NOT_PINNED_V0',blockers)
  }else if(phase==='active_v1'){
    // Non-replayable historic migration SHA must not be treated as current live V1.
    check(SHA.test(headSha||'')&&headSha!=='062036f7021e215ffbfdcbf5689d207a0549b68b',
      'STATE_STILL_PINNED_TO_V0',blockers)
  }
  check(appId===EXPECTED_APP_ID,'APP_ID_MISMATCH',blockers)
  check(rulesetId===STATE_RULESET_ID&&rule?.id===STATE_RULESET_ID,
    'STATE_RULESET_ID_MISMATCH',blockers)
  try {
    const policy=verifyStateBranchRuleset(rule,appId)
    check(policy.bypassActorsVerified===true,
      'STATE_RULESET_BYPASS_LIST_NOT_VISIBLE',blockers)
  }catch(e){blockers.push('STATE_RULESET_'+(e.code??'UNVERIFIED'))}
  try {
    check(appRule?.id===STATE_RULESET_ID,'APP_TOKEN_RULESET_ID_MISMATCH',blockers)
    const appPolicy=verifyStateBranchRuleset(appRule,appId)
    check(appPolicy.appCanBypass===true && appRule?.current_user_can_bypass==='always',
      'APP_TOKEN_STATE_BYPASS_NOT_VERIFIED',blockers)
  }catch(e){blockers.push('APP_TOKEN_RULESET_'+(e.code??'UNVERIFIED'))}

  const protections=environment?.protection_rules
  check(environment?.name===ENV_NAME&&Array.isArray(protections),
    'AUTO_ENV_NOT_FOUND_OR_UNREADABLE',blockers)
  check(environment?.can_admins_bypass===false,
    'AUTO_ENV_ADMIN_BYPASS_ENABLED_OR_UNVERIFIED',blockers)
  check(Array.isArray(protections)&&
    protections.every(x=>x?.type==='branch_policy'),
    'AUTO_ENV_HAS_MANUAL_APPROVAL_GATE',blockers)
  const deploy=environment?.deployment_branch_policy
  check(deploy?.protected_branches===false&&deploy?.custom_branch_policies===true,
    'AUTO_ENV_BRANCH_POLICY_NOT_CUSTOM_MAIN_ONLY',blockers)
  check(branchPolicies?.total_count===1&&
    Array.isArray(branchPolicies.branch_policies)&&
    branchPolicies.branch_policies.length===1&&
    branchPolicies.branch_policies[0]?.name==='main',
    'AUTO_ENV_BRANCH_POLICY_NOT_EXACT_MAIN',blockers)

  check(names(environmentSecrets,'secrets').includes('PRP_COLLAB_APP_PRIVATE_KEY'),
    'AUTO_ENV_APP_PRIVATE_KEY_SECRET_MISSING',blockers)
  const vars=Array.isArray(environmentVariables?.variables)?
    environmentVariables.variables:[]
  const variable=name=>vars.find(x=>x?.name===name)?.value
  check(typeof variable('PRP_COLLAB_APP_CLIENT_ID')==='string'&&
    variable('PRP_COLLAB_APP_CLIENT_ID').length>0,
    'AUTO_ENV_APP_CLIENT_ID_MISSING',blockers)
  check(String(variable('PRP_COLLAB_APP_ID')??'')===String(appId),
    'AUTO_ENV_APP_ID_MISMATCH',blockers)
  check(String(variable('PRP_COLLAB_RULESET_ID')??'')===String(rule?.id),
    'AUTO_ENV_RULESET_ID_MISMATCH',blockers)

  try {
    validateSnapshot(snapshot)
    check(snapshot.requirement_id===REQ,'WRONG_REQUIREMENT',blockers)
    if(phase==='bootstrap_v0'){
      check(snapshot.version===0&&snapshot.status==='ACTIVE'&&
        snapshot.tasks.length===5&&snapshot.tasks.every(t=>
          t.claim==null&&t.status==='READY')&&
        snapshot.processed_requests.length===0,
        'NOT_CLEAN_INITIAL_PILOT_STATE',blockers)
    }else if(phase==='active_v1'){
      // Check actual V1 task/Issue identities instead of inferring migration from version.
      requireMigratedLiveState(snapshot)
      check(hasExactV1Definitions(snapshot),'MIGRATED_TASK_DEFINITION_MISMATCH',blockers)
      check(snapshot.status==='ACTIVE','MIGRATED_REQUIREMENT_NOT_ACTIVE',blockers)
    }
  }catch{blockers.push(phase==='active_v1'?
    'INVALID_OR_UNMIGRATED_STATE_SNAPSHOT':'INVALID_STATE_SNAPSHOT')}

  check(installationRepos?.total_count===1&&
    installationRepos?.repositories?.length===1&&
    installationRepos.repositories[0]?.full_name===REPO,
    'DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED',blockers)
  check(publicationHold?.schema_version===1&&
    typeof publicationHold.reason==='string'&&publicationHold.reason.trim().length>0,
    'PUBLICATION_HOLD_MISSING_OR_INVALID',blockers)

  return {
    repository:REPO,requirement_id:REQ,phase,
    state_sha:SHA.test(headSha||'')?headSha:null,
    status:blockers.length===0?'PRECONDITIONS_OBSERVED':'NO_GO',
    blockers,allow_claim:false,allow_merge:false,allow_deploy:false,
    note:phase==='active_v1'?
      'Read-only V1 observation is not task approval, an authorized state write, a main merge or production deployment. Current operations still require an owner-authored Issue and trusted workflow.':
      'This read-only report never authorizes a state write. The first live operation still requires an explicit owner-created Issue request and must pass the trusted Issue workflow.'
  }
}
function run() {
  if(process.argv.length!==2) throw Error('NO_ARGUMENTS_ACCEPTED')
  const main=get('branches/main').data
  const stateBranch=get('branches/'+REF).data
  const appId=Number(process.env.PRP_COLLAB_APP_ID)
  const rulesetId=process.env.PRP_COLLAB_RULESET_ID
  const rule=/^[1-9]\d*$/.test(rulesetId??'')?get('rulesets/'+rulesetId).data:null
  const appRule=/^[1-9]\d*$/.test(rulesetId??'')&&process.env.PRP_COLLAB_APP_TOKEN
    ?get('rulesets/'+rulesetId,process.env.PRP_COLLAB_APP_TOKEN).data
    :null
  const mainRule=get('rulesets/'+MAIN_RULESET_ID).data
  const environment=get('environments/'+ENV_NAME).data
  const branchPolicies=get('environments/'+ENV_NAME+'/deployment-branch-policies').data
  const environmentSecrets=get('environments/'+ENV_NAME+'/secrets').data
  const environmentVariables=get('environments/'+ENV_NAME+'/variables').data
  const headSha=stateBranch?.commit?.sha
  let snapshot=null
  if(SHA.test(headSha||'')){
    try {
      // Read the exact verified remote state commit, not a potentially stale local checkout.
      const file=api('contents/requirements/'+REQ+'.json?ref='+headSha)
      if(file?.encoding!=='base64'||typeof file.content!=='string')
        throw Error('STATE_CONTENT_UNREADABLE')
      snapshot=JSON.parse(Buffer.from(file.content,'base64').toString('utf8'))
    }catch{/* no local object: reject rather than assume state */}
  }
  let publicationHold=null
  try{
    const file=api('contents/app/deploy/publication-hold.json?ref=main')
    publicationHold=JSON.parse(Buffer.from(file.content,'base64').toString('utf8'))
  }catch{/* missing hold is a blocker */}
  let installationRepos=null
  if(process.env.PRP_COLLAB_APP_TOKEN){
    try{
      installationRepos=JSON.parse(execFileSync('gh',['api','installation/repositories'],
        {encoding:'utf8',maxBuffer:1024*1024,
         env:{...process.env,GH_TOKEN:process.env.PRP_COLLAB_APP_TOKEN},
         stdio:['ignore','pipe','pipe']}))
    }catch{/* refuse to infer app access */}
  }
  // V0 checks remain exact and fail closed; migrated states use a separate V1 contract.
  const phase=Number.isInteger(snapshot?.version)&&snapshot.version>=1?
    'active_v1':'bootstrap_v0'
  const report=evaluateActivationEvidence({main,stateBranch,rule,appRule,mainRule,appId,
    rulesetId:Number(rulesetId),
    environment,branchPolicies,environmentSecrets,environmentVariables,snapshot,
    headSha,installationRepos,publicationHold},{phase})
  process.stdout.write(JSON.stringify(report,null,2)+'\n')
  if(report.status!=='PRECONDITIONS_OBSERVED')process.exitCode=2
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try{run()}catch{
    console.error('PRP_ACTIVATION_PREFLIGHT_ERROR=INVALID_INPUT_OR_API')
    process.exitCode=2
  }
}
