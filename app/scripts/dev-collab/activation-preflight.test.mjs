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
   {type:'pull_request'},{type:'required_status_checks',parameters:{
    strict_required_status_checks_policy:true,
    required_status_checks:['backend-tests','web-build','mobile-build',
     'db-migration-integration','video-db-integration','impact-report']
     .map(context=>({context,integration_id:15368}))
   }}],
  bypass_actors:[]},
 stateBranch:{name:'prp-collab-state',protected:true,commit:{sha:V0}},
 headSha:V0,appId:5561446,rulesetId:26294671,
 rule:{id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  bypass_actors:[{actor_type:'Integration',actor_id:5561446,bypass_mode:'always'}]},
 appRule:{id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  current_user_can_bypass:'always'},
 expectedClientId:'Iv1.test-client-id',
 environment:{name:'prp-collab-automation',can_admins_bypass:false,protection_rules:[],
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
test('administrator bypass must be disabled for the automation environment',()=>{
 const x=good();x.environment.can_admins_bypass=true
 assert.ok(evaluateActivationEvidence(x).blockers.includes(
  'AUTO_ENV_ADMIN_BYPASS_ENABLED_OR_UNVERIFIED'))
 const missing=good();delete missing.environment.can_admins_bypass
 assert.ok(evaluateActivationEvidence(missing).blockers.includes(
  'AUTO_ENV_ADMIN_BYPASS_ENABLED_OR_UNVERIFIED'))
})
test('the App-scoped token must independently see its state Ruleset bypass',()=>{
 const x=good();x.appRule.current_user_can_bypass='never'
 assert.ok(evaluateActivationEvidence(x).blockers.includes(
  'APP_TOKEN_RULESET_RULESET_APP_BYPASS_NOT_VERIFIED'))
})
test('main required checks must be strict and match the exact six protected contexts',()=>{
 const x=good()
 x.mainRule.rules.find(r=>r.type==='required_status_checks')
  .parameters.strict_required_status_checks_policy=false
 assert.ok(evaluateActivationEvidence(x).blockers.includes('MAIN_REQUIRED_CHECKS_NOT_EXACT'))
 const y=good()
 y.mainRule.rules.find(r=>r.type==='required_status_checks')
  .parameters.required_status_checks.pop()
 assert.ok(evaluateActivationEvidence(y).blockers.includes('MAIN_REQUIRED_CHECKS_NOT_EXACT'))
})
test('the Environment App Client ID variable must exist without exposing its value',()=>{
 const x=good()
 x.environmentVariables.variables=x.environmentVariables.variables.filter(v=>v.name!=='PRP_COLLAB_APP_CLIENT_ID')
 assert.ok(evaluateActivationEvidence(x).blockers.includes('AUTO_ENV_APP_CLIENT_ID_MISSING'))
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

test('activation preflight rejects a substituted App or state Ruleset ID',()=>{
 const x=good();x.appId=999999;x.rulesetId=999999
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('APP_ID_MISMATCH'))
 assert.ok(out.blockers.includes('STATE_RULESET_ID_MISMATCH'))
})

// Sanitized V17 definition fixture, independently copied from the V17 ledger.
function migrated(){
 const x=good()
 x.headSha='884a607b4370748814223394b1772e165ed292fc'
 x.stateBranch.commit.sha=x.headSha
 x.snapshot.version=17
 x.snapshot.tasks=[
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
].map(t=>({...t,status:t.task_id==='T-001'?'DONE':'READY',claim:null}))
 x.snapshot.processed_requests=[{request_id:'11111111-1111-4111-8111-111111111111',fingerprint:'a'.repeat(64),actor:'synthetic-owner',receipt:{type:'accept',task_id:'T-001',version:17}}]
 return x
}
test('V1 read-only phase recognizes migrated task identities without granting any authority',()=>{
 const x=migrated()
 const result=evaluateActivationEvidence(x,{phase:'active_v1'})
 assert.equal(result.phase,'active_v1')
 assert.equal(result.status,'PRECONDITIONS_OBSERVED')
 assert.deepEqual(result.blockers,[])
 assert.equal(result.state_sha,x.headSha)
 assert.equal(result.allow_claim,false)
 assert.equal(result.allow_merge,false)
 assert.equal(result.allow_deploy,false)
})
test('V0 bootstrap gate remains pinned and rejects migrated snapshot by default',()=>{
 const out=evaluateActivationEvidence(migrated())
 assert.equal(out.phase,'bootstrap_v0')
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.includes('STATE_NOT_PINNED_V0'))
 assert.ok(out.blockers.includes('NOT_CLEAN_INITIAL_PILOT_STATE'))
})
test('V1 phase rejects a version bump without all four migrated task identities',()=>{
 const x=migrated()
 x.snapshot.tasks=x.snapshot.tasks.filter(t=>t.task_id!=='T-009')
 const out=evaluateActivationEvidence(x,{phase:'active_v1'})
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.includes('INVALID_OR_UNMIGRATED_STATE_SNAPSHOT'))
})
test('V1 cannot reuse V0 state SHA or an unverified current branch ref',()=>{
 const x=migrated()
 x.headSha=V0
 x.stateBranch.commit.sha=V0
 assert.ok(evaluateActivationEvidence(x,{phase:'active_v1'}).blockers.includes('STATE_STILL_PINNED_TO_V0'))
 const y=migrated()
 y.stateBranch.commit.sha='a'.repeat(40)
 assert.ok(evaluateActivationEvidence(y,{phase:'active_v1'}).blockers.includes('STATE_REF_UNVERIFIED'))
})
test('V1 read-only report preserves all existing App, policy, environment and hold fail-closed gates',()=>{
 const x=migrated()
 x.rule.bypass_actors=[]
 x.appRule.current_user_can_bypass='never'
 x.environmentSecrets.secrets=[]
 x.publicationHold=null
 const out=evaluateActivationEvidence(x,{phase:'active_v1'})
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.some(s=>s.startsWith('STATE_RULESET_')))
 assert.ok(out.blockers.some(s=>s.startsWith('APP_TOKEN_RULESET_')))
 assert.ok(out.blockers.includes('AUTO_ENV_APP_PRIVATE_KEY_SECRET_MISSING'))
 assert.ok(out.blockers.includes('PUBLICATION_HOLD_MISSING_OR_INVALID'))
})
test('unknown preflight phase fails closed even with otherwise valid evidence',()=>{
 const out=evaluateActivationEvidence(migrated(),{phase:'magic'})
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.includes('UNKNOWN_PREFLIGHT_PHASE'))
})


