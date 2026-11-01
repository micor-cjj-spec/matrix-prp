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
function setup(){
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
  'migration-guard.mjs','bootstrap-audit.mjs','state-rule-policy.mjs'])
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
 writeFileSync(join(seed,REQ),JSON.stringify(initial(),null,2)+'\n')
 git(seed,'add',REQ);git(seed,'commit','-m','initial state')
 git(seed,'push','origin','prp-collab-state')
 const first=git(root,'--git-dir',origin,'rev-parse',REF)
 git(root,'clone','--branch','main',origin,runner)
 const fakeDir=join(root,'bin');mkdirSync(fakeDir)
 const mock=[
  '#!/usr/bin/env bash','set -euo pipefail',
  '[[ "$1" == api ]] || exit 3',
  'case "$2" in',
  ' */issues/999) cat "$PRP_MOCK_ISSUE" ;;',
  ' */rulesets/26294671) cat "$PRP_MOCK_RULESET" ;;',
  ' */branches/prp-collab-state) echo "{\\"protected\\":true}" ;;',
  ' *) echo "UNKNOWN_GH_ROUTE" >&2; exit 3 ;;',
  'esac'
 ].join('\n')+'\n'
 writeFileSync(join(fakeDir,'gh'),mock,{mode:0o755})
 const eventPath=join(root,'event.json'),issuePath=join(root,'issue.json')
 const rulePath=join(root,'rule.json'),temp=join(root,'run-temp')
 mkdirSync(temp)
 writeFileSync(rulePath,JSON.stringify({
  id:26294671,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:[REF],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  bypass_actors:[{actor_type:'Integration',actor_id:5561446,bypass_mode:'always'}]
 }))
 const prepare=(payload,author=OWNER)=>{
  const issue={number:999,title:'[PRP-COLLAB-REQUEST]',state:'open',
   user:{login:author,id:101},author_association:'OWNER',body:JSON.stringify(payload)}
  const evt={action:'opened',sender:{login:author,id:101,type:'User'},
   repository:{full_name:REPO,default_branch:'main',owner:{login:OWNER}},
   issue}
  writeFileSync(eventPath,JSON.stringify(evt));writeFileSync(issuePath,JSON.stringify(issue))
 }
 prepare(request())
 const env={...process.env,PATH:fakeDir+':'+process.env.PATH,
  GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'issues',
  GITHUB_EVENT_ACTION:'opened',GITHUB_EVENT_PATH:eventPath,
  GITHUB_REF:'refs/heads/main',GITHUB_SHA:main,GITHUB_ACTOR:OWNER,
  GITHUB_REPOSITORY:REPO,GITHUB_REPOSITORY_OWNER:OWNER,
  GITHUB_WORKFLOW_REF:REPO+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main',
  GH_TOKEN:'not-a-real-token',COLLAB_APP_ID:'5561446',
  COLLAB_RULESET_ID:'26294671',RUNNER_TEMP:temp,
  PRP_MOCK_ISSUE:issuePath,PRP_MOCK_RULESET:rulePath}
 const execute=()=>spawnSync(process.execPath,['app/scripts/dev-collab/issue-transaction.mjs'],
  {cwd:runner,env,encoding:'utf8',timeout:15000})
 const head=()=>git(root,'--git-dir',origin,'rev-parse',REF)
 const snapshot=()=>JSON.parse(git(root,'--git-dir',origin,'show',REF+':'+REQ))
 return {root,prepare,execute,head,snapshot,initialHead:first,
  dispose:()=>rmSync(root,{recursive:true,force:true})}
}
test('isolated bare Git: owner issue atomically claims, repeat is idempotent and stale claim rejects',
 {timeout:40000},()=>{
 const f=setup()
 try{
  const first=f.execute()
  assert.equal(first.status,0,first.stderr)
  assert.match(first.stdout,/PRP_COLLAB_ISSUE_SUCCESS=999/)
  assert.notEqual(f.head(),f.initialHead)
  const s=f.snapshot()
  assert.equal(s.version,1)
  assert.equal(s.tasks[0].claim.worker_id,'chat-A')
  const receipt=readFileSync(join(f.root,'run-temp/prp-issue-receipt.md'),'utf8')
  assert.doesNotMatch(receipt,new RegExp(s.tasks[0].claim.claim_id))
  const prev=f.head()
  // New run temp simulates a fresh Actions invocation using the same Issue event.
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'))
  const replay=f.execute()
  assert.equal(replay.status,0,replay.stderr)
  assert.equal(f.head(),prev)
  f.prepare(request('22222222-2222-4222-8222-222222222222',0))
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'))
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
