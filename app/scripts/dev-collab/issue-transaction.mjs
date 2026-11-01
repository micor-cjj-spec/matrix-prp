import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs'
import {join} from 'node:path'
import {tmpdir} from 'node:os'
import {execFileSync} from 'node:child_process'
import {fileURLToPath} from 'node:url'
import {resolve} from 'node:path'
import {validateIssueEvent} from './issue-ingress.mjs'
import {applyCommand,validateSnapshot,CollabError} from './core.mjs'
import {verifyStateBranchRuleset} from './state-rule-policy.mjs'
import {applyOwnerIssuedMigration} from './issue-migrate.mjs'

const REPO='micor-cjj-spec/matrix-prp',SHA=/^[a-f0-9]{40}$/
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const run=(program,args,options={})=>execFileSync(program,args,{
 encoding:'utf8',timeout:15000,maxBuffer:4*1024*1024,...options}).trim()
const gh=(endpoint)=>JSON.parse(run('gh',['api',endpoint]))
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
 const markers=[...issue.body.matchAll(/<!-- PRP_TASK_MANIFEST\\n([\\s\\S]*?)\\n-->/g)]
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

export function applyAuthenticatedIssue(snapshot,validated,now,verifyRemote=()=>false){
 validateSnapshot(snapshot)
 const {command,expected_version,actor}=validated
 const replay=snapshot.processed_requests.some(r=>r.request_id===command.request_id)
 check(replay||snapshot.version===expected_version,'ISSUE_STALE_VERSION')
 check(actor==='micor-cjj-spec','ISSUE_UNTRUSTED_ACTOR')
 const context={actor,now,recoveryAuthorized:validated.recoveryAuthorized===true}
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
 const ruleset=gh('repos/'+REPO+'/rulesets/'+env.COLLAB_RULESET_ID)
 verifyStateBranchRuleset(ruleset,Number(env.COLLAB_APP_ID))
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
  state_sha:meta.state_sha}
}
function receiptMarkdown(info){
 return ['### PRP collaboration request completed','',
  'Request ID: '+info.request_id,
  'Operation: '+info.action,
  'Task: '+info.requirement_id+'/'+info.task_id,
  'State version: '+info.version,'Remote state SHA: '+info.state_sha,
  '','Result was committed using a non-force Git push.',
  'Public receipt excludes claim credentials.'].join('\n')+'\n'
}
async function main(){
 const env=process.env
 const event=JSON.parse(readFileSync(env.GITHUB_EVENT_PATH,'utf8'))
 const issue=gh('repos/'+REPO+'/issues/'+event.issue?.number)
 const validated=validateIssueEvent(env,event,issue)
 if(validated.command.type==='register_task'){
   const taskIssue=gh('repos/'+REPO+'/issues/'+validated.command.issue_number)
   verifyTaskIssue(taskIssue,validated)
   validated.taskIssueVerified=true
 }
 verifyBranchAndRunner(env)
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
 const {snapshot,receipt}=applyAuthenticatedIssue(before,validated,
   new Date().toISOString(),verifiedGitCheckpoint)
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
   check(git('ls-remote','--exit-code','--refs','origin',stateRef)===base,
     'ISSUE_RACE_BEFORE_PUSH')
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
   process.exitCode=1
 })
}