test('V17 definitions reject altered issue identity, scope and dependency even at later versions',()=>{
 for(const mutate of [
  x=>x.snapshot.tasks[0].issue_number=999,
  x=>x.snapshot.tasks[6].allowed_paths=['app/scripts/dev-collab/'],
  x=>x.snapshot.tasks[6].depends_on=[],
  x=>x.snapshot.tasks[0].title='changed',
  x=>x.snapshot.tasks.push({...x.snapshot.tasks[0],task_id:'T-010',issue_number:900})
 ]){
  const x=migrated();x.snapshot.version=19;mutate(x)
  const out=evaluateActivationEvidence(x,{phase:'active_v1'})
  assert.equal(out.status,'NO_GO')
  assert.ok(out.blockers.includes('MIGRATED_TASK_DEFINITION_MISMATCH')||out.blockers.includes('INVALID_OR_UNMIGRATED_STATE_SNAPSHOT'))
 }
})
test('post-migration preflight permits legitimate later versions and claims but grants no authority',()=>{
 const x=migrated();x.snapshot.version=19
 x.snapshot.tasks[6].status='IN_PROGRESS'
 x.snapshot.tasks[6].claim={claim_id:'22222222-2222-4222-8222-222222222222',worker_id:'synthetic-worker',actor:'synthetic-owner',generation:1}
 const out=evaluateActivationEvidence(x,{phase:'active_v1'})
 assert.equal(out.status,'PRECONDITIONS_OBSERVED');assert.equal(out.allow_claim,false)
 assert.equal(out.allow_merge,false);assert.equal(out.allow_deploy,false)
})
test('App ruleset response must bind exact rule ID and caller-specific bypass even when list is visible',()=>{
 const x=migrated();x.appRule.id=999
 assert.ok(evaluateActivationEvidence(x,{phase:'active_v1'}).blockers.includes('APP_TOKEN_RULESET_ID_MISMATCH'))
 const y=migrated();y.appRule.bypass_actors=y.rule.bypass_actors;y.appRule.current_user_can_bypass='never'
 assert.ok(evaluateActivationEvidence(y,{phase:'active_v1'}).blockers.includes('APP_TOKEN_STATE_BYPASS_NOT_VERIFIED'))
})
