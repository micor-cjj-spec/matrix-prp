import {readFileSync,writeFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {resolve} from 'node:path'
import {CollabError} from './core.mjs'
import {validateTaskScopeList} from './task-scope-policy.mjs'
import {validateOwnerAttestation,historicalNote} from './ruleset-415-attestation.mjs'

const REPO='micor-cjj-spec/matrix-prp'
// Numeric GitHub owner ID is stable across username changes and prevents an
// abandoned or renamed owner login from silently authorizing a different user.
const OWNER_ID=123868412
const WORKFLOW=REPO+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SHA=/^[0-9a-f]{40}$/
const REQ=/^REQ-[0-9]{8}-[0-9]{3}$/
const TASK=/^T-[0-9]{3}$/
const WORKER=/^[a-zA-Z0-9_-]{3,64}$/
const ACTIONS=new Set(['claim','start','progress','pause','block','resume','release',
 'checkpoint','handoff','takeover','submit','accept','capture_receipt','accept_receipt','accept_historical_415','accept_historical_446','accept_historical_271','rework','register_task','migrate_v1'])
const FIELDS=new Set(['schema_version','action','request_id','requirement_id',
 'task_id','worker_id','claim_id','note','pr_number','head_sha','checkpoint',
 'new_worker_id','expected_claim_id','expected_head_sha','expected_version',
 'expected_state_sha','expected_proposal_sha','issue_number','title','depends_on','allowed_paths','policy_attestation'])
const CP_FIELDS=new Set(['summary','next_step','branch','head_sha','tests','blockers','pr_number'])
const BASE_FIELDS=['schema_version','action','request_id','requirement_id',
 'task_id','worker_id','expected_version']
const ACTION_FIELDS={
 claim:[],
 start:['claim_id'],
 pause:['claim_id'],
 resume:['claim_id'],
 release:['claim_id'],
 progress:['claim_id','note','head_sha'],
 block:['claim_id','note'],
 rework:['claim_id','note'],
 checkpoint:['claim_id','checkpoint'],
 handoff:['claim_id','new_worker_id','expected_head_sha','note'],
 takeover:['claim_id','new_worker_id','expected_claim_id','expected_head_sha','note','checkpoint'],
 submit:['claim_id','pr_number','head_sha'],
 accept:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 capture_receipt:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 accept_receipt:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 accept_historical_446:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 accept_historical_271:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 accept_historical_415:['claim_id','pr_number','head_sha','expected_state_sha','policy_attestation'],
 register_task:['issue_number','title','depends_on','allowed_paths']
}
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const plain=x=>x!==null&&typeof x==='object'&&!Array.isArray(x)
const line=(v,max)=>typeof v==='string'&&v.length>0&&v.length<=max&&
 !/[\u0000-\u001f\u007f]/.test(v)
const exact=(x,allowed)=>Object.keys(x).every(k=>allowed.has(k))
function checkpoint(x){
 check(plain(x)&&exact(x,CP_FIELDS),'INGRESS_CHECKPOINT_FIELDS')
 check(line(x.summary,400)&&x.summary.trim().length>=4,'INGRESS_CHECKPOINT_SUMMARY')
 check(line(x.next_step,400)&&x.next_step.trim().length>=4,'INGRESS_CHECKPOINT_NEXT')
 check(typeof x.branch==='string' && /^[a-zA-Z0-9][a-zA-Z0-9_.\/-]{0,119}$/.test(x.branch) &&
 !x.branch.includes('..')&&!x.branch.includes('//')&&!x.branch.endsWith('.lock') &&
 !x.branch.endsWith('/')&&!x.branch.endsWith('.'),'INGRESS_CHECKPOINT_BRANCH')
 check(SHA.test(x.head_sha),'INGRESS_CHECKPOINT_SHA')
 check(x.tests===undefined||line(x.tests,300),'INGRESS_CHECKPOINT_TESTS')
 check(x.blockers===undefined||line(x.blockers,300),'INGRESS_CHECKPOINT_BLOCKERS')
 check(x.pr_number===undefined||(Number.isInteger(x.pr_number)&&x.pr_number>0),'INGRESS_CHECKPOINT_PR')
}
function payload(body){
 check(typeof body==='string'&&body.length>0&&body.length<=4096,'INGRESS_BODY_SIZE')
 let data
 try{data=JSON.parse(body)}catch{throw new CollabError('INGRESS_BODY_NOT_JSON')}
 check(plain(data)&&exact(data,FIELDS),'INGRESS_BODY_FIELDS')
 if(data.action==='probe'){
   const allowed=new Set(['schema_version','action','request_id','requirement_id'])
   check(data.schema_version===1&&UUID.test(data.request_id)&&
     data.requirement_id==='REQ-20261031-001'&&
     exact(data,allowed)&&Object.keys(data).length===4,
     'INGRESS_UNAPPROVED_PROBE')
   return data
 }
 if(data.action==='migrate_v1'){
   const approved=new Set(['schema_version','action','request_id','requirement_id',
     'expected_state_sha','expected_proposal_sha'])
   check(data.schema_version===1 && UUID.test(data.request_id) &&
     data.requirement_id==='REQ-20261031-001' &&
     exact(data,approved) && Object.keys(data).length===6 &&
     data.expected_state_sha==='062036f7021e215ffbfdcbf5689d207a0549b68b' &&
     data.expected_proposal_sha==='bf80d5c384d5f687cb980b6e04127fc42167d7a8',
     'INGRESS_UNAPPROVED_MIGRATION')
   return data
 }
 check(data.schema_version===1 && ACTIONS.has(data.action) &&
 UUID.test(data.request_id) && REQ.test(data.requirement_id) &&
 TASK.test(data.task_id) && WORKER.test(data.worker_id),'INGRESS_REQUIRED')
 check(Number.isSafeInteger(data.expected_version)&&data.expected_version>=0,
   'INGRESS_EXPECTED_VERSION')
 const allowed=new Set([...BASE_FIELDS,...ACTION_FIELDS[data.action]])
 check(exact(data,allowed),'INGRESS_ACTION_FIELDS')
 check(data.claim_id===undefined||UUID.test(data.claim_id),'INGRESS_CLAIM')
 check(data.expected_claim_id===undefined||UUID.test(data.expected_claim_id),'INGRESS_OLD_CLAIM')
 check(data.new_worker_id===undefined||WORKER.test(data.new_worker_id),'INGRESS_NEW_WORKER')
 check(data.note===undefined||line(data.note,500),'INGRESS_NOTE')
 check(data.pr_number===undefined||(Number.isSafeInteger(data.pr_number)&&data.pr_number>0),'INGRESS_PR')
 check(data.head_sha===undefined||SHA.test(data.head_sha),'INGRESS_SHA')
 check(data.expected_head_sha===undefined||SHA.test(data.expected_head_sha),'INGRESS_EXPECTED_SHA')
 if(data.checkpoint!==undefined)checkpoint(data.checkpoint)
 if(['claim','register_task'].includes(data.action))check(data.claim_id===undefined,'INGRESS_CLAIM_NOT_ALLOWED')
 else if(data.action!=='takeover')
   check(UUID.test(data.claim_id),'INGRESS_CLAIM_REQUIRED')
 if(['checkpoint'].includes(data.action))check(data.checkpoint!==undefined,'INGRESS_CHECKPOINT_REQUIRED')
 if(['handoff','takeover'].includes(data.action)){
   check(WORKER.test(data.new_worker_id) && data.new_worker_id!==data.worker_id &&
     SHA.test(data.expected_head_sha) && line(data.note,300),'INGRESS_RECOVERY_FIELDS')
   if(data.action==='takeover')check(
     UUID.test(data.expected_claim_id) &&
     (data.claim_id===undefined||data.claim_id===data.expected_claim_id),
     'INGRESS_TAKEOVER_EXPECTED_CLAIM')
 }
 if(['progress','block','rework'].includes(data.action))check(line(data.note,500),'INGRESS_NOTE_REQUIRED')
 if(['submit','accept','capture_receipt','accept_receipt','accept_historical_415','accept_historical_446','accept_historical_271'].includes(data.action))check(data.pr_number>0&&SHA.test(data.head_sha),
   'INGRESS_SUBMIT_EVIDENCE')
 if(['accept_historical_446','accept_historical_271','capture_receipt','accept_receipt'].includes(data.action)||(data.action==='accept'&&(data.policy_attestation!==undefined||data.expected_state_sha!==undefined))){
   check(SHA.test(data.expected_state_sha||'')&&typeof data.policy_attestation==='string'&&
     line(data.policy_attestation,2048)&&data.policy_attestation.startsWith('PRP_RULESET_ATTESTATION_V1:'),
     'INGRESS_OWNER_POLICY_FIELDS')
   let note
   try{note=JSON.parse(data.policy_attestation.slice('PRP_RULESET_ATTESTATION_V1:'.length))}
   catch{throw new CollabError('INGRESS_OWNER_POLICY_FIELDS')}
   check(plain(note)&&note.expected_state_sha===data.expected_state_sha,'INGRESS_OWNER_POLICY_STATE')
 }
 if(data.action==='accept_historical_271')check(data.requirement_id==='REQ-20261031-001'&&['T-002','T-003'].includes(data.task_id)&&data.pr_number===271&&data.head_sha==='48b3a69232690e7e2fb54a2d92efac02cc512c0e'&&data.expected_version>=25,'INGRESS_HISTORICAL_271_PIN')
 if(data.action==='accept_historical_446')check(data.requirement_id==='REQ-20261031-001'&&data.task_id==='T-007'&&data.pr_number===446&&data.head_sha==='216b280386120f932eee28f22448d41bcaf82dec'&&data.worker_id==='chat_t007_security_20261125'&&data.expected_version>=20,'INGRESS_HISTORICAL_446_PIN')
 if(data.action==='accept_historical_415')check(data.requirement_id==='REQ-20261031-001'&&data.task_id==='T-001'&&data.pr_number===415&&data.head_sha==='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65'&&data.worker_id==='chat_t001_delivery_20261125'&&data.expected_version>=13&&SHA.test(data.expected_state_sha),'INGRESS_HISTORICAL_415_PIN')
 if(data.action==='register_task'){
   check(Number.isSafeInteger(data.issue_number)&&data.issue_number>0,'INGRESS_TASK_ISSUE')
   check(line(data.title,200)&&data.title.trim().length>=4,'INGRESS_TASK_TITLE')
   check(Array.isArray(data.depends_on)&&data.depends_on.length<=99&&
     data.depends_on.every(x=>TASK.test(x))&&
     new Set(data.depends_on).size===data.depends_on.length,'INGRESS_TASK_DEPENDENCIES')
   check(validateTaskScopeList(data.allowed_paths),'INGRESS_TASK_SCOPE')
 }
 return data
}

/** Trust ONLY the GitHub-owned event envelope (not free-form Issue body fields). */
export function validateIssueEvent(env,event,currentIssue=null,now=Date.now()){
 check(env.GITHUB_ACTIONS==='true'&&env.GITHUB_EVENT_NAME==='issues'&&
 env.GITHUB_EVENT_ACTION==='opened'&&env.GITHUB_REF==='refs/heads/main'&&
 env.GITHUB_REPOSITORY===REPO&&env.GITHUB_REPOSITORY_OWNER==='micor-cjj-spec'&&
 env.GITHUB_ACTOR==='micor-cjj-spec'&&env.GITHUB_WORKFLOW_REF===WORKFLOW&&
 SHA.test(env.GITHUB_SHA||''),'INGRESS_UNTRUSTED_RUN')
 check(plain(event)&&event.action==='opened'&&event.repository?.full_name===REPO&&
 event.repository?.default_branch==='main'&&
 event.repository?.owner?.login==='micor-cjj-spec'&&
 Number.isSafeInteger(event.repository?.owner?.id)&&
 event.repository.owner.id===OWNER_ID&&
 event.repository.owner.id===event.sender?.id&&
 event.sender?.login==='micor-cjj-spec'&&event.sender?.type==='User'&&
 Number.isSafeInteger(event.sender?.id)&&event.sender.id>0 &&
 event.issue?.user?.login===event.sender.login&&
 event.issue?.user?.id===event.sender.id&&
 event.issue?.author_association==='OWNER' &&
 event.issue?.state==='open'&&!event.issue?.pull_request &&
 Number.isSafeInteger(event.issue?.number)&&event.issue.number>0 &&
 event.issue?.title==='[PRP-COLLAB-REQUEST]','INGRESS_UNTRUSTED_ISSUE')
 if(currentIssue){
   check(currentIssue.number===event.issue.number &&
     currentIssue.user?.id===event.sender.id &&
     currentIssue.user?.login===event.sender.login &&
     currentIssue.author_association==='OWNER' &&
     currentIssue.title===event.issue.title &&
     currentIssue.body===event.issue.body &&
     currentIssue.state==='open' && !currentIssue.pull_request,'INGRESS_ISSUE_MODIFIED')
 }
 const data=payload(event.issue.body)
 if(data.action==='probe')return {
   command:{type:'probe',request_id:data.request_id,
     requirement_id:data.requirement_id},
   expected_version:0,source_issue:event.issue.number,
   actor:event.sender.login,actorId:event.sender.id,
   recoveryAuthorized:false,oneShotProbe:true
 }
 if(data.action==='migrate_v1')return {
   command:{type:data.action,request_id:data.request_id,
     requirement_id:data.requirement_id,
     expected_state_sha:data.expected_state_sha,
     expected_proposal_sha:data.expected_proposal_sha},
   expected_version:0,source_issue:event.issue.number,
   actor:event.sender.login,actorId:event.sender.id,recoveryAuthorized:false,oneShotMigration:true
 }
 // Only the event-authorized GitHub actor becomes the state-transaction actor.
 const historical=data.action==='accept_historical_415'
 const historical446=data.action==='accept_historical_446',historical271=data.action==='accept_historical_271'
 const captureReceipt=data.action==='capture_receipt',receiptAccept=data.action==='accept_receipt'
 const ownerPolicy=(data.action==='accept'||historical446||historical271||captureReceipt||receiptAccept)&&data.policy_attestation!==undefined
 const command={type:(historical||historical446||historical271||receiptAccept)?'accept':data.action,requirement_id:data.requirement_id,
   task_id:data.task_id,request_id:data.request_id,worker_id:data.worker_id}
 for(const key of ['claim_id','note','pr_number','head_sha','checkpoint',
   'new_worker_id','expected_claim_id','expected_head_sha','issue_number',
   'title','depends_on','allowed_paths'])
   if(data[key]!==undefined)command[key]=data[key]
 if(historical){
   check(currentIssue&&currentIssue.created_at===event.issue.created_at,'INGRESS_HISTORICAL_ISSUE_TIME')
   validateOwnerAttestation(data.policy_attestation,{requestId:data.request_id,mainSha:env.GITHUB_SHA,issueCreatedAt:event.issue.created_at,now})
   command.note=historicalNote(data.policy_attestation)
 }
 if(ownerPolicy){
   check(currentIssue&&currentIssue.created_at===event.issue.created_at&&
     typeof event.issue.created_at==='string'&&Number.isFinite(Date.parse(event.issue.created_at)),
     'INGRESS_OWNER_POLICY_ISSUE_TIME')
   // Exact canonical note is included in the existing command fingerprint.
   // All binding, freshness, live policy and CI checks occur in trusted review.
   command.note=(historical446?'PRP_HISTORICAL_446_V1:':historical271?'PRP_HISTORICAL_271_V1:':receiptAccept?'PRP_PREMERGE_RECEIPT_V1:':'')+data.policy_attestation
 }
 if(['handoff','takeover'].includes(data.action))
   command.expected_version=data.expected_version
 if(data.action==='takeover'&&command.claim_id===undefined)
   command.claim_id=data.expected_claim_id
 return {command,expected_version:data.expected_version,
   source_issue:event.issue.number,actor:event.sender.login,actorId:event.sender.id,
   recoveryAuthorized:data.action==='takeover',
   ...(historical?{historical415:true,expectedStateSha:data.expected_state_sha,policyAttestation:data.policy_attestation,issueCreatedAt:event.issue.created_at}:{}),
   ...(ownerPolicy?{ownerPolicy:true,...(historical446?{historical446:true}:{}),...(historical271?{historical271:true}:{}),...(captureReceipt?{captureReceipt:true}:{}),...(receiptAccept?{receiptAccept:true}:{}),expectedStateSha:data.expected_state_sha,issueCreatedAt:event.issue.created_at}:{})}
}
if(process.argv[1] && fileURLToPath(import.meta.url)===resolve(process.argv[1])){
 try{
  if(process.argv.length!==4)throw new CollabError('INGRESS_ARGS')
  const env=process.env
  const event=JSON.parse(readFileSync(process.argv[2],'utf8'))
  // Current API metadata must be checked by the caller before this point.
  const current=JSON.parse(readFileSync(process.argv[3],'utf8'))
  const validated=validateIssueEvent(env,event,current)
  writeFileSync(env.RUNNER_TEMP+'/prp-collab-validated-request.json',
    JSON.stringify(validated)+'\n',{mode:0o600,flag:'wx'})
  console.log('PRP_COLLAB_ISSUE_REQUEST_VALIDATED='+validated.source_issue)
 }catch(e){
  console.error('PRP_COLLAB_ISSUE_REJECTED='+(e?.code||'INVALID_REQUEST'))
  process.exitCode=1
 }
}
