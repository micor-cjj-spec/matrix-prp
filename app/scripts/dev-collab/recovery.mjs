import { readFileSync, readdirSync, lstatSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { validateSnapshot, availableTasks } from './core.mjs'

const INCOMPLETE=new Set(['READY','CLAIMED','IN_PROGRESS','PAUSED','BLOCKED','IN_REVIEW'])
const ID=/^REQ-[0-9]{8}-[0-9]{3}$/
const TASK=/^T-[0-9]{3}$/

export function listUnfinishedRequirements(snapshots) {
  if(!Array.isArray(snapshots) || snapshots.length>1000)throw new Error('INVALID_REQUIREMENT_INDEX')
  const seen=new Set()
  const result=[]
  for(const source of snapshots) {
    const s=validateSnapshot(source)
    if(seen.has(s.requirement_id))throw new Error('DUPLICATE_REQUIREMENT')
    seen.add(s.requirement_id)
    const ready=new Set(availableTasks(s).map(t=>t.task_id))
    const tasks=s.tasks.filter(t=>INCOMPLETE.has(t.status)).map(t=>({
      task_id:t.task_id, issue_number:t.issue_number, title:t.title,
      status:t.status==='READY'&&!ready.has(t.task_id)?'WAITING':t.status,
      worker_id:t.claim?.worker_id??null,
      checkpoint_at:t.checkpoint?.recorded_at??null, checkpoint_head_sha:t.checkpoint?.head_sha??null,
      pr_number:t.pr_number??t.checkpoint?.pr_number??null
    }))
    if(s.status!=='CLOSED' && tasks.length)result.push({
      requirement_id:s.requirement_id,issue_number:s.issue_number,title:s.title,
      status:s.status,version:s.version,updated_at:s.updated_at??null,tasks
    })
  }
  return result.sort((a,b)=>a.requirement_id.localeCompare(b.requirement_id))
}

export function recoveryBrief(snapshot,taskId) {
  const s=validateSnapshot(snapshot)
  if(!TASK.test(taskId))throw new Error('INVALID_TASK_ID')
  const t=s.tasks.find(x=>x.task_id===taskId)
  if(!t)throw new Error('UNKNOWN_TASK')
  const cp=t.checkpoint
  return {
    requirement_id:s.requirement_id,requirement_issue:s.issue_number,
    state_version:s.version,task_id:t.task_id,task_issue:t.issue_number,
    title:t.title,status:t.status,worker_id:t.claim?.worker_id??null,
    dependencies:[...t.depends_on],allowed_paths:[...t.allowed_paths],
    task_pr:t.pr_number??null,task_head_sha:t.head_sha??null,
    checkpoint:cp?{
      summary:cp.summary,next_step:cp.next_step,blockers:cp.blockers??null,
      tests:cp.tests??null,branch:cp.branch,head_sha:cp.head_sha,
      pr_number:cp.pr_number??null,recorded_at:cp.recorded_at,
      source_worker:cp.worker_id,
      checkpoint_origin:cp.origin??'legacy_unspecified',
      git_sha_verified:false,
      stale_vs_state_head:Boolean(t.head_sha&&t.head_sha!==cp.head_sha)
    }:null,
    handoff_count:t.handoff_history?.length??0,
    last_handoff:t.handoff_history?.length?{
      type:t.handoff_history.at(-1).type,
      at:t.handoff_history.at(-1).at,
      from_worker:t.handoff_history.at(-1).from_worker,
      to_worker:t.handoff_history.at(-1).to_worker
    }:null,
    requires_owner_approval_for_forced_takeover:true,
    takeover_authorization:'explicit_owner_authored_issue',
    requires_github_gui_approval_for_forced_takeover:false,
    can_recover_uncommitted_chat_work:false,
    warning:cp?'Verify the linked branch/SHA and CI on GitHub before continuing.':
      'No durable checkpoint; reconstruct only from existing GitHub commits, Issues and PRs.'
  }
}

export function loadRequirementDirectory(directory) {
  const names=readdirSync(directory).filter(n=>ID.test(n.replace(/\.json$/,''))&&n.endsWith('.json')).sort()
  if(names.length>1000)throw new Error('TOO_MANY_REQUIREMENTS')
  return names.map(name=>{
    const path=join(directory,name)
    if(!lstatSync(path).isFile())throw new Error('INVALID_REQUIREMENT_FILE')
    const value=JSON.parse(readFileSync(path,'utf8'))
    if(name!==value.requirement_id+'.json')throw new Error('REQUIREMENT_FILENAME_MISMATCH')
    return value
  })
}

if(process.argv[1] && fileURLToPath(import.meta.url)===resolve(process.argv[1])){
  try{
    if(process.argv.length!==3 && process.argv.length!==5)throw new Error('USAGE_DIRECTORY_OR_DIRECTORY_REQ_TASK')
    const entries=loadRequirementDirectory(process.argv[2])
    let result
    if(process.argv.length===3)result=listUnfinishedRequirements(entries)
    else{
      const req=process.argv[3]
      const s=entries.find(x=>x.requirement_id===req)
      if(!s)throw new Error('UNKNOWN_REQUIREMENT')
      result=recoveryBrief(s,process.argv[4])
    }
    process.stdout.write(JSON.stringify(result,null,2)+'\n')
  }catch(e){
    console.error('PRP_RECOVERY_READ_ERROR='+(e?.code??e?.message??'INVALID_DATA'))
    process.exitCode=1
  }
}
