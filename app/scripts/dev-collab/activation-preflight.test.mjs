import test from 'node:test'
import assert from 'node:assert/strict'
import {evaluateActivationEvidence} from './activation-preflight.mjs'

const V0='062036f7021e215ffbfdcbf5689d207a0549b68b'
const REQ='REQ-20261031-001'
const REPO='micor-cjj-spec/matrix-prp'
const good=()=>({
 main:{name:'main',protected:true},
 mainRule:{id:24968649,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['~DEFAULT_BRANCH'],exclude:[]}},
  rules:[{type:'deletion'},{type:'non_fast_forward'},
   {type:'pull_request'},{type:'required_status_checks'}],
  bypass_actors:[]},
 stateBranch:{name:'prp-collab-state',protected:true,commit:{sha:V0}},
 headSha:V0,appId:5561446,rulesetId:26294671,
 rule:{id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  bypass_actors:[{actor_type:'Integration',actor_id:5561446,bypass_mode:'always'}]},
 environment:{name:'prp-collab-automation',protection_rules:[],
  deployment_branch_policy:{protected_branches:false,custom_branch_policies:true}},
 branchPolicies:{total_count:1,branch_policies:[{name:'main'}]},
 environmentSecrets:{total_count:1,secrets:[{name:'PRP_COLLAB_APP_PRIVATE_KEY'}]},
 environmentVariables:{total_count:3,variables:[
  {name:'PRP_COLLAB_APP_CLIENT_ID',value:'Iv1.test-client-id'},
  {name:'PRP_COLLAB_APP_ID',value:'5561446'},
  {name:'PRP_COLLAB_RULESET_ID',value:'26294671'}]},
 installationRepos:{total_count:1,repositories:[{full_name:REPO}]},
 publicationHold:{schema_version:1,reason:'Hold production publication during collaboration bootstrap'},
 snapshot:{schema_version:1,requirement_id:REQ,issue_number:132,title:'Task registry',
  status:'ACTIVE',version:0,updated_at:'2026-10-31T16:07:29Z',processed_requests:[],
  tasks:[
   {task_id:'T-001',issue_number:133,title:'Core',status:'READY',claim:null,
    depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs']},
   {task_id:'T-002',issue_number:134,title:'Coordinator',status:'READY',claim:null,
    depends_on:['T-001'],allowed_paths:['app/scripts/dev-collab/coordinator-cli.mjs']},
   {task_id:'T-003',issue_number:135,title:'Workflows',status:'READY',claim:null,
    depends_on:['T-001'],allowed_paths:['.github/workflows/prp-collab-coordinator.yml']},
   {task_id:'T-004',issue_number:136,title:'Docs',status:'READY',claim:null,
    depends_on:['T-001'],allowed_paths:['app/docs/dev-collab/']},
   {task_id:'T-005',issue_number:137,title:'Acceptance',status:'READY',claim:null,
    depends_on:['T-001','T-002','T-003','T-004'],
    allowed_paths:['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']}
  ]}
})
test('no-click automation prerequisites can be observed but never authorize a claim',()=>{
 const result=evaluateActivationEvidence(good())
 assert.equal(result.status,'PRECONDITIONS_OBSERVED')
 assert.deepEqual(result.blockers,[])
 assert.equal(result.allow_claim,false)
 assert.equal(result.allow_merge,false)
 assert.equal(result.allow_deploy,false)
})
test('unprotected branches, main bypass, missing rulesets and broad App scope fail closed',()=>{
 const x=good()
 x.stateBranch.protected=false
 x.mainRule.bypass_actors=[{actor_type:'RepositoryRole',actor_id:5,bypass_mode:'always'}]
 x.rule=null;x.appId=NaN;x.installationRepos={total_count:2,
  repositories:[{full_name:REPO},{full_name:'another/repository'}]}
 const out=evaluateActivationEvidence(x)
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.includes('STATE_BRANCH_UNPROTECTED'))
 assert.ok(out.blockers.includes('MAIN_BYPASS_ACTORS_NOT_EMPTY_OR_VISIBLE'))
 assert.ok(out.blockers.some(x=>x.startsWith('STATE_RULESET_')))
 assert.ok(out.blockers.includes('DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED'))
})
test('the automation environment must have no reviewers or wait timer',()=>{
 for(const protection of [
  {type:'required_reviewers',reviewers:[{type:'User',reviewer:{login:'owner'}}]},
  {type:'wait_timer',wait_timer:1},
  {type:'custom_deployment_protection_rule'}
 ]){
  const x=good();x.environment.protection_rules=[protection]
  assert.ok(evaluateActivationEvidence(x).blockers.includes('AUTO_ENV_HAS_MANUAL_APPROVAL_GATE'))
 }
})
test('automation Environment must be restricted to exactly main',()=>{
 const x=good()
 x.environment.deployment_branch_policy={protected_branches:true,custom_branch_policies:false}
 x.branchPolicies={total_count:2,branch_policies:[{name:'main'},{name:'release/*'}]}
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('AUTO_ENV_BRANCH_POLICY_NOT_CUSTOM_MAIN_ONLY'))
 assert.ok(out.blockers.includes('AUTO_ENV_BRANCH_POLICY_NOT_EXACT_MAIN'))
})
test('environment secret and exact variables are required without exposing secret values',()=>{
 const x=good()
 x.environmentSecrets={total_count:0,secrets:[]}
 x.environmentVariables={total_count:1,variables:[
  {name:'PRP_COLLAB_APP_ID',value:'999'}]}
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('AUTO_ENV_APP_PRIVATE_KEY_SECRET_MISSING'))
 assert.ok(out.blockers.includes('AUTO_ENV_APP_CLIENT_ID_MISSING'))
 assert.ok(out.blockers.includes('AUTO_ENV_APP_ID_MISMATCH'))
 assert.ok(out.blockers.includes('AUTO_ENV_RULESET_ID_MISMATCH'))
})
test('a redacted bypass list is not enough for the administrator preflight',()=>{
 const x=good()
 delete x.rule.bypass_actors
 x.rule.current_user_can_bypass='always'
 assert.ok(evaluateActivationEvidence(x).blockers.includes(
  'STATE_RULESET_BYPASS_LIST_NOT_VISIBLE'))
})
test('wrong state version, claimed tasks, missing hold or unpinned V0 fail closed',()=>{
 const x=good()
 x.snapshot.version=1
 x.publicationHold=null
 x.headSha='a'.repeat(40)
 x.stateBranch.commit.sha=x.headSha
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('NOT_CLEAN_INITIAL_PILOT_STATE'))
 assert.ok(out.blockers.includes('PUBLICATION_HOLD_MISSING_OR_INVALID'))
 assert.ok(out.blockers.includes('STATE_NOT_PINNED_V0'))
})
