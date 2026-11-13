import test from 'node:test'
import assert from 'node:assert/strict'
import {execFileSync,spawnSync} from 'node:child_process'
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,cpSync,rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
const OWNER='micor-cjj-spec',REPO=OWNER+'/matrix-prp'
const REF='refs/heads/prp-collab-state',REQ='requirements/REQ-20261031-001.json'
const location=fileURLToPath(new URL('.',import.meta.url))
const git=(cwd,...args)=>execFileSync('git',args,{cwd,encoding:'utf8',
 stdio:['ignore','pipe','pipe']}).trim()
const initial=()=>({schema_version:1,requirement_id:'REQ-20261031-001',
 issue_number:132,title:'Collaboration task',status:'ACTIVE',version:0,
 processed_requests:[],tasks:[{task_id:'T-001',issue_number:133,title:'Core task',
  status:'READY',depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],
  claim:null}]})
const request=(id='11111111-1111-4111-8111-111111111111',version=0)=>({
 schema_version:1,action:'claim',request_id:id,
 requirement_id:'REQ-20261031-001',task_id:'T-001',
 worker_id:'chat-A',expected_version:version})
const reviewedV1=()=>{
 const snapshot=initial()
 snapshot.version=1
 for(const [number,issue] of [[2,134],[3,135],[4,136],[5,137],
  [6,141],[7,142],[8,143],[9,146]]){
  snapshot.tasks.push({task_id:'T-'+String(number).padStart(3,'0'),
   issue_number:issue,title:'Reviewed task '+number,status:'READY',
   depends_on:[],allowed_paths:[],claim:null})
 }
 return snapshot
}
function setup({v1=false}={}){
 const root=mkdtempSync(join(tmpdir(),'prp-issue-local-'))
 const origin=join(root,'origin.git'),seed=join(root,'seed'),runner=join(root,'runner')
 mkdirSync(seed)
 git(root,'init','--bare','--initial-branch=main',origin)
 git(seed,'init','--initial-branch=main')
 git(seed,'config','user.name','CI test user')
 git(seed,'config','user.email','test@example.invalid')
 git(seed,'remote','add','origin',origin)
 const dest=join(seed,'app/scripts/dev-collab')
 mkdirSync(dest,{recursive:true})
 for(const filename of [
  'core.mjs','issue-ingress.mjs','issue-transaction.mjs','issue-migrate.mjs',
  'migration-guard.mjs','bootstrap-audit.mjs','state-rule-policy.mjs','task-scope-policy.mjs'])
  cpSync(join(location,filename),join(dest,filename))
 mkdirSync(join(seed,'app/deploy'),{recursive:true})
 writeFileSync(join(seed,'app/deploy/publication-hold.json'),
  JSON.stringify({schema_version:1,reason:'Test-only release hold'})+'\n')
 git(seed,'add','.')
 git(seed,'commit','-m','trusted main source fixture')
 git(seed,'push','origin','main')
 const main=git(seed,'rev-parse','HEAD')
 git(seed,'checkout','-b','prp-collab-state')
 mkdirSync(join(seed,'requirements'))
 writeFileSync(join(seed,REQ),JSON.stringify(v1?reviewedV1():initial(),null,2)+'\n')
 git(seed,'add',REQ);git(seed,'commit','-m','initial state')
 git(seed,'push','origin','prp-collab-state')
 const first=git(root,'--git-dir',origin,'rev-parse',REF)
 // A real remote feature ref is needed for checkpoint verification.
 git(seed,'checkout','-b','feat/chat-a-checkpoint','main')
 writeFileSync(join(seed,'checkpoint-proof.txt'),'committed chat checkpoint\\n')
 git(seed,'add','checkpoint-proof.txt')
 git(seed,'commit','-m','checkpoint commit from old chat')
 git(seed,'push','origin','feat/chat-a-checkpoint')
 const checkpointSha=git(seed,'rev-parse','HEAD')
 git(root,'clone','--branch','main',origin,runner)
 const fakeDir=join(root,'bin');mkdirSync(fakeDir)
 const mock=[
  '#!/usr/bin/env bash','set -euo pipefail',
  '[[ "$1" == api ]] || exit 3',
  'case "$2" in',
  ' */issues/999) cat "$PRP_MOCK_ISSUE" ;;',
  ' */issues/1000) cat "$PRP_MOCK_TASK_ISSUE" ;;',
  ' */rulesets/26294671) [[ "${GH_TOKEN:-}" == "isolated-test-app-token" ]] || exit 4; cat "$PRP_MOCK_RULESET" ;;',
  ' installation/repositories) [[ "${GH_TOKEN:-}" == "isolated-test-app-token" ]] || exit 4; cat "$PRP_MOCK_APP_REPOS" ;;',
  ' */branches/main) echo "{\\"protected\\":true}" ;;',
  ' */branches/prp-collab-state) if [[ "${PRP_MOCK_DRIFT_MAIN:-}" == "1" ]]; then git -C "$PRP_MOCK_SEED" checkout main >/dev/null 2>&1; echo drift > "$PRP_MOCK_SEED/main-moved.txt"; git -C "$PRP_MOCK_SEED" add main-moved.txt; git -C "$PRP_MOCK_SEED" commit -m "new trusted source" >/dev/null; git -C "$PRP_MOCK_SEED" push origin main >/dev/null 2>&1; fi; echo "{\\"protected\\":true}" ;;',
  ' *) echo "UNKNOWN_GH_ROUTE" >&2; exit 3 ;;',
  'esac'
 ].join('\n')+'\n'
 writeFileSync(join(fakeDir,'gh'),mock,{mode:0o755})
 const eventPath=join(root,'event.json'),issuePath=join(root,'issue.json')
 const taskIssuePath=join(root,'task-issue.json')
 const rulePath=join(root,'rule.json'),appReposPath=join(root,'app-repos.json'),temp=join(root,'run-temp')
 mkdirSync(temp)
 writeFileSync(appReposPath,JSON.stringify({total_count:1,repositories:[{full_name:REPO}]}))
 writeFileSync(rulePath,JSON.stringify({
  id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:[REF],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  current_user_can_bypass:'always'
 }))
 const prepare=(payload,author=OWNER)=>{
  const issue={number:999,title:'[PRP-COLLAB-REQUEST]',state:'open',
   user:{login:author,id:123868412},author_association:'OWNER',body:JSON.stringify(payload)}
  const evt={action:'opened',sender:{login:author,id:123868412,type:'User'},
   repository:{full_name:REPO,default_branch:'main',owner:{login:OWNER,id:123868412}},
   issue}
  writeFileSync(eventPath,JSON.stringify(evt));writeFileSync(issuePath,JSON.stringify(issue))
 }
 prepare(request())
 const prepareTaskIssue=(manifest,author=OWNER)=>{
  const issue={number:1000,title:'[TASK]['+manifest.requirement_id+'/'+
   manifest.task_id+'] '+manifest.title,state:'open',
   user:{login:author,id:author===OWNER?123868412:202},author_association:'OWNER',
   body:'Task objective and acceptance criteria\n\n<!-- PRP_TASK_MANIFEST\n'+
    JSON.stringify(manifest)+'\n-->'}
  writeFileSync(taskIssuePath,JSON.stringify(issue))
 }
 const env={...process.env,PATH:fakeDir+':'+process.env.PATH,
  GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'issues',
  GITHUB_EVENT_ACTION:'opened',GITHUB_EVENT_PATH:eventPath,
  GITHUB_REF:'refs/heads/main',GITHUB_SHA:main,GITHUB_ACTOR:OWNER,
  GITHUB_REPOSITORY:REPO,GITHUB_REPOSITORY_OWNER:OWNER,PRP_COLLAB_TEST_DIAGNOSTICS:'1',
  GITHUB_WORKFLOW_REF:REPO+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main',
  GH_TOKEN:'not-a-real-token',COLLAB_APP_TOKEN:'isolated-test-app-token',
  COLLAB_APP_ID:'5561446',COLLAB_RULESET_ID:'26294671',RUNNER_TEMP:temp,
  PRP_MOCK_ISSUE:issuePath,PRP_MOCK_TASK_ISSUE:taskIssuePath,
  PRP_MOCK_RULESET:rulePath,PRP_MOCK_APP_REPOS:appReposPath,PRP_MOCK_SEED:seed}
 const execute=(extra={})=>spawnSync(process.execPath,['app/scripts/dev-collab/issue-transaction.mjs'],
  {cwd:runner,env:{...env,...extra},encoding:'utf8',timeout:15000})
 const head=()=>git(root,'--git-dir',origin,'rev-parse',REF)
 const snapshot=()=>JSON.parse(git(root,'--git-dir',origin,'show',REF+':'+REQ))
 return {root,prepare,prepareTaskIssue,execute,head,snapshot,initialHead:first,initialMain:main,origin,checkpointSha,appReposPath,
  dispose:()=>rmSync(root,{recursive:true,force:true})}
}
test('isolated Git: owner probe verifies App scope without mutating protected state',
 {timeout:30000},()=>{
 const f=setup()
 try{
  const initialSha=f.head()
  f.prepare({schema_version:1,action:'probe',
    request_id:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
    requirement_id:'REQ-20261031-001'})
  const result=f.execute()
  assert.equal(result.status,0,result.stderr)
  assert.match(result.stdout,/PRP_COLLAB_PROBE_READ_ONLY=999/)
  assert.equal(f.head(),initialSha)
  assert.equal(f.snapshot().version,0)
  assert.equal(f.snapshot().tasks[0].claim,null)
  const receipt=readFileSync(join(f.root,'run-temp/prp-issue-receipt.md'),'utf8')
  assert.match(receipt,/No task was claimed and no Git state was written/)
  assert.doesNotMatch(receipt,/claim_id|private-key|Token:/)
 }finally{f.dispose()}
})

