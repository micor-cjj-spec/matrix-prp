import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
#!/usr/bin/env node
/**
 * Read-only GitHub preflight. A pass means prerequisites are observable,
 * NEVER authorization to merge, deploy, or accept a task.
 */
import { execFileSync } from 'node:child_process'
import { verifyStateBranchRuleset } from './state-rule-policy.mjs'
import { validateSnapshot } from './core.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const REF='prp-collab-state'
const REQ='REQ-20261031-001'
const envName='prp-collab-controller'
const SHA=/^[a-f0-9]{40}$/

function api(path) {
  return JSON.parse(execFileSync('gh',['api','repos/'+REPO+'/'+path],
    {encoding:'utf8',maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']}))
}
function get(path) {
  try { return { data:api(path) } }
  catch { return { error:'API_UNAVAILABLE_OR_ACCESS_DENIED' } }
}
function check(value,code,blocks) {if(!value)blocks.push(code)}
export function evaluateActivationEvidence(data) {
  const blockers=[]
  const {main,stateBranch,rule,appId,environment,snapshot,headSha,installationRepos}=data??{}
  check(main?.name==='main'&&main?.protected===true,'MAIN_NOT_PROTECTED',blockers)
  check(stateBranch?.name===REF&&stateBranch?.protected===true,'STATE_BRANCH_UNPROTECTED',blockers)
  check(SHA.test(headSha)&&stateBranch?.commit?.sha===headSha,'STATE_REF_UNVERIFIED',blockers)
  try {
    validateSnapshot(snapshot)
    check(snapshot.requirement_id===REQ,'WRONG_REQUIREMENT',blockers)
    check(snapshot.version===0 && snapshot.status==='ACTIVE' &&
      snapshot.tasks.every(t=>t.claim==null && t.status==='READY') &&
      snapshot.processed_requests.length===0,'NOT_CLEAN_INITIAL_PILOT_STATE',blockers)
  }catch{blockers.push('INVALID_STATE_SNAPSHOT')}
  try { verifyStateBranchRuleset(rule,appId) }
  catch(e){blockers.push('STATE_RULESET_'+(e.code??'UNVERIFIED'))}
  const reviewers=environment?.protection_rules?.find(x=>x.type==='required_reviewers')
  check(environment?.name===envName && Array.isArray(reviewers?.reviewers) &&
    reviewers.reviewers.length>0,'ENVIRONMENT_REVIEW_NOT_VERIFIED',blockers)
  check(installationRepos?.total_count===1 &&
    installationRepos?.repositories?.length===1 &&
    installationRepos.repositories[0].full_name===REPO,
    'DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED',blockers)
  return {
    repository:REPO,requirement_id:REQ,
    state_sha:SHA.test(headSha)?headSha:null,
    status:blockers.length===0?'PRECONDITIONS_OBSERVED':'NO_GO',
    blockers,allow_claim:false,allow_merge:false,allow_deploy:false,
    note:'An administrator must independently approve the policy and a controlled live test. This report never grants activation.'
  }
}
function run() {
  if(process.argv.length!==2) throw Error('NO_ARGUMENTS_ACCEPTED')
  const main=get('branches/main').data
  const branch=get('branches/'+REF).data
  const appId=Number(process.env.PRP_COLLAB_APP_ID)
  const rulesetId=process.env.PRP_COLLAB_RULESET_ID
  const rule=/^[1-9]\d*$/.test(rulesetId??'')?get('rulesets/'+rulesetId).data:null
  const environment=get('environments/'+envName).data
  const headSha=branch?.commit?.sha
  let snapshot=null
  if(SHA.test(headSha)){
    try {
      const bytes=execFileSync('git',['show',headSha+':requirements/'+REQ+'.json'],
        {encoding:'utf8',maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']})
      snapshot=JSON.parse(bytes)
    } catch { /* no local object: reject rather than assume state */ }
  }
  // Requires an actual temporary app installation token, provided only as a runner
  // environment secret. Never print it or expose it in CLI arguments.
  let installationRepos=null
  if(process.env.PRP_COLLAB_APP_TOKEN){
    try {
      installationRepos=JSON.parse(execFileSync('gh',['api','installation/repositories'],
        {encoding:'utf8',maxBuffer:1024*1024,
         env:{...process.env,GH_TOKEN:process.env.PRP_COLLAB_APP_TOKEN},
         stdio:['ignore','pipe','pipe']}))
    } catch { /* refuse to infer app access */ }
  }
  const report=evaluateActivationEvidence({main,stateBranch:branch,rule,appId,
    environment,snapshot,headSha,installationRepos})
  process.stdout.write(JSON.stringify(report,null,2)+'\n')
  if(report.status!=='PRECONDITIONS_OBSERVED')process.exitCode=2
}
if (process.argv[1] && fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try {run()} catch {
    console.error('PRP_ACTIVATION_PREFLIGHT_ERROR=INVALID_INPUT_OR_API')
    process.exitCode=2
  }
}
