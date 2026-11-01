import test from 'node:test'
import assert from 'node:assert/strict'
import {verifyExactTaskDelta,verifyMigrationEvidence} from './migration-guard.mjs'
import {SCOPE_MIGRATION_FILES} from './bootstrap-audit.mjs'
import {readFileSync} from 'node:fs'
import {spawnSync} from 'node:child_process'
const z='0'.repeat(40),h='1'.repeat(40)
const state=()=>({
 schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
 title:'多 GPT 会话共享开发任务 MVP',status:'ACTIVE',version:0,
 updated_at:'2026-10-31T16:05:00Z',processed_requests:[],
 tasks:[
 {task_id:'T-001',issue_number:133,title:'Core',status:'READY',depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null},
 {task_id:'T-002',issue_number:134,title:'Templates',status:'READY',depends_on:[],allowed_paths:['.github/ISSUE_TEMPLATE/'],claim:null},
 {task_id:'T-003',issue_number:135,title:'Coordinator',status:'READY',depends_on:['T-001'],allowed_paths:['app/scripts/dev-collab/coordinator-cli.mjs'],claim:null},
 {task_id:'T-004',issue_number:136,title:'Docs',status:'READY',depends_on:['T-001','T-003'],allowed_paths:['app/docs/dev-collab/'],claim:null},
 {task_id:'T-005',issue_number:137,title:'Integration',status:'READY',depends_on:['T-001','T-002','T-003','T-004'],allowed_paths:[],claim:null}]
})
const newTasks=[
 ['T-006',141,'只读任务看板与 Issue 投影',['T-003']],
 ['T-007',142,'可信验收与 GitHub App 安全验证',['T-003']],
 ['T-008',143,'CAS 并发及工作流边界测试',['T-003','T-007','T-009']],
 ['T-009',146,'GPT 会话任务恢复、持久化断点与授权接管',['T-003','T-007']]]
const proposal=()=>{
 const a=state();a.version=1;a.updated_at='2026-11-01T02:00:00Z'
 a.tasks[4].depends_on.push('T-006','T-007','T-008','T-009')
 a.tasks[4].allowed_paths=['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']
 for(const [id,issue,title,deps] of newTasks)
   a.tasks.push({task_id:id,issue_number:issue,title,status:'READY',
     depends_on:deps,allowed_paths:SCOPE_MIGRATION_FILES[id],claim:null})
 return a
}
const rule=()=>({id:26294671,target:'branch',enforcement:'active',
 conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
 rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
 bypass_actors:[{actor_type:'Integration',actor_id:5561446,bypass_mode:'always'}]})