test('isolated Git: live owner claim cannot consume fixed V0 migration SHA',
 {timeout:30000},()=>{
 const f=setup()
 try{
  const original=f.head()
  const rejected=f.execute()
  assert.notEqual(rejected.status,0)
  assert.match(rejected.stderr,/ISSUE_MIGRATE_V1_FIRST/)
  assert.equal(f.head(),original)
  assert.equal(f.snapshot().version,0)
 }finally{f.dispose()}
})
test('isolated bare Git: owner issue atomically claims, repeat is idempotent and stale claim rejects',
 {timeout:40000},()=>{
 const f=setup({v1:true})
 try{
  f.prepare(request(undefined,1))
  const first=f.execute()
  assert.equal(first.status,0,first.stderr)
  assert.match(first.stdout,/PRP_COLLAB_ISSUE_SUCCESS=999/)
  assert.notEqual(f.head(),f.initialHead)
  const s=f.snapshot()
  assert.equal(s.version,2)
  assert.equal(s.tasks[0].claim.worker_id,'chat-A')
  const oldClaim=s.tasks[0].claim.claim_id
  const checkpoint={summary:'Committed work from the original GPT session',
   next_step:'Transfer to a fresh GPT session and run CI',
   branch:'feat/chat-a-checkpoint',head_sha:f.checkpointSha,
   tests:'CI pending; no passing result claimed'}
  const requestBase={schema_version:1,requirement_id:'REQ-20261031-001',
   task_id:'T-001',worker_id:'chat-A'}
  f.prepare({...requestBase,action:'checkpoint',
   request_id:'22222222-2222-4222-8222-222222222222',
   expected_version:2,claim_id:oldClaim,checkpoint})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const checkpointRun=f.execute()
  assert.equal(checkpointRun.status,0,checkpointRun.stderr)
  assert.equal(f.snapshot().tasks[0].checkpoint.head_sha,f.checkpointSha)
  assert.equal(f.snapshot().tasks[0].checkpoint.origin,'claimant')
  f.prepare({...requestBase,action:'handoff',
   request_id:'33333333-3333-4333-8333-333333333333',
   expected_version:3,claim_id:oldClaim,new_worker_id:'chat-B',
   expected_head_sha:f.checkpointSha,note:'Continue in a fresh GPT conversation'})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const handoff=f.execute()
  assert.equal(handoff.status,0,handoff.stderr)
  const transferred=f.snapshot()
  assert.equal(transferred.version,4)
  assert.equal(transferred.tasks[0].claim.worker_id,'chat-B')
  assert.equal(transferred.tasks[0].claim.generation,2)
  const newClaim=transferred.tasks[0].claim.claim_id
  f.prepare({...requestBase,action:'start',
   request_id:'44444444-4444-4444-8444-444444444444',
   expected_version:4,claim_id:oldClaim})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const oldChat=f.execute()
  assert.notEqual(oldChat.status,0)
  assert.match(oldChat.stderr,/STALE_OR_FOREIGN_CLAIM/)
  assert.equal(f.snapshot().version,4)
  f.prepare({...requestBase,worker_id:'chat-B',action:'start',
   request_id:'55555555-5555-4555-8555-555555555555',
   expected_version:4,claim_id:newClaim})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const newChat=f.execute()
  assert.equal(newChat.status,0,newChat.stderr)
  assert.equal(f.snapshot().tasks[0].status,'IN_PROGRESS')
  const manifest={schema_version:1,requirement_id:'REQ-20261031-001',
   task_id:'T-010',title:'Add dashboard filtering',depends_on:['T-001'],
   allowed_paths:['app/web/src/']}
  f.prepareTaskIssue(manifest)
  f.prepare({...requestBase,action:'register_task',task_id:'T-010',
   request_id:'66666666-6666-4666-8666-666666666666',
   expected_version:5,issue_number:1000,title:manifest.title,
   depends_on:manifest.depends_on,allowed_paths:manifest.allowed_paths})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const beforeRegister=f.head()
  const registered=f.execute()
  assert.equal(registered.status,0,registered.stderr)
  assert.equal(f.snapshot().tasks.find(t=>t.task_id==='T-010')?.status,'READY')
  assert.notEqual(f.head(),beforeRegister)
  assert.equal(f.snapshot().version,6)
  const prev=f.head()
  f.prepare(request('77777777-7777-4777-8777-777777777777',0))
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const stale=f.execute()
  assert.notEqual(stale.status,0)
  assert.match(stale.stderr,/PRP_COLLAB_ISSUE_FAILURE=ISSUE_STALE_VERSION/)
  assert.equal(f.head(),prev)
 }finally{f.dispose()}
})
test('isolated Git never writes state for a non-owner opened Issue', {timeout:30000},()=>{
 const f=setup()
 try{
  f.prepare(request(), 'attacker')
  const attempt=f.execute()
  assert.notEqual(attempt.status,0)
  assert.match(attempt.stderr,/INGRESS_UNTRUSTED_ISSUE/)
  assert.equal(f.head(),f.initialHead)
 }finally{f.dispose()}
})


