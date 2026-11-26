import {readFileSync,writeFileSync,mkdtempSync,mkdirSync,lstatSync} from 'node:fs'
import {join} from 'node:path'
import {tmpdir} from 'node:os'
import {execFileSync} from 'node:child_process'
import {fileURLToPath} from 'node:url'
import {resolve} from 'node:path'
import {validateIssueEvent} from './issue-ingress.mjs'
import {historicalNote,isHistoricalNote} from './ruleset-415-attestation.mjs'
import {applyCommand,validateSnapshot,CollabError,requireMigratedLiveState} from './core.mjs'
export {requireMigratedLiveState}
import {verifyStateBranchRuleset} from './state-rule-policy.mjs'
import {applyOwnerIssuedMigration} from './issue-migrate.mjs'

const REPO='micor-cjj-spec/matrix-prp',EXPECTED_APP_ID=5561446,EXPECTED_RULESET_ID=26294671,SHA=/^[a-f0-9]{40}$/
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const plain=x=>x!==null&&typeof x==='object'&&!Array.isArray(x)
const run=(program,args,options={})=>execFileSync(program,args,{
 encoding:'utf8',timeout:15000,maxBuffer:4*1024*1024,...options}).trim()
const gh=(endpoint,token)=>JSON.parse(run('gh',['api',endpoint],token?{env:{...process.env,GH_TOKEN:token}}:{}))
const git=(...args)=>run('git',args)
export function verifyTaskIssue(issue,validated){
 const {command,actor,actorId,source_issue}=validated
 check(command?.type==='register_task'&&issue?.number===command.issue_number&&
   issue.number!==source_issue&&issue.state==='open'&&!issue.pull_request&&
   issue.user?.login===actor&&issue.user?.id===actorId&&
   issue.author_association==='OWNER'&&
   issue.title==='[TASK]['+command.requirement_id+'/'+command.task_id+'] '+command.title,
   'ISSUE_TASK_IDENTITY')
 check(typeof issue.body==='string','ISSUE_TASK_BODY')
 const markers=[...issue.body.matchAll(/<!-- PRP_TASK_MANIFEST\n([\s\S]*?)\n-->/g)]
 check(markers.length===1,'ISSUE_TASK_MANIFEST_COUNT')
 let manifest
 try{manifest=JSON.parse(markers[0][1])}catch{throw new CollabError('ISSUE_TASK_MANIFEST_JSON')}
 const fields=['schema_version','requirement_id','task_id','title','depends_on','allowed_paths']
 check(plain(manifest)&&Object.keys(manifest).length===fields.length&&
   Object.keys(manifest).every(k=>fields.includes(k))&&manifest.schema_version===1&&
   manifest.requirement_id===command.requirement_id&&
   manifest.task_id===command.task_id&&manifest.title===command.title&&
   JSON.stringify(manifest.depends_on)===JSON.stringify(command.depends_on)&&
   JSON.stringify(manifest.allowed_paths)===JSON.stringify(command.allowed_paths),
   'ISSUE_TASK_MANIFEST_MISMATCH')
 return true
}

