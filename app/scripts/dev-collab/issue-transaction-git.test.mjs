import test from 'node:test'
import assert from 'node:assert/strict'
import {execFileSync,spawnSync} from 'node:child_process'
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,cpSync,rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {buildOwnerRulesetAttestation,REQUIRED_CHECKS} from './review-gate.mjs'
import {historical271Fixture} from './review-historical-271.test.mjs'
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
   depends_on:[],allowed_paths:number===2?['app/docs/dev-collab/']:[],claim:null})
 }
 return snapshot
}
const policy=()=>({
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
  "bypass_actors": [],
  "current_user_can_bypass": "never"
})
const reviewHead='a'.repeat(40),reviewMerge='b'.repeat(40),reviewClaim='11111111-1111-4111-8111-111111111111'
function setup({v1=false,review=false,capture=false,historicalTask=null}={}){
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
  'migration-guard.mjs','bootstrap-audit.mjs','state-rule-policy.mjs','task-scope-policy.mjs','ruleset-415-attestation.mjs',
  ...(review?['review-context.mjs','review-gate.mjs','review-provenance.mjs','review-receipt-runtime.mjs','review-receipt.mjs','review-receipt-store.mjs']:[]),...(historicalTask?['review-historical-271.mjs']:[])])
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
 const seedSnapshot=historicalTask?historical271Fixture(historicalTask).snapshot:(v1||review)?reviewedV1():initial()
 if(review&&!historicalTask)Object.assign(seedSnapshot.tasks[0],{status:'IN_REVIEW',
   claim:{claim_id:reviewClaim,worker_id:'chat-A',actor:OWNER},pr_number:138,head_sha:reviewHead})
 if(capture){
   const submitId='33333333-3333-4333-8333-333333333333'
   seedSnapshot.processed_requests.push({request_id:submitId,fingerprint:'a'.repeat(64),actor:OWNER,
     receipt:{type:'submit',task_id:'T-001',request_id:submitId,version:1,status:'IN_REVIEW',replayed:false}})
 }
 writeFileSync(join(seed,REQ),JSON.stringify(seedSnapshot,null,2)+'\n')
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
  'if [[ "$2" == --method ]]; then [[ "$3" == GET && "$4" == --hostname && "$5" == github.com ]] || exit 3; set -- api "$6"; fi',
  'if [[ -n "${PRP_MOCK_REVIEW_ROUTES:-}" && "$2" != */issues/* && "$2" != */rulesets/26294671 && "$2" != installation/repositories && "$2" != */branches/prp-collab-state ]]; then [[ "$GH_TOKEN" == not-a-real-token ]] || exit 4; node "$PRP_MOCK_REVIEW_READER" "$2"; exit $?; fi',
  'case "$2" in',
  ' */issues/999) if [[ "${PRP_MOCK_REVOKE_ON_RECHECK:-}" == "1" ]]; then n=$(cat "$PRP_MOCK_ISSUE_READ_COUNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$PRP_MOCK_ISSUE_READ_COUNT"; if (( n >= 2 )); then cat "$PRP_MOCK_ISSUE_REVOKED"; else cat "$PRP_MOCK_ISSUE"; fi; else cat "$PRP_MOCK_ISSUE"; fi ;;',
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
 const taskIssuePath=join(root,'task-issue.json'),revokedIssuePath=join(root,'revoked-issue.json')
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
  const issue={number:999,title:'[PRP-COLLAB-REQUEST]',state:'open',created_at:new Date().toISOString(),
   user:{login:author,id:123868412},author_association:'OWNER',body:JSON.stringify(payload)}
  const evt={action:'opened',sender:{login:author,id:123868412,type:'User'},
   repository:{full_name:REPO,default_branch:'main',owner:{login:OWNER,id:123868412}},
   issue}
  writeFileSync(eventPath,JSON.stringify(evt));writeFileSync(issuePath,JSON.stringify(issue))
  writeFileSync(revokedIssuePath,JSON.stringify({...issue,state:'closed'}))
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
  PRP_MOCK_ISSUE_REVOKED:revokedIssuePath,PRP_MOCK_ISSUE_READ_COUNT:join(root,'issue-read-count'),
  PRP_MOCK_RULESET:rulePath,PRP_MOCK_APP_REPOS:appReposPath,PRP_MOCK_SEED:seed}
 const routesPath=join(root,'review-routes.json'),readerPath=join(root,'review-reader.mjs'),ruleReadsPath=join(root,'integration-rule-reads')
 writeFileSync(readerPath,`import {readFileSync,writeFileSync,existsSync} from 'node:fs'
 const key=process.argv[2],routes=JSON.parse(readFileSync(process.env.PRP_MOCK_REVIEW_ROUTES,'utf8'))
 if(!Object.hasOwn(routes,key))process.exit(3)
 const value=routes[key]
 if(key.endsWith('/rulesets/28050327')){
   const f=process.env.PRP_MOCK_RULE_READS
   const n=(existsSync(f)?Number(readFileSync(f,'utf8')):0)+1
   writeFileSync(f,String(n))
   if(process.env.PRP_MOCK_POLICY_DRIFT==='1'&&n>=Number(process.env.PRP_MOCK_POLICY_DRIFT_AFTER||2))value.updated_at='2026-11-26T00:00:00Z'
 }
 console.log(JSON.stringify(value))`)
 const prepareReview=({missingAssociation=false}={})=>{
  assert.equal(review,true)
  const req='REQ-20261031-001',requestId='22222222-2222-4222-8222-222222222222',integration='integrate/'+req
  const note=buildOwnerRulesetAttestation(policy(),{requestId,action:'accept',requirementId:req,taskId:'T-001',
   prNumber:138,headSha:reviewHead,stateVersion:1,mainSha:main,stateSha:first,observedAt:new Date(Date.now()-1000).toISOString()})
  prepare({schema_version:1,action:'accept',request_id:requestId,requirement_id:req,task_id:'T-001',
   worker_id:'chat-A',claim_id:reviewClaim,expected_version:1,expected_state_sha:first,
   pr_number:138,head_sha:reviewHead,policy_attestation:note})
  const root='repos/'+REPO,headRef='feat/synthetic',repo={full_name:REPO,id:1261866723}
  const rule=policy();delete rule.bypass_actors
  const checkRuns=REQUIRED_CHECKS.map((name,i)=>({name,id:i+1,head_sha:reviewHead,status:'completed',conclusion:'success',app:{slug:'github-actions',id:15368},
   details_url:'https://github.com/'+REPO+'/actions/runs/'+(name==='impact-report'?102:name==='dev-collab-contract'?103:101)+'/job/'+(i+1)}))
  const routes={
   [root+'/branches/main']:{name:'main',protected:true,commit:{sha:main}},
   [root+'/branches/'+encodeURIComponent(integration)]:{name:integration,protected:true,commit:{sha:reviewMerge}},
   [root+'/rulesets/28050327']:rule,
   [root+'/pulls/138']:{number:138,changed_files:1,head:{sha:reviewHead,ref:headRef,repo},
    base:{ref:integration,repo},merged:true,merged_at:'2026-10-31T18:00:00Z',merge_commit_sha:reviewMerge},
   [root+'/pulls/138/files?per_page=100']:[{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}],
   [root+'/compare/'+reviewMerge+'...'+reviewMerge]:{status:'identical',behind_by:0,base_commit:{sha:reviewMerge},merge_base_commit:{sha:reviewMerge},commits:[]},
   [root+'/commits/'+reviewHead+'/check-runs?per_page=100']:{total_count:checkRuns.length,check_runs:checkRuns},
   [root+'/actions/runs/9001']:{id:9001,event:'issues',path:'.github/workflows/prp-collab-issue-ingress.yml',
    status:'in_progress',head_branch:'main',head_sha:main,run_attempt:1,created_at:new Date().toISOString(),
    actor:{login:OWNER,id:123868412},repository:repo}
  }
  for(const [id,name,path] of [[101,'CI','.github/workflows/ci.yml'],[102,'Feature Impact Report','.github/workflows/feature-impact.yml'],[103,'PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']]){
   const jobs=checkRuns.filter(c=>c.details_url.includes('/runs/'+id+'/')).map(c=>({name:c.name,id:c.id,run_id:id,run_attempt:1,head_sha:reviewHead,head_branch:headRef,workflow_name:name,status:'completed',conclusion:'success',started_at:'2026-10-31T17:01:00Z',completed_at:'2026-10-31T17:59:00Z'}))
   routes[root+'/actions/runs/'+id]={id,name,path,run_attempt:1,created_at:'2026-10-31T17:00:00Z',event:'pull_request',
    status:'completed',conclusion:'success',head_sha:reviewHead,head_branch:headRef,repository:repo,head_repository:repo,
    pull_requests:missingAssociation?[]:[{number:138,head:{sha:reviewHead},base:{ref:integration}}]}
   routes[root+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest']={total_count:jobs.length,jobs}
  }
  writeFileSync(routesPath,JSON.stringify(routes))
  return {GITHUB_RUN_ID:'9001',GITHUB_RUN_ATTEMPT:'1',PRP_MOCK_REVIEW_ROUTES:routesPath,PRP_MOCK_REVIEW_READER:readerPath,PRP_MOCK_RULE_READS:ruleReadsPath}
 }
 const prepareCapture=()=>{
   assert.equal(capture,true)
   const extra=prepareReview()
   const routes=JSON.parse(readFileSync(routesPath,'utf8')),root='repos/'+REPO
   const p=routes[root+'/pulls/138'],base='c'.repeat(40),synthetic='d'.repeat(40),tree='e'.repeat(40)
   Object.assign(p,{state:'open',merged:false,draft:false,mergeable:true,merge_commit_sha:synthetic});p.base.sha=base;delete p.merged_at
   routes[root+'/branches/'+encodeURIComponent(p.base.ref)].commit.sha=base
   routes[root+'/git/commits/'+synthetic]={sha:synthetic,tree:{sha:tree},parents:[{sha:base},{sha:reviewHead}]}
   routes[root+'/commits/'+reviewHead+'/check-runs?per_page=100&filter=latest']=routes[root+'/commits/'+reviewHead+'/check-runs?per_page=100']
   for(const n of ['ci.yml','feature-impact.yml','prp-dev-collab-contract.yml'])for(const ref of [base,synthetic])
     routes[root+'/contents/.github/workflows/'+n+'?ref='+ref]={sha:tree}
   for(const id of [101,102,103]){
     const run=routes[root+'/actions/runs/'+id]
     run.pull_requests=[{number:138,head:{sha:reviewHead,repo:{id:1261866723}},base:{ref:p.base.ref,sha:base,repo:{id:1261866723}}}]
     for(const j of routes[root+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest'].jobs){
       const action=id===101?'v4':'3d3c42e5aac5ba805825da76410c181273ba90b1',resolved=id===101?'11d5960a326750d5838078e36cf38b85af677262':action
       j.steps=[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+action,conclusion:'success',started_at:'2026-10-31T17:02:00Z',completed_at:'2026-10-31T17:02:05Z'}]
       routes[root+'/actions/jobs/'+j.id+'/logs']=[
        "2026-10-31T17:01:59Z Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")",
        '2026-10-31T17:02:00Z ##[group]Run actions/checkout@'+action,
        '2026-10-31T17:02:01Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags origin +'+synthetic+':refs/remotes/pull/138/merge',
        '2026-10-31T17:02:02Z [command]/usr/bin/git checkout --progress --force refs/remotes/pull/138/merge',
        '2026-10-31T17:02:03Z [command]/usr/bin/git log -1 --format=%H',
        '2026-10-31T17:02:04Z '+synthetic,'2026-10-31T17:02:06Z ##[group]Run tests'].join('\n')
     }
   }
   const requestId='44444444-4444-4444-8444-444444444444',req='REQ-20261031-001'
   const note=buildOwnerRulesetAttestation(policy(),{requestId,action:'capture_receipt',requirementId:req,taskId:'T-001',
     prNumber:138,headSha:reviewHead,stateVersion:1,mainSha:main,stateSha:first,observedAt:new Date(Date.now()-1000).toISOString()})
   prepare({schema_version:1,action:'capture_receipt',request_id:requestId,requirement_id:req,task_id:'T-001',
     worker_id:'chat-A',claim_id:reviewClaim,expected_version:1,expected_state_sha:first,pr_number:138,head_sha:reviewHead,policy_attestation:note})
   routes[root+'/actions/runs/9001'].created_at=new Date().toISOString()
   writeFileSync(routesPath,JSON.stringify(routes))
   const mockFetch=join(temp,'mock-fetch.mjs')
   // No network even if the production code unexpectedly attempts a different URL.
   writeFileSync(mockFetch,"import {readFileSync} from 'node:fs';globalThis.fetch=async (url,opts)=>{const u=new URL(url);if(u.origin!=='https://api.github.com'||opts?.headers?.Authorization!=='Bearer not-a-real-token')throw Error('unexpected external fetch');const value=JSON.parse(readFileSync(process.env.PRP_MOCK_REVIEW_ROUTES,'utf8'))[u.pathname.slice(1)];if(typeof value!=='string')throw Error('missing log fixture');return new Response(value,{status:200})}")
   return {...extra,NODE_OPTIONS:'--import='+mockFetch}
 }
 const prepareHistorical271=()=>{
   assert.ok(historicalTask&&review)
   const extra=prepareReview(),fixture=historical271Fixture(historicalTask,main,first)
   const {command,request_id,claim_id,HEAD}=fixture,req='REQ-20261031-001',version=fixture.snapshot.version
   const note=buildOwnerRulesetAttestation(policy(),{requestId:request_id,action:'accept',requirementId:req,taskId:historicalTask,
     prNumber:271,headSha:HEAD,stateVersion:version,mainSha:main,stateSha:first,observedAt:new Date(Date.now()-1000).toISOString()})
   prepare({schema_version:1,action:'accept_historical_271',request_id,requirement_id:req,task_id:historicalTask,
     worker_id:command.worker_id,claim_id,expected_version:version,expected_state_sha:first,pr_number:271,head_sha:HEAD,policy_attestation:note})
   const root='repos/'+REPO,oldRoutes=JSON.parse(readFileSync(routesPath,'utf8'))
   const routes={...fixture.routes,[root+'/rulesets/28050327']:oldRoutes[root+'/rulesets/28050327'],[root+'/actions/runs/9001']:oldRoutes[root+'/actions/runs/9001']}
   routes[root+'/actions/runs/9001'].created_at=new Date().toISOString()
   writeFileSync(routesPath,JSON.stringify(routes))
   const mockFetch=join(temp,'mock-fetch.mjs')
   writeFileSync(mockFetch,"import {readFileSync} from 'node:fs';globalThis.fetch=async (url,opts)=>{const u=new URL(url);if(u.origin!=='https://api.github.com'||opts?.headers?.Authorization!=='Bearer not-a-real-token')throw Error('unexpected external fetch');const value=JSON.parse(readFileSync(process.env.PRP_MOCK_REVIEW_ROUTES,'utf8'))[u.pathname.slice(1)];if(typeof value!=='string')throw Error('missing log fixture');return new Response(value,{status:200})}")
   return {...extra,NODE_OPTIONS:'--import='+mockFetch}
 }
 const execute=(extra={})=>spawnSync(process.execPath,['app/scripts/dev-collab/issue-transaction.mjs'],
  {cwd:runner,env:{...env,...extra},encoding:'utf8',timeout:capture||historicalTask?120000:15000})
 const head=()=>git(root,'--git-dir',origin,'rev-parse',REF)
 const snapshot=()=>JSON.parse(git(root,'--git-dir',origin,'show',REF+':'+REQ))
 return {root,prepare,prepareTaskIssue,prepareReview,prepareCapture,prepareHistorical271,execute,head,snapshot,initialHead:first,initialMain:main,origin,checkpointSha,appReposPath,ruleReadsPath,
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
test('isolated Git: two ChatGPT-labelled workers can claim independent tasks, not the same task or stale version',
 {timeout:50000},()=>{
 const f=setup({v1:true})
 try{
  const a={...request('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',1),worker_id:'chat-A'}
  f.prepare(a)
  assert.equal(f.execute().status,0)
  const afterA=f.head()
  assert.equal(f.snapshot().version,2)
  assert.equal(f.snapshot().tasks[0].claim.worker_id,'chat-A')

  // Session B read version 1 before A committed and must retry after refresh.
  const stale={...request('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',1),
   task_id:'T-002',worker_id:'chat-B'}
  f.prepare(stale)
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const rejected=f.execute()
  assert.notEqual(rejected.status,0)
  assert.match(rejected.stderr,/ISSUE_STALE_VERSION/)
  assert.equal(f.head(),afterA)
  assert.equal(f.snapshot().tasks[1].status,'READY')

  const fresh={...stale,request_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
   expected_version:2}
  f.prepare(fresh)
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  assert.equal(f.execute().status,0)
  const both=f.snapshot()
  assert.equal(both.version,3)
  assert.equal(both.tasks[0].claim.worker_id,'chat-A')
  assert.equal(both.tasks[1].claim.worker_id,'chat-B')
  assert.notEqual(both.tasks[0].claim.claim_id,both.tasks[1].claim.claim_id)
  const afterB=f.head()

  // A third label cannot claim a task already owned by Session A.
  f.prepare({...request('dddddddd-dddd-4ddd-8ddd-dddddddddddd',3),
   worker_id:'chat-C'})
  rmSync(join(f.root,'run-temp/prp-issue-receipt.md'),{force:true})
  const collision=f.execute()
  assert.notEqual(collision.status,0)
  assert.match(collision.stderr,/TASK_NOT_READY/)
  assert.equal(f.head(),afterB)
  assert.equal(f.snapshot().version,3)
 } finally {f.dispose()}
})
test('isolated Git: owner closes request after validation, no protected state push',
 {timeout:30000},()=>{
 const f=setup({v1:true})
 try{
  f.prepare(request(undefined,1))
  const before=f.head()
  const result=f.execute({PRP_MOCK_REVOKE_ON_RECHECK:'1'})
  assert.notEqual(result.status,0)
  assert.match(result.stderr,/INGRESS_ISSUE_MODIFIED/)
  assert.equal(f.head(),before)
  assert.equal(f.snapshot().version,1)
  assert.equal(f.snapshot().tasks[0].claim,null)
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
 const f=setup({v1:true})
 try{
  const manifest={schema_version:1,requirement_id:'REQ-20261031-001',
   task_id:'T-010',title:'Different title',depends_on:[],
   allowed_paths:['app/web/src/']}
  f.prepareTaskIssue(manifest)
  f.prepare({schema_version:1,action:'register_task',
   request_id:'88888888-8888-4888-8888-888888888888',
   requirement_id:'REQ-20261031-001',task_id:'T-010',worker_id:'chat-A',
   expected_version:1,issue_number:1000,title:'Requested title',
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
 const f=setup({v1:true})
 try{
  f.prepare(request(undefined,1))
  const before=f.head()
  const attempt=f.execute({PRP_MOCK_DRIFT_MAIN:'1'})
  assert.notEqual(attempt.status,0)
  assert.match(attempt.stderr,/ISSUE_MAIN_CHANGED_BEFORE_PUSH/)
  assert.equal(f.head(),before)
  assert.equal(f.snapshot().version,1)
  assert.equal(f.snapshot().tasks[0].claim,null)
  assert.notEqual(git(f.root,'--git-dir',f.origin,'rev-parse','refs/heads/main'),f.initialMain)
 }finally{f.dispose()}
})

test('isolated bare Git: ordinary owner Issue attestation rechecks live policy before non-force CAS', {timeout:30000},()=>{
 const f=setup({review:true})
 try{
  const before=f.snapshot(),initial=f.head()
  const res=f.execute(f.prepareReview())
  assert.equal(res.status,0,res.stderr)
  assert.match(res.stdout,/PRP_COLLAB_ISSUE_SUCCESS=999/)
  assert.notEqual(f.head(),initial)
  assert.equal(f.snapshot().version,2);assert.equal(f.snapshot().tasks[0].status,'DONE')
  assert.deepEqual(f.snapshot().tasks.slice(1),before.tasks.slice(1))
  assert.equal(Number(readFileSync(f.ruleReadsPath,'utf8')),2)
  assert.equal(git(f.root,'--git-dir',f.origin,'rev-parse',f.head()+'^'),initial)
 }finally{f.dispose()}
})
test('isolated bare Git: changed integration Ruleset at final recheck refuses CAS', {timeout:30000},()=>{
 const f=setup({review:true})
 try{
  const before=f.snapshot(),initial=f.head()
  const res=f.execute({...f.prepareReview(),PRP_MOCK_POLICY_DRIFT:'1'})
  assert.notEqual(res.status,0)
  assert.match(res.stderr,/OWNER_RULESET_ATTESTATION_POLICY|INTEGRATION_POLICY_DRIFT/)
  assert.equal(Number(readFileSync(f.ruleReadsPath,'utf8')),2)
  assert.equal(f.head(),initial);assert.deepEqual(f.snapshot(),before)
 }finally{f.dispose()}
})
test('isolated bare Git: missing PR association remains fail closed even with valid owner policy proof', {timeout:30000},()=>{
 const f=setup({review:true})
 try{
  const before=f.snapshot(),initial=f.head()
  const res=f.execute(f.prepareReview({missingAssociation:true}))
  assert.notEqual(res.status,0)
  assert.match(res.stderr,/WORKFLOW_PR_MISMATCH_/)
  assert.equal(f.head(),initial);assert.deepEqual(f.snapshot(),before)
 }finally{f.dispose()}
})

test('real isolated Git: Owner capture adds exactly one receipt, keeps requirement byte-identical', {timeout:120000},()=>{
 const f=setup({review:true,capture:true})
 try{
   const before=f.snapshot(),initial=f.head(),result=f.execute(f.prepareCapture())
   assert.equal(result.status,0,result.stderr)
   const head=f.head(),path='receipts/REQ-20261031-001/T-001/33333333-3333-4333-8333-333333333333.json'
   assert.notEqual(head,initial)
   assert.equal(git(f.root,'--git-dir',f.origin,'show','-s','--format=%P',head),initial)
   assert.equal(git(f.root,'--git-dir',f.origin,'diff','--name-status',initial,head),'A\t'+path)
   assert.deepEqual(f.snapshot(),before)
   const receipt=JSON.parse(git(f.root,'--git-dir',f.origin,'show',head+':'+path))
   assert.equal(receipt.body.state_sha,initial);assert.equal(receipt.body.state_version,1);assert.equal(receipt.body.checks.length,7)
   assert.match(result.stdout,new RegExp('PRP_COLLAB_RECEIPT_APPEND=999 '+head+' '+receipt.digest))
   assert.equal(JSON.stringify(receipt).includes(reviewClaim),false)
 }finally{f.dispose()}
})
test('real isolated Git: evidence drift in final capture recheck prevents any state write', {timeout:120000},()=>{
 const f=setup({review:true,capture:true})
 try{
   const initial=f.head(),before=f.snapshot()
   const result=f.execute({...f.prepareCapture(),PRP_MOCK_POLICY_DRIFT:'1',PRP_MOCK_POLICY_DRIFT_AFTER:'3'})
   assert.notEqual(result.status,0);assert.equal(f.head(),initial);assert.deepEqual(f.snapshot(),before)
 }finally{f.dispose()}
})

test('real isolated Git: historical #271 accepts T-002 and T-003 independently, one state file and exact replay', {timeout:300000},()=>{
 for(const historicalTask of ['T-002','T-003']){
  const h=setup({review:true,historicalTask})
  try{
   const before=h.snapshot(),extra=h.prepareHistorical271(),result=h.execute(extra)
   assert.equal(result.status,0,result.stderr)
   const after=h.snapshot(),sha=h.head()
   assert.equal(after.version,before.version+1)
   assert.equal(after.tasks.find(t=>t.task_id===historicalTask).status,'DONE')
   assert.deepEqual(after.tasks.filter(t=>t.task_id!==historicalTask),before.tasks.filter(t=>t.task_id!==historicalTask))
   assert.equal(git(h.root,'--git-dir',h.origin,'show','-s','--format=%P',sha),h.initialHead)
   assert.equal(git(h.root,'--git-dir',h.origin,'diff','--name-only',h.initialHead,sha),REQ)
   // A fresh runner temp directory simulates an independent retry of the same Issue.
   const retry=join(h.root,'retry-temp');mkdirSync(retry)
   const replay=h.execute({...extra,RUNNER_TEMP:retry})
   assert.equal(replay.status,0,replay.stderr);assert.equal(h.head(),sha)
  }finally{h.dispose()}
 }
})
test('real isolated Git: #271 final Ruleset recheck failure preserves the exact original state', {timeout:180000},()=>{
 const h=setup({review:true,historicalTask:'T-003'})
 try{
  const before=h.snapshot(),extra=h.prepareHistorical271(),result=h.execute({...extra,PRP_MOCK_POLICY_DRIFT:'1',PRP_MOCK_POLICY_DRIFT_AFTER:'3'})
  assert.notEqual(result.status,0);assert.match(result.stderr,/OWNER_RULESET_ATTESTATION_POLICY|INTEGRATION_POLICY_DRIFT/)
  assert.equal(h.head(),h.initialHead);assert.deepEqual(h.snapshot(),before)
 }finally{h.dispose()}
})