const input=()=>({before:state(),after:proposal(),pr:{
 number:144,state:'open',draft:true,changed_files:1,
 base:{ref:'prp-collab-state',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
 head:{ref:'proposal/prp-collab-state-scope-20261101',sha:h,
 repo:{full_name:'micor-cjj-spec/matrix-prp'}}},
 prFiles:[{filename:'requirements/REQ-20261031-001.json',status:'modified'}],
 rule:rule(),appId:5561446,ruleId:26294671,stateSha:z,proposalSha:h,
 mode:'verify',approvalPhrase:'',appInstallation:null})
const fails=(e,code)=>assert.throws(()=>verifyMigrationEvidence(e),x=>x.message==='MIGRATION_'+code)
test('exact V0 to V1 preserves original claims and rejects hidden fields and approvals',()=>{
 assert.equal(verifyExactTaskDelta(state(),proposal()).task_count,9)
 let s=proposal();s.admin_bypass=true
 assert.throws(()=>verifyExactTaskDelta(state(),s),/MIGRATION_TOP_LEVEL_FIELD_CHANGE/)
 s=proposal();s.tasks[4].secret='x'
 assert.throws(()=>verifyExactTaskDelta(state(),s),/MIGRATION_HISTORIC_FIELD_CHANGE/)
 s=proposal();s.tasks[8].privilege=true
 assert.throws(()=>verifyExactTaskDelta(state(),s),/MIGRATION_NEW_TASK_FIELDS/)
 s=proposal();s.tasks[8].title='wrong'
 assert.throws(()=>verifyExactTaskDelta(state(),s),/MIGRATION_UNAPPROVED_TASK_DELTA/)
 s=proposal();s.tasks[0].status='DONE'
 assert.throws(()=>verifyExactTaskDelta(state(),s))
})
test('verification is read-only, with no implicit permission for state updates',()=>{
 const report=verifyMigrationEvidence(input())
 assert.equal(report.status,'READ_ONLY_PRECHECK_PASSED')
 assert.equal(report.state_write_authorized_by_this_report,false)
 assert.equal(report.production_deploy_authorized,false)
 assert.equal(report.designated_app_bypass_verified,true)
 assert.equal(report.bypass_actor_list_visible,true)
})
test('apply refuses draft, missing consent or broader App installation',()=>{
 const e=input();e.mode='apply'
 fails(e,'PROPOSAL_STILL_DRAFT')
 e.pr.draft=false;fails(e,'EXPLICIT_OWNER_APPROVAL')
 e.approvalPhrase='APPLY-REQ-20261031-001-V1';fails(e,'APP_INSTALLATION_SCOPE')
 e.appInstallation={total_count:2,repositories:[{full_name:'micor-cjj-spec/matrix-prp'},{full_name:'other/repo'}]}
 fails(e,'APP_INSTALLATION_SCOPE')
 e.appInstallation={total_count:1,repositories:[{full_name:'micor-cjj-spec/matrix-prp'}]}
 assert.equal(verifyMigrationEvidence(e).status,'APP_WRITE_PRECONDITIONS_OBSERVED')
})
test('wrong PR, modified file scope, state revision or rule bypass must fail',()=>{
 let e=input();e.pr.head.sha=z;fails(e,'PROPOSAL_PR_IDENTITY')
 e=input();e.pr.base.ref='main';fails(e,'PROPOSAL_PR_IDENTITY')
 e=input();e.prFiles=[];fails(e,'PROPOSAL_FILES')
 e=input();e.pr.changed_files=2;fails(e,'PROPOSAL_FILES')
 e=input();e.ruleId=999;fails(e,'RULESET_ID')
 e=input();e.stateSha=h;fails(e,'SHA')
 e=input();e.rule.bypass_actors[0].actor_id=999
 assert.throws(()=>verifyMigrationEvidence(e),x=>x.code==='UNSAFE_RULESET_BYPASS')
})
test('workflow only runs on reviewed main with owner, environment and App on apply',()=>{
 const w=readFileSync(new URL('../../../.github/workflows/prp-collab-migration.yml',import.meta.url),'utf8')
 const sh=readFileSync(new URL('./migration-transaction.sh',import.meta.url),'utf8')
 assert.match(w,/workflow_dispatch:/)
 assert.doesNotMatch(w,/pull_request_target:|workflow_run:|schedule:/)
 assert.match(w,/github\.ref == 'refs\/heads\/main'/)
 assert.match(w,/github\.actor == github\.repository_owner/)
 assert.match(w,/environment: prp-collab-controller/)
 assert.match(w,/if: inputs\.mode == 'apply'/)
 assert.ok(w.includes('actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510'))
 assert.ok(w.includes("permission-contents: ${{ inputs.mode == 'apply' && 'write' || 'read' }}"))
 assert.ok(w.includes('package-manager-cache: false'))
 assert.ok(w.includes('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'))
 assert.ok(w.includes('actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1'))
 assert.match(w,/owner: \$\{\{ github\.repository_owner \}\}/)
 assert.match(w,/repositories: matrix-prp/)
 assert.match(sh,/POST_PUSH_SHA_MISMATCH/)
 assert.match(sh,/POST_PUSH_REF_UNAVAILABLE/)
 assert.match(w,/persist-credentials: \$\{\{ inputs\.mode == 'apply' \}\}/)
 assert.doesNotMatch(w,/\n\s+contents: write|pull-requests: write|issues: write|actions: write/)
 assert.match(sh,/PRP_COLLAB_MIGRATION=VERIFIED_READ_ONLY/)
 assert.match(sh,/PUBLICATION_HOLD_MISSING/)
 assert.match(sh,/PUBLICATION_HOLD_INVALID/)
 assert.match(sh,/MAIN_HEAD_MOVED/)
 assert.match(sh,/MAIN_HEAD_RACE/)
 assert.match(sh,/UNAPPROVED_STATE_SHA/)
 assert.match(sh,/UNAPPROVED_PROPOSAL_SHA/)
 assert.match(w,/COLLAB_APPROVED_STATE_SHA: '062036f7021e215ffbfdcbf5689d207a0549b68b'/)
 assert.match(w,/COLLAB_APPROVED_PROPOSAL_SHA: 'fb57656dca6df5f12e083fc0430263b4d88e452d'/)
 assert.match(sh,/ls-remote --refs origin refs\/heads\/prp-collab-state/)
 assert.match(sh,/git -C "\$state_worktree" push origin HEAD:refs\/heads\/prp-collab-state/)
 assert.doesNotMatch(sh,/git push .*--force|git push .* -f |kubectl |docker compose up|systemctl |sudo |ssh /)
 const run=spawnSync('bash',['-n',new URL('./migration-transaction.sh',import.meta.url).pathname],{encoding:'utf8'})
 assert.equal(run.status,0,run.stderr)
})
test('unauthorized workflow ref is rejected before any Git access',()=>{
 const path=new URL('./migration-transaction.sh',import.meta.url).pathname
 const e={...process.env,GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',
 GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_REF:'refs/heads/feature',
 GITHUB_ACTOR:'micor-cjj-spec',GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',
 GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-migration.yml@refs/heads/main',
 GITHUB_SHA:z}
 const p=spawnSync('bash',[path],{encoding:'utf8',env:e})
 assert.equal(p.status,2)
 assert.match(p.stderr,/PRP_COLLAB_MIGRATION_BLOCKED=SOURCE_REF/)
})

test('migration preflight distinguishes App bypass verification from a redacted bypass actor list',()=>{
 const e=input();delete e.rule.bypass_actors;e.rule.current_user_can_bypass='always'
 const report=verifyMigrationEvidence(e)
 assert.equal(report.designated_app_bypass_verified,true)
 assert.equal(report.bypass_actor_list_visible,false)
 const denied=input();delete denied.rule.bypass_actors;denied.rule.current_user_can_bypass='never'
 assert.throws(()=>verifyMigrationEvidence(denied),e=>e.code==='RULESET_APP_BYPASS_NOT_VERIFIED')
})