test('isolated Git rejects a writer token not confined to this repository', {timeout:30000},()=>{
 const f=setup()
 try{
  writeFileSync(f.appReposPath,JSON.stringify({total_count:2,repositories:[
   {full_name:REPO},{full_name:'another/repository'}]}))
  const before=f.head()
  const attempt=f.execute()
  assert.notEqual(attempt.status,0)
  assert.match(attempt.stderr,/ISSUE_APP_SCOPE/)
  assert.equal(f.head(),before)
 }finally{f.dispose()}
})

test('isolated Git rejects a task Issue whose owner-authored manifest does not match the request',
 {timeout:30000},()=>{
 const f=setup()
 try{
  const manifest={schema_version:1,requirement_id:'REQ-20261031-001',
   task_id:'T-002',title:'Different title',depends_on:[],
   allowed_paths:['app/web/src/']}
  f.prepareTaskIssue(manifest)
  f.prepare({schema_version:1,action:'register_task',
   request_id:'88888888-8888-4888-8888-888888888888',
   requirement_id:'REQ-20261031-001',task_id:'T-002',worker_id:'chat-A',
   expected_version:0,issue_number:1000,title:'Requested title',
   depends_on:[],allowed_paths:['app/web/src/']})
  const before=f.head()
  const attempt=f.execute()
  assert.notEqual(attempt.status,0)
  assert.match(attempt.stderr,/ISSUE_TASK_IDENTITY/)
  assert.equal(f.head(),before)
 }finally{f.dispose()}
})


