import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
/**
 * Read-only preflight for the ChatGPT Issue-driven no-click controller.
 * A pass means prerequisites are observable, NEVER authorization to mutate,
 * merge, accept a task or deploy.
 */
import { execFileSync } from 'node:child_process'
import { verifyStateBranchRuleset } from './state-rule-policy.mjs'
import { validateSnapshot } from './core.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const REF='prp-collab-state'
const REQ='REQ-20261031-001'
const ENV_NAME='prp-collab-automation'
const MAIN_RULESET_ID=24968649
const EXPECTED_APP_ID=5561446
const STATE_RULESET_ID=26294671
const SHA=/^[a-f0-9]{40}$/

function api(path) {
  return JSON.parse(execFileSync('gh',['api','repos/'+REPO+'/'+path],
    {encoding:'utf8',maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']}))
}
function get(path) {
  try { return {data:api(path)} }
  catch { return {error:'API_UNAVAILABLE_OR_ACCESS_DENIED'} }
}
function check(value,code,blocks) {if(!value)blocks.push(code)}
function names(collection,key) {
  return Array.isArray(collection?.[key])?collection[key].map(x=>x?.name):[]
}
export function evaluateActivationEvidence(data) {
  const blockers=[]
  const {main,stateBranch,rule,mainRule,appId,rulesetId,environment,branchPolicies,
    environmentSecrets,environmentVariables,snapshot,headSha,installationRepos,
    publicationHold}=data??{}

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
  check(Array.isArray(mainRule?.bypass_actors)&&mainRule.bypass_actors.length===0,
    'MAIN_BYPASS_ACTORS_NOT_EMPTY_OR_VISIBLE',blockers)

  check(stateBranch?.name===REF&&stateBranch?.protected===true,
    'STATE_BRANCH_UNPROTECTED',blockers)
  check(SHA.test(headSha||'')&&stateBranch?.commit?.sha===headSha,
    'STATE_REF_UNVERIFIED',blockers)
  check(headSha==='062036f7021e215ffbfdcbf5689d207a0549b68b',
    'STATE_NOT_PINNED_V0',blockers)
  check(appId===EXPECTED_APP_ID,'APP_ID_MISMATCH',blockers)
  check(rulesetId===STATE_RULESET_ID&&rule?.id===STATE_RULESET_ID,
    'STATE_RULESET_ID_MISMATCH',blockers)
  let policy=null
  try {
    policy=verifyStateBranchRuleset(rule,appId)
    check(policy.bypassActorsVerified===true,
      'STATE_RULESET_BYPASS_LIST_NOT_VISIBLE',blockers)
  }catch(e){blockers.push('STATE_RULESET_'+(e.code??'UNVERIFIED'))}

  const protections=environment?.protection_rules
  check(environment?.name===ENV_NAME&&Array.isArray(protections),
    'AUTO_ENV_NOT_FOUND_OR_UNREADABLE',blockers)
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
    check(snapshot.version===0&&snapshot.status==='ACTIVE'&&
      snapshot.tasks.length===5&&snapshot.tasks.every(t=>
        t.claim==null&&t.status==='READY')&&
      snapshot.processed_requests.length===0,
      'NOT_CLEAN_INITIAL_PILOT_STATE',blockers)
  }catch{blockers.push('INVALID_STATE_SNAPSHOT')}

  check(installationRepos?.total_count===1&&
    installationRepos?.repositories?.length===1&&
    installationRepos.repositories[0]?.full_name===REPO,
    'DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED',blockers)
  check(publicationHold?.schema_version===1&&
    typeof publicationHold.reason==='string'&&publicationHold.reason.trim().length>0,
    'PUBLICATION_HOLD_MISSING_OR_INVALID',blockers)

  return {
    repository:REPO,requirement_id:REQ,
    state_sha:SHA.test(headSha||'')?headSha:null,
    status:blockers.length===0?'PRECONDITIONS_OBSERVED':'NO_GO',
    blockers,allow_claim:false,allow_merge:false,allow_deploy:false,
    note:'This read-only report never authorizes a state write. The first live operation still requires an explicit owner-created Issue request and must pass the trusted Issue workflow.'
  }
}
function run() {
  if(process.argv.length!==2) throw Error('NO_ARGUMENTS_ACCEPTED')
  const main=get('branches/main').data
  const stateBranch=get('branches/'+REF).data
  const appId=Number(process.env.PRP_COLLAB_APP_ID)
  const rulesetId=process.env.PRP_COLLAB_RULESET_ID
  const rule=/^[1-9]\d*$/.test(rulesetId??'')?get('rulesets/'+rulesetId).data:null
  const mainRule=get('rulesets/'+MAIN_RULESET_ID).data
  const environment=get('environments/'+ENV_NAME).data
  const branchPolicies=get('environments/'+ENV_NAME+'/deployment-branch-policies').data
  const environmentSecrets=get('environments/'+ENV_NAME+'/secrets').data
  const environmentVariables=get('environments/'+ENV_NAME+'/variables').data
  const headSha=stateBranch?.commit?.sha
  let snapshot=null
  if(SHA.test(headSha||'')){
    try {
      const bytes=execFileSync('git',['show',headSha+':requirements/'+REQ+'.json'],
        {encoding:'utf8',maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']})
      snapshot=JSON.parse(bytes)
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
  const report=evaluateActivationEvidence({main,stateBranch,rule,mainRule,appId,
    rulesetId:Number(rulesetId),environment,branchPolicies,environmentSecrets,
    environmentVariables,snapshot,
    headSha,installationRepos,publicationHold})
  process.stdout.write(JSON.stringify(report,null,2)+'\n')
  if(report.status!=='PRECONDITIONS_OBSERVED')process.exitCode=2
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try{run()}catch{
    console.error('PRP_ACTIVATION_PREFLIGHT_ERROR=INVALID_INPUT_OR_API')
    process.exitCode=2
  }
}
