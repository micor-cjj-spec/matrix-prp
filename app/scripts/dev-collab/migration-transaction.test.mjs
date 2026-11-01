import test from 'node:test'
import assert from 'node:assert/strict'
import {execFileSync,spawnSync} from 'node:child_process'
import {mkdtempSync,mkdirSync,writeFileSync,cpSync,rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {SCOPE_MIGRATION_FILES} from './bootstrap-audit.mjs'

const REQ='requirements/REQ-20261031-001.json'
const source=fileURLToPath(new URL('.',import.meta.url))
const git=(cwd,...args)=>execFileSync('git',args,{cwd,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim()
const initial=()=>({schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
 title:'多 GPT 会话共享开发任务 MVP',status:'ACTIVE',version:0,
 updated_at:'2026-10-31T16:05:00Z',processed_requests:[],tasks:[
 {task_id:'T-001',issue_number:133,title:'Core',status:'READY',depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null},
 {task_id:'T-002',issue_number:134,title:'Templates',status:'READY',depends_on:[],allowed_paths:['.github/ISSUE_TEMPLATE/'],claim:null},
 {task_id:'T-003',issue_number:135,title:'Coordinator',status:'READY',depends_on:['T-001'],allowed_paths:['app/scripts/dev-collab/coordinator-cli.mjs'],claim:null},
 {task_id:'T-004',issue_number:136,title:'Docs',status:'READY',depends_on:['T-001','T-003'],allowed_paths:['app/docs/dev-collab/'],claim:null},
 {task_id:'T-005',issue_number:137,title:'Integration',status:'READY',depends_on:['T-001','T-002','T-003','T-004'],allowed_paths:[],claim:null}
 ]})
const candidate=()=>{
 const s=initial();s.version=1;s.updated_at='2026-11-01T02:42:00Z'
 s.tasks[4].depends_on.push('T-006','T-007','T-008','T-009')
 s.tasks[4].allowed_paths=['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']
 for(const [id,issue,title,deps] of [
 ['T-006',141,'只读任务看板与 Issue 投影',['T-003']],
 ['T-007',142,'可信验收与 GitHub App 安全验证',['T-003']],
 ['T-008',143,'CAS 并发及工作流边界测试',['T-003','T-007','T-009']],
 ['T-009',146,'GPT 会话任务恢复、持久化断点与授权接管',['T-003','T-007']]
 ])s.tasks.push({task_id:id,issue_number:issue,title,status:'READY',
    depends_on:deps,allowed_paths:SCOPE_MIGRATION_FILES[id],claim:null})
 return s
}
function setup(){
 const root=mkdtempSync(join(tmpdir(),'prp-migration-local-'))
 const origin=join(root,'origin.git'),seed=join(root,'seed'),runner=join(root,'runner')
 mkdirSync(seed)
 git(root,'init','--bare','--initial-branch=main',origin)
 git(seed,'init','--initial-branch=main')
 git(seed,'config','user.name','Test owner')
 git(seed,'config','user.email','ci@example.invalid')
 git(seed,'remote','add','origin',origin)
 const dest=join(seed,'app/scripts/dev-collab');mkdirSync(dest,{recursive:true})
 for(const n of ['core.mjs','task-scope-policy.mjs','bootstrap-audit.mjs','state-rule-policy.mjs',
   'migration-guard.mjs','migration-transaction.sh'])
   cpSync(join(source,n),join(dest,n))
 mkdirSync(join(seed,'app/deploy'),{recursive:true})
 writeFileSync(join(seed,'app/deploy/publication-hold.json'),
   JSON.stringify({schema_version:1,reason:'Isolated local-test publication freeze'})+'\n')
 git(seed,'add','.');git(seed,'commit','-m','reviewed main source')
 git(seed,'push','origin','main')
 const main=git(seed,'rev-parse','HEAD')
 git(seed,'checkout','-b','prp-collab-state')
 mkdirSync(join(seed,'requirements'))
 writeFileSync(join(seed,REQ),JSON.stringify(initial(),null,2)+'\n')
 git(seed,'add',REQ);git(seed,'commit','-m','state V0')
 git(seed,'push','origin','prp-collab-state')
 const stateSha=git(seed,'rev-parse','HEAD')
 git(seed,'checkout','-b','proposal/prp-collab-state-scope-20261101')
 writeFileSync(join(seed,REQ),JSON.stringify(candidate(),null,2)+'\n')
 git(seed,'add',REQ);git(seed,'commit','-m','candidate V1')
 git(seed,'push','origin','proposal/prp-collab-state-scope-20261101')
 const proposalSha=git(seed,'rev-parse','HEAD')
 git(root,'clone','--branch','main',origin,runner)
 const bin=join(root,'bin');mkdirSync(bin)
 const mock=[
  '#!/usr/bin/env bash','set -euo pipefail',
  '[[ "$1" == api ]] || exit 2',
  'case "$2" in',
  ' */pulls/144) cat "$PRP_MOCK_PR" ;;',
  ' */pulls/144/files*) cat "$PRP_MOCK_FILES" ;;',
  ' */pulls/144/reviews*) cat "$PRP_MOCK_REVIEWS" ;;',
  ' */rulesets/26294671) [[ "${GH_TOKEN:-}" == "local-test-read-token" || "${GH_TOKEN:-}" == "local-test-write-token" ]] || exit 4; cat "$PRP_MOCK_RULE" ;;',
  ' installation/repositories) cat "$PRP_MOCK_APP" ;;',
  " *) echo UNEXPECTED_API >&2; exit 2 ;;",
  'esac'
 ].join('\n')+'\n'
 writeFileSync(join(bin,'gh'),mock,{mode:0o755})
 const temp=join(root,'temp');mkdirSync(temp)
 const names={pr:join(root,'pr.json'),files:join(root,'files.json'),reviews:join(root,'reviews.json'),
  rule:join(root,'rule.json'),app:join(root,'app.json')}
 const pr={number:144,state:'open',draft:true,changed_files:1,
  user:{login:'micor-cjj-spec',id:123868412},
  base:{ref:'prp-collab-state',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
  head:{ref:'proposal/prp-collab-state-scope-20261101',sha:proposalSha,
   repo:{full_name:'micor-cjj-spec/matrix-prp'}}}
 const rule={id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  bypass_actors:[{actor_type:'Integration',actor_id:5561446,bypass_mode:'always'}]}
 const save=(file,value)=>writeFileSync(file,JSON.stringify(value))
 save(names.pr,pr);save(names.files,[{filename:REQ,status:'modified'}]);save(names.reviews,[])
 save(names.rule,rule)
 save(names.app,{total_count:1,repositories:[{full_name:'micor-cjj-spec/matrix-prp'}]})
 const env={...process.env,PATH:bin+':'+process.env.PATH,RUNNER_TEMP:temp,
  GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',
  GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_REF:'refs/heads/main',
  GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-migration.yml@refs/heads/main',
  GITHUB_ACTOR:'micor-cjj-spec',GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',
  GITHUB_SHA:main,GITHUB_RUN_ID:'12345678',GITHUB_RUN_ATTEMPT:'1',
  COLLAB_APP_ID:'5561446',COLLAB_RULESET_ID:'26294671',
  COLLAB_EXPECTED_STATE_SHA:stateSha,COLLAB_EXPECTED_PROPOSAL_SHA:proposalSha,
  COLLAB_APPROVED_STATE_SHA:stateSha,COLLAB_APPROVED_PROPOSAL_SHA:proposalSha,
  COLLAB_MIGRATION_MODE:'verify',COLLAB_APPROVAL_PHRASE:'',
  COLLAB_APP_TOKEN:'local-test-read-token',GH_TOKEN:'read-only',
  PRP_MOCK_PR:names.pr,PRP_MOCK_FILES:names.files,PRP_MOCK_REVIEWS:names.reviews,
  PRP_MOCK_RULE:names.rule,PRP_MOCK_APP:names.app}
 return {root,names,pr,save,
  execute:(override={})=>spawnSync('bash',['app/scripts/dev-collab/migration-transaction.sh'],
   {cwd:runner,encoding:'utf8',timeout:15000,env:{...env,...override}}),
  state:()=>git(root,'--git-dir',origin,'rev-parse','refs/heads/prp-collab-state'),
  cleanup:()=>rmSync(root,{recursive:true,force:true})}
}

test('read-only migration verification requires a scoped App token to inspect the ruleset',
 {timeout:30000},()=>{
 const f=setup()
 try{
  const before=f.state()
  const result=f.execute({COLLAB_APP_TOKEN:''})
  assert.notEqual(result.status,0)
  assert.match(result.stderr,/DEDICATED_APP_TOKEN/)
  assert.equal(f.state(),before)
 }finally{f.cleanup()}
})

test('isolated Git preview is read only; simulated authorized apply commits once; stale replay is denied',
 {timeout:45000},()=>{
 const f=setup()
 try{
  const before=f.state()
  const wrongApp=f.execute({COLLAB_APP_ID:'999999'})
  assert.notEqual(wrongApp.status,0)
  assert.match(wrongApp.stderr,/APP_ID/)
  const wrongRuleset=f.execute({COLLAB_RULESET_ID:'999999'})
  assert.notEqual(wrongRuleset.status,0)
  assert.match(wrongRuleset.stderr,/RULESET_ID/)
  assert.equal(f.state(),before)
  const wrongState=f.execute({COLLAB_EXPECTED_STATE_SHA:'0'.repeat(40)})
  assert.notEqual(wrongState.status,0)
  assert.match(wrongState.stderr,/UNAPPROVED_STATE_SHA/)
  const wrongProposal=f.execute({COLLAB_EXPECTED_PROPOSAL_SHA:'1'.repeat(40)})
  assert.notEqual(wrongProposal.status,0)
  assert.match(wrongProposal.stderr,/UNAPPROVED_PROPOSAL_SHA/)
  const verify=f.execute()
  assert.equal(verify.status,0,verify.stderr)
  assert.match(verify.stdout,/PRP_COLLAB_MIGRATION=VERIFIED_READ_ONLY/)
  assert.equal(f.state(),before)
  const input={COLLAB_MIGRATION_MODE:'apply',COLLAB_APP_TOKEN:'local-test-write-token',
   COLLAB_APPROVAL_PHRASE:'APPLY-REQ-20261031-001-V1'}
  const denied=f.execute(input)
  assert.notEqual(denied.status,0)
  assert.match(denied.stderr,/PROPOSAL_STILL_DRAFT/)
  assert.equal(f.state(),before)
  f.pr.draft=false;f.save(f.names.pr,f.pr)
  const noReview=f.execute(input)
  assert.notEqual(noReview.status,0)
  assert.match(noReview.stderr,/INDEPENDENT_REVIEW_REQUIRED/)
  assert.equal(f.state(),before)
  f.save(f.names.reviews,[{id:1,user:{login:'independent-reviewer',id:999},
   state:'APPROVED',commit_id:f.pr.head.sha,submitted_at:'2026-11-01T03:00:00Z'}])
  const accepted=f.execute(input)
  assert.equal(accepted.status,0,accepted.stderr)
  assert.match(accepted.stdout,/PRP_COLLAB_MIGRATION_APPLIED_SHA=/)
  assert.match(accepted.stdout,new RegExp(f.state()))
  assert.notEqual(f.state(),before)
  const replay=f.execute()
  assert.notEqual(replay.status,0)
  assert.match(replay.stderr,/STATE_MOVED_OR_MIGRATED/)
 }finally{f.cleanup()}
})