test('isolated Git registers T-010 on reviewed V1 seed and safely replays after Task Issue edit',
 {timeout:40000},()=>{
 const f=setup({v1:true})
 try{
  const manifest={schema_version:1,requirement_id:'REQ-20261031-001',
   task_id:'T-010',title:'Add dashboard filtering',depends_on:['T-001'],
   allowed_paths:['app/web/src/']}
  f.prepareTaskIssue(manifest)
  f.prepare({schema_version:1,action:'register_task',
   request_id:'66666666-6666-4666-8666-666666666666',
   requirement_id:'REQ-20261031-001',task_id:'T-010',
   worker_id:'chat-A',expected_version:1,issue_number:1000,
   title:manifest.title,depends_on:manifest.depends_on,
   allowed_paths:manifest.allowed_paths})
  const added=f.execute()
  assert.equal(added.status,0,added.stderr)
  const updated=f.snapshot()
  assert.equal(updated.version,2)
  assert.equal(updated.tasks.length,10)
  assert.equal(updated.tasks[9].task_id,'T-010')
  assert.equal(updated.tasks[9].issue_number,1000)
  assert.equal(updated.tasks[9].status,'READY')
  assert.equal(updated.tasks[9].claim,null)
  const prev=f.head()
  f.prepareTaskIssue({...manifest,title:'Changed Issue after registration'})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const replay=f.execute()
  assert.equal(replay.status,0,replay.stderr)
  assert.equal(f.head(),prev)
  assert.equal(f.snapshot().tasks.length,10)
 }finally{f.dispose()}
})

test('isolated Git refuses a state push if trusted main changes after initial validation',
 {timeout:30000},()=>{
 const f=setup()
 try{
  const before=f.head()
  const attempt=f.execute({PRP_MOCK_DRIFT_MAIN:'1'})
  assert.notEqual(attempt.status,0)
  assert.match(attempt.stderr,/ISSUE_MAIN_CHANGED_BEFORE_PUSH/)
  assert.equal(f.head(),before)
  assert.equal(f.snapshot().version,0)
  assert.equal(f.snapshot().tasks[0].claim,null)
  assert.notEqual(git(f.root,'--git-dir',f.origin,'rev-parse','refs/heads/main'),f.initialMain)
 }finally{f.dispose()}
})