export function applyAuthenticatedIssue(snapshot,validated,now,verifyRemote=()=>false,
    reviewedEvidence=null){
 validateSnapshot(snapshot)
 const {command,expected_version,actor}=validated
 const replay=snapshot.processed_requests.some(r=>r.request_id===command.request_id)
 check(replay||snapshot.version===expected_version,'ISSUE_STALE_VERSION')
 check(actor==='micor-cjj-spec','ISSUE_UNTRUSTED_ACTOR')
 const context={actor,now,recoveryAuthorized:validated.recoveryAuthorized===true}
 // A recorded request has already passed remote evidence checks at its first
 // successful state transition. Replay still checks actor and exact fingerprint
 // in applyCommand, but must not depend on a feature branch remaining at that SHA.
 if(replay)return applyCommand(snapshot,command,context)
 if(command.type==='accept'){
   const task=snapshot.tasks.find(t=>t.task_id===command.task_id)
   check(task?.status==='IN_REVIEW' &&
     task.claim?.actor===actor &&
     task.claim?.worker_id===command.worker_id &&
     task.claim?.claim_id===command.claim_id,
     'ISSUE_ACCEPT_CLAIM_MISMATCH')
   check(task.pr_number===command.pr_number && task.head_sha===command.head_sha,
     'ISSUE_ACCEPT_SUBMISSION_MISMATCH')
   check(reviewedEvidence?.reviewerAuthorized===true &&
     reviewedEvidence?.ciVerified===true &&
     reviewedEvidence?.mergedIntoIntegration===true,
     'ISSUE_ACCEPT_TRUSTED_REVIEW_REQUIRED')
   if(validated.historical415===true)check(validated.policyAttestation&&command.note===historicalNote(validated.policyAttestation)&&reviewedEvidence.historical415Verified===true,'ISSUE_HISTORICAL_PROOF_REQUIRED')
   else check(!isHistoricalNote(command.note),'ISSUE_HISTORICAL_ACTION_REQUIRED')
   const marked446=typeof command.note==='string'&&command.note.startsWith('PRP_HISTORICAL_446_V1:')
   check(marked446===(validated.historical446===true)&&(!marked446||(validated.ownerPolicy===true&&reviewedEvidence.historical446Verified===true)),'ISSUE_HISTORICAL_446_PROOF_REQUIRED')
   const receiptMarked=typeof command.note==='string'&&command.note.startsWith('PRP_PREMERGE_RECEIPT_V1:')
   check(receiptMarked===(validated.receiptAccept===true)&&(!receiptMarked||(validated.ownerPolicy===true&&reviewedEvidence.receiptEvidenceVerified===true)),'ISSUE_RECEIPT_PROOF_REQUIRED')
   if(validated.ownerPolicy===true)check(reviewedEvidence.ownerRulesetAttested===true,'ISSUE_OWNER_POLICY_PROOF_REQUIRED')
   else check(!(typeof command.note==='string'&&command.note.startsWith('PRP_RULESET_ATTESTATION_V1:')),'ISSUE_OWNER_POLICY_ACTION_REQUIRED')
   context.reviewerAuthorized=true
   context.ciVerified=true
   context.mergedIntoIntegration=true
 }
 if(command.type==='register_task')
   check(validated.taskIssueVerified===true,'ISSUE_TASK_NOT_VERIFIED')
 if(['checkpoint','handoff','takeover'].includes(command.type)){
   const task=snapshot.tasks.find(t=>t.task_id===command.task_id)
   const checkpoint=command.type==='checkpoint'
     ? command.checkpoint
     : (command.checkpoint??task?.checkpoint)
   check(checkpoint && verifyRemote(checkpoint),'ISSUE_UNVERIFIED_RECOVERY_HEAD')
   if(command.type==='takeover')context.gitEvidenceVerified=true
 }
 return applyCommand(snapshot,command,context)
}
function verifyBranchAndRunner(env){
 check(env.GITHUB_EVENT_NAME==='issues'&&env.GITHUB_REF==='refs/heads/main'&&
   env.GITHUB_EVENT_ACTION==='opened'&&env.GITHUB_ACTOR==='micor-cjj-spec'&&
   env.GITHUB_REPOSITORY===REPO,'ISSUE_UNTRUSTED_RUNNER')
 check(git('rev-parse','HEAD')===env.GITHUB_SHA,'ISSUE_SOURCE_REVISION')
 const main=git('ls-remote','--exit-code','--refs','origin','refs/heads/main').split('\t')
 check(main.length===2&&main[0]===env.GITHUB_SHA&&
   main[1]==='refs/heads/main','ISSUE_MAIN_HEAD_CHANGED')
 const hold=JSON.parse(readFileSync('app/deploy/publication-hold.json','utf8'))
 check(hold?.schema_version===1&&typeof hold.reason==='string'&&
   hold.reason.trim().length>0,'ISSUE_PUBLICATION_NOT_HELD')
 check(typeof env.COLLAB_APP_TOKEN==='string'&&env.COLLAB_APP_TOKEN.length>0,
   'ISSUE_APP_TOKEN_MISSING')
 check(env.COLLAB_APP_ID===String(EXPECTED_APP_ID),'ISSUE_APP_ID')
 check(env.COLLAB_RULESET_ID===String(EXPECTED_RULESET_ID),'ISSUE_RULESET_ID')
 const ruleset=gh('repos/'+REPO+'/rulesets/'+EXPECTED_RULESET_ID,env.COLLAB_APP_TOKEN)
 verifyStateBranchRuleset(ruleset,EXPECTED_APP_ID)
 const installation=gh('installation/repositories',env.COLLAB_APP_TOKEN)
 check(installation?.total_count===1&&installation?.repositories?.length===1&&
   installation.repositories[0]?.full_name===REPO,'ISSUE_APP_SCOPE')
 const mainStatus=gh('repos/'+REPO+'/branches/main')
 check(mainStatus.protected===true,'ISSUE_MAIN_NOT_PROTECTED')
 const status=gh('repos/'+REPO+'/branches/prp-collab-state')
 check(status.protected===true,'ISSUE_STATE_NOT_PROTECTED')
}
function verifiedGitCheckpoint(cp){
 const name=cp.branch
 check(name!=='main'&&name!=='prp-collab-state','ISSUE_RECOVERY_BRANCH')
 const observed=git('ls-remote','--exit-code','--refs','origin','refs/heads/'+name)
 return observed===cp.head_sha+'\trefs/heads/'+name
}
export function redactedReceipt(receipt,meta){
 return {request_id:receipt.request_id,action:receipt.type,
  requirement_id:meta.requirement_id,task_id:receipt.task_id,
  version:receipt.version,status:receipt.status,
  task_issue_number:receipt.issue_number,state_sha:meta.state_sha}
}
function receiptMarkdown(info){
 return ['### PRP collaboration request completed','',
  'Request ID: '+info.request_id,
  'Operation: '+info.action,
  'Task: '+info.requirement_id+'/'+info.task_id,
  ...(info.task_issue_number?[ 'Task Issue: #'+info.task_issue_number ]:[]),
  'State version: '+info.version,'Remote state SHA: '+info.state_sha,
  '','Result was committed using a non-force Git push.',
  'Public receipt excludes claim credentials.'].join('\n')+'\n'
}
// Resolve only an internally derived receipt path in the isolated state worktree.
function receiptLocalPath(tmp,path,create=false){
 const parts=path.split('/')
 let here=tmp
 for(const part of parts.slice(0,-1)){
   here=join(here,part)
   let stat
   try{stat=lstatSync(here)}catch(e){if(e.code!=='ENOENT')throw e}
   if(!stat){if(!create)return null;mkdirSync(here,{mode:0o700});stat=lstatSync(here)}
   check(stat.isDirectory()&&!stat.isSymbolicLink(),'ISSUE_RECEIPT_DIRECTORY')
 }
 const file=join(tmp,path)
 try{const stat=lstatSync(file);check(stat.isFile()&&!stat.isSymbolicLink(),'ISSUE_RECEIPT_FILE')}
 catch(e){if(e.code!=='ENOENT')throw e}
 return file
}
function existingReceiptBytes(tmp,path){
 const file=receiptLocalPath(tmp,path)
 if(!file)return null
 try{return readFileSync(file,'utf8')}catch(e){if(e.code==='ENOENT')return null;throw e}
}
async function captureReceiptTransaction({before,validated,env,event,head,base,stateRef,tmp}){
 const {trustedReviewContext,ghApi}=await import('./review-context.mjs')
 const receiptRuntime=await import('./review-receipt-runtime.mjs')
 const {submittedReceiptPath,verifyReceiptOrigin,receiptAppendMarker}=receiptRuntime
 const {planReceiptAppend,parseStoredReceipt,verifyReceiptAppendCommit}=await import('./review-receipt-store.mjs')
 const command=validated.command
 check(validated.captureReceipt===true&&validated.ownerPolicy===true&&validated.expectedStateSha===head&&
   validated.expected_version===before.version&&!before.processed_requests.some(x=>x.request_id===command.request_id),'ISSUE_RECEIPT_STATE')
 const proof=Object.freeze({actorId:validated.actorId,sourceIssue:validated.source_issue,
   issueCreatedAt:validated.issueCreatedAt,stateSha:head,expectedStateSha:validated.expectedStateSha,
   expectedVersion:validated.expected_version,note:command.note,captureReceipt:true})
 const path=submittedReceiptPath(before,command.task_id)
 const existingBytes=existingReceiptBytes(tmp,path)
 const original=existingBytes===null?null:parseStoredReceipt(existingBytes)
 const capturedAt=new Date().toISOString()
 const collect=()=>{
   const x=trustedReviewContext(before,command,env,ghApi,proof,receiptRuntime)
   check(x.captureEvidenceVerified===true,'ISSUE_RECEIPT_CAPTURE_REQUIRED')
   if(original){
     verifyReceiptOrigin(before,command.task_id,head,env.GITHUB_SHA,original,ghApi,new Date().toISOString())
     x.evidence.captureOrigin=original.body.capture_origin
   }
   const plan=planReceiptAppend({snapshot:before,taskId:command.task_id,evidence:x.evidence,capturedAt,
     expectedStateSha:head,observedStateSha:head,existingBytes})
   check(plan.path===path,'ISSUE_RECEIPT_PATH')
   return plan
 }
 const plan=collect()
 const recheck=()=>{
   verifyBranchAndRunner(env)
   check(git('ls-remote','--exit-code','--refs','origin',stateRef)===base,'ISSUE_RACE_BEFORE_PUSH')
   validateIssueEvent(env,event,gh('repos/'+REPO+'/issues/'+validated.source_issue))
 }
 let expected=head
 if(plan.action==='append'){
   const file=receiptLocalPath(tmp,path,true)
   writeFileSync(file,plan.bytes,{mode:0o600,flag:'wx'})
   git('-C',tmp,'add','--',path)
   check(git('-C',tmp,'diff','--cached','--name-status')==='A\t'+path,'ISSUE_RECEIPT_WRITE_SCOPE')
   git('-C',tmp,'diff','--cached','--check')
   git('-C',tmp,'config','user.name','prp-collab-writer[bot]')
   git('-C',tmp,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
   git('-C',tmp,'commit','-m','chore(collab): capture receipt '+command.requirement_id+'/'+command.task_id,
     '-m','Request-issue: '+validated.source_issue,'-m','Request-id: '+command.request_id)
   expected=git('-C',tmp,'rev-parse','HEAD')
   const parents=git('-C',tmp,'show','-s','--format=%P',expected).split(' ').map(sha=>({sha}))
   const diff=git('-C',tmp,'diff-tree','--no-commit-id','--name-status','-r',expected)
   check(diff==='A\t'+path,'ISSUE_RECEIPT_WRITE_SCOPE')
   verifyReceiptAppendCommit(plan,{commit:{sha:expected,parents},parent:head,files:[{filename:path,status:'added'}],
     committedBytes:execFileSync('git',['-C',tmp,'show',expected+':'+path],{encoding:'utf8',timeout:15000,maxBuffer:65536}),remoteBefore:head})
   recheck()
   const fresh=collect()
   check(fresh.action==='append'&&fresh.path===plan.path&&fresh.bytes===plan.bytes&&fresh.digest===plan.digest,'ISSUE_RECEIPT_EVIDENCE_REVOKED')
   recheck()
   git('-C',tmp,'push','origin','HEAD:'+stateRef)
 }else{
   check(plan.action==='replay','ISSUE_RECEIPT_PLAN')
   recheck()
 }
 const remote=git('ls-remote','--exit-code','--refs','origin',stateRef)
 check(remote===expected+'\t'+stateRef,'ISSUE_REMOTE_POST_PUSH_MISMATCH')
 git('fetch','--no-tags','origin',stateRef)
 check(git('rev-parse','FETCH_HEAD')===expected,'ISSUE_RECEIPT_POST_PUSH_REF')
 const bytes=execFileSync('git',['show',expected+':'+path],{encoding:'utf8',timeout:15000,maxBuffer:65536})
 check(bytes===plan.bytes,'ISSUE_RECEIPT_POST_PUSH_BYTES')
 writeFileSync(join(env.RUNNER_TEMP,'prp-issue-receipt.md'),[
   '### PRP collaboration pre-merge receipt '+(plan.action==='append'?'committed':'replayed'),
   '', 'Request ID: '+command.request_id,'Task: '+command.requirement_id+'/'+command.task_id,
   'State version (unchanged): '+before.version,'Remote state SHA: '+expected,'Receipt digest: '+plan.digest,
   'No task status changed. No PR was merged. No acceptance was executed.'
 ].join('\n')+'\n',{mode:0o600,flag:'wx'})
 if(plan.action==='append')console.log(receiptAppendMarker(validated.source_issue,expected,plan.digest))
}
async function main(){
 const env=process.env
 const event=JSON.parse(readFileSync(env.GITHUB_EVENT_PATH,'utf8'))
 const issue=gh('repos/'+REPO+'/issues/'+event.issue?.number)
 const validated=validateIssueEvent(env,event,issue)
 verifyBranchAndRunner(env)
 if(validated.oneShotProbe===true){
   const stateRef='refs/heads/prp-collab-state'
   const current=git('ls-remote','--exit-code','--refs','origin',stateRef)
   const [head,ref]=current.split('\t')
   check(ref===stateRef&&SHA.test(head),'ISSUE_PROBE_STATE_REF')
   const receipt=['### PRP collaboration read-only probe passed','',
     'Request ID: '+validated.command.request_id,
     'Source Issue: #'+validated.source_issue,
     'State SHA observed: '+head,
     '','Verified owner Issue event, reviewed main source, publication hold,',
     'branch protections, state Ruleset and one-repository App installation scope.',
     '**No task was claimed and no Git state was written.**',
     'This probe does not prove App write permission or a real Ruleset bypass push.']
   writeFileSync(join(env.RUNNER_TEMP,'prp-issue-receipt.md'),
     receipt.join('\n')+'\n',{mode:0o600,flag:'wx'})
   console.log('PRP_COLLAB_PROBE_READ_ONLY='+validated.source_issue)
   console.log('PRP_COLLAB_PROBE_STATE_SHA='+head)
   return
 }
 if(validated.oneShotMigration===true){
   const result=applyOwnerIssuedMigration(validated,env)
   const summary=['### PRP V0 to V1 migration completed','',
     'Request ID: '+result.request_id,
     'Requirement: '+result.requirement_id,
     'State version: '+result.version,
     'Remote state SHA: '+result.state_sha,
     '','Completed with an owner-authenticated GitHub Issue and a non-force App push.']
   writeFileSync(join(env.RUNNER_TEMP,'prp-issue-receipt.md'),
     summary.join('\n')+'\n',{mode:0o600,flag:'wx'})
   console.log('PRP_COLLAB_ISSUE_MIGRATION='+result.source_issue)
   return
 }
 const stateRef='refs/heads/prp-collab-state'
 const base=git('ls-remote','--exit-code','--refs','origin',stateRef)
 const [head,ref]=base.split('\t')
 check(ref===stateRef&&SHA.test(head),'ISSUE_STATE_REF')
 const tmp=mkdtempSync(join(env.RUNNER_TEMP||tmpdir(),'prp-issue-'))
 git('fetch','--no-tags','origin',stateRef)
 check(git('rev-parse','FETCH_HEAD')===head,'ISSUE_STATE_RACE')
 git('worktree','add','--detach',tmp,head)
 const path='requirements/'+validated.command.requirement_id+'.json'
 const file=join(tmp,path)
 const before=JSON.parse(readFileSync(file,'utf8'))
 requireMigratedLiveState(before)
 if(validated.captureReceipt===true){
   await captureReceiptTransaction({before,validated,env,event,head,base,stateRef,tmp})
   return
 }
 // A successfully recorded registration is immutable in the state ledger.
 // Replays must not depend on the mutable Task Issue body still being present.
 if(validated.command.type==='register_task' &&
    !before.processed_requests?.some(r=>r.request_id===validated.command.request_id)){
   const taskIssue=gh('repos/'+REPO+'/issues/'+validated.command.issue_number)
   verifyTaskIssue(taskIssue,validated)
   validated.taskIssueVerified=true
 }
 // Acceptance is intentionally different from a worker command: no positive
 // reviewer flags may arrive from the Issue. The protected main trust root
 // must independently verify the merged PR, protected integration base, exact
 // head, full latest Actions job set and PR-event workflow provenance.
 const alreadyApplied=before.processed_requests?.some(r=>
   r.request_id===validated.command.request_id)===true
 // The isolated Git harness exercises legacy claim/handoff/release with a
 // minimal runner. Load high-privilege review modules only for genuine new
 // accept requests; never weaken the accept proof or permit a fallback.
 let loadReview=null
 let verifiedReview=null
 if(validated.command.type==='accept'&&!alreadyApplied){
   const {trustedReviewContext,ghApi}=await import('./review-context.mjs')
   if(validated.historical415===true){
     const {trustedHistorical415Context}=await import('./review-historical-owner-415.mjs')
     loadReview=()=>trustedHistorical415Context(before,validated,head,env,route=>gh(route))
   }else if(validated.ownerPolicy===true){
     check(validated.expectedStateSha===head&&validated.expected_version===before.version,
       'ISSUE_OWNER_POLICY_STATE_MISMATCH')
     const proof=Object.freeze({actorId:validated.actorId,sourceIssue:validated.source_issue,
       issueCreatedAt:validated.issueCreatedAt,stateSha:head,expectedStateSha:validated.expectedStateSha,
       expectedVersion:validated.expected_version,note:validated.command.note,...(validated.historical446===true?{historical446:true}:{}),...(validated.receiptAccept===true?{receiptAccept:true}:{})})
     const receiptRuntime=validated.receiptAccept===true?await import('./review-receipt-runtime.mjs'):undefined
     loadReview=validated.historical446===true||validated.receiptAccept===true
       ?()=>trustedReviewContext(before,validated.command,env,ghApi,proof,receiptRuntime)
       :()=>trustedReviewContext(before,validated.command,env,route=>gh(route),proof)
   }else loadReview=()=>trustedReviewContext(before,validated.command,env,route=>gh(route))
   verifiedReview=loadReview()
 }
 const {snapshot,receipt}=applyAuthenticatedIssue(before,validated,
   new Date().toISOString(),verifiedGitCheckpoint,verifiedReview)
 const replay=snapshot===before
 if(!replay){
   writeFileSync(file,JSON.stringify(snapshot,null,2)+'\n',{mode:0o600})
   git('-C',tmp,'add','--',path)
   check(git('-C',tmp,'diff','--cached','--name-only')===path,'ISSUE_WRITE_SCOPE')
   git('-C',tmp,'diff','--cached','--check')
   git('-C',tmp,'config','user.name','prp-collab-writer[bot]')
   git('-C',tmp,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
   git('-C',tmp,'commit','-m','chore(collab): '+validated.command.type+' '+
     validated.command.requirement_id+'/'+validated.command.task_id,
     '-m','Request-issue: '+validated.source_issue,
     '-m','Request-id: '+validated.command.request_id,
     '-m','Author: '+validated.actor)
   check(git('ls-remote','--exit-code','--refs','origin',
     'refs/heads/main')===env.GITHUB_SHA+'\trefs/heads/main',
     'ISSUE_MAIN_CHANGED_BEFORE_PUSH')
   check(git('ls-remote','--exit-code','--refs','origin',stateRef)===base,
     'ISSUE_RACE_BEFORE_PUSH')
   // Narrow the revocation window: re-read the owner Issue before Git CAS push.
   validateIssueEvent(env,event,gh('repos/'+REPO+'/issues/'+validated.source_issue))
   // Repeat external evidence verification at the final pre-push boundary.
   // The non-force Git CAS then prevents a stale state snapshot from winning.
   if(validated.command.type==='accept'){
     const fresh=loadReview()
     check(fresh.reviewerAuthorized===true&&fresh.ciVerified===true&&
       fresh.mergedIntoIntegration===true&&(validated.historical415!==true||fresh.historical415Verified===true)&&
       (validated.ownerPolicy!==true||fresh.ownerRulesetAttested===true)&&(validated.historical446!==true||fresh.historical446Verified===true)&&(validated.receiptAccept!==true||fresh.receiptEvidenceVerified===true),'ISSUE_ACCEPT_EVIDENCE_REVOKED')
     if(validated.receiptAccept===true)verifyBranchAndRunner(env)
     check(git('ls-remote','--exit-code','--refs','origin','refs/heads/main')===env.GITHUB_SHA+'\trefs/heads/main','ISSUE_MAIN_CHANGED_BEFORE_PUSH')
     check(git('ls-remote','--exit-code','--refs','origin',stateRef)===base,'ISSUE_RACE_BEFORE_PUSH')
     validateIssueEvent(env,event,gh('repos/'+REPO+'/issues/'+validated.source_issue))
   }
   git('-C',tmp,'push','origin','HEAD:'+stateRef)
 }
 const newSha=git('ls-remote','--exit-code','--refs','origin',stateRef).split('\t')[0]
 const expected=replay?head:git('-C',tmp,'rev-parse','HEAD')
 check(newSha===expected,'ISSUE_REMOTE_POST_PUSH_MISMATCH')
 const redacted=redactedReceipt(receipt,{requirement_id:validated.command.requirement_id,
   state_sha:newSha})
 writeFileSync(join(env.RUNNER_TEMP,'prp-issue-receipt.md'),receiptMarkdown(redacted),{
   mode:0o600,flag:'wx'})
 console.log('PRP_COLLAB_ISSUE_SUCCESS='+validated.source_issue)
 console.log('PRP_COLLAB_REMOTE_SHA='+newSha)
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
 main().catch(e=>{
   console.error('PRP_COLLAB_ISSUE_FAILURE='+(e instanceof CollabError?e.code:'TRANSACTION_FAILED'))
   if(process.env.PRP_COLLAB_TEST_DIAGNOSTICS==='1'){
     const detail=e?.stderr?.toString('utf8')||e?.message||'unknown'
     console.error('ISOLATED_TEST_DETAIL='+detail.replace(/\s+/g,' ').slice(0,280))
   }
   process.exitCode=1
 })
}
