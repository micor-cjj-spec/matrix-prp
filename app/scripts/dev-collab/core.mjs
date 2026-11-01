import { createHash, randomUUID } from 'node:crypto'

export class CollabError extends Error {
  constructor(code, message = code) {
    super(message)
    this.name = 'CollabError'
    this.code = code
  }
}

const TASK_STATES = new Set(['READY', 'CLAIMED', 'IN_PROGRESS', 'PAUSED', 'BLOCKED', 'IN_REVIEW', 'DONE', 'CANCELED'])
const REQUIREMENT_STATES = new Set(['ACTIVE', 'ACCEPTANCE', 'CLOSED', 'CANCELED'])
const CLAIMED_STATES = new Set(['CLAIMED', 'IN_PROGRESS', 'PAUSED', 'BLOCKED', 'IN_REVIEW'])
const WORKING_STATES = new Set(['CLAIMED', 'IN_PROGRESS', 'PAUSED', 'BLOCKED'])
const HEX_SHA = /^[a-f0-9]{40}$/
const WORKER = /^[a-zA-Z0-9_-]{3,64}$/
const REQ = /^REQ-[0-9]{8}-[0-9]{3}$/
const TASK = /^T-[0-9]{3}$/
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function check(condition, code) {
  if (!condition) throw new CollabError(code)
}

function plain(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function safePath(path) {
  return typeof path === 'string' && path.length > 3 && path.length <= 200 &&
    /^[a-zA-Z0-9_.\/-]+$/.test(path) && !path.startsWith('/') &&
    !path.includes('//') && !path.split('/').includes('..') &&
    !path.split('/').includes('.') && !path.startsWith('.git/') &&
    path.includes('/')
}

function overlaps(a, b) {
  return a === b || (a.endsWith('/') && b.startsWith(a)) ||
    (b.endsWith('/') && a.startsWith(b))
}

export function scopesOverlap(a, b) {
  return a.some(left => b.some(right => overlaps(left, right)))
}


function singleLine(value,min,max){
  return typeof value === 'string' && value.length>=min && value.length<=max &&
    value.trim().length>0 && !/[\x00-\x1f\x7f]/.test(value)
}
function safeBranch(value){
  return typeof value==='string' && /^[a-zA-Z0-9][a-zA-Z0-9_.\/-]{0,119}$/.test(value) &&
    !value.includes('..') && !value.includes('//') &&
    !value.endsWith('/') && !value.endsWith('.') && !value.endsWith('.lock')
}
function verifyCheckpoint(cp){
  check(plain(cp) && Object.keys(cp).every(k=>
    ['summary','next_step','branch','head_sha','tests','blockers','pr_number','recorded_at','worker_id'].includes(k)),
    'CHECKPOINT_FIELDS')
  check(singleLine(cp.summary,4,400) && singleLine(cp.next_step,4,400),'CHECKPOINT_DESCRIPTION')
  check(safeBranch(cp.branch) && HEX_SHA.test(cp.head_sha),'CHECKPOINT_GIT_REFERENCE')
  check(cp.tests===undefined || singleLine(cp.tests,4,300),'CHECKPOINT_TESTS')
  check(cp.blockers===undefined || singleLine(cp.blockers,4,300),'CHECKPOINT_BLOCKERS')
  check(cp.pr_number===undefined || (Number.isInteger(cp.pr_number)&&cp.pr_number>0),'CHECKPOINT_PR_NUMBER')
  check(cp.recorded_at===undefined || (typeof cp.recorded_at==='string' &&
    Number.isFinite(Date.parse(cp.recorded_at))),'CHECKPOINT_TIME')
  check(cp.worker_id===undefined || WORKER.test(cp.worker_id),'CHECKPOINT_WORKER')
}

export function validateSnapshot(snapshot) {
  check(plain(snapshot), 'INVALID_SNAPSHOT')
  check(snapshot.schema_version === 1, 'SCHEMA_VERSION')
  check(REQ.test(snapshot.requirement_id), 'REQUIREMENT_ID')
  check(Number.isInteger(snapshot.version) && snapshot.version >= 0, 'VERSION')
  check(REQUIREMENT_STATES.has(snapshot.status), 'REQUIREMENT_STATUS')
  check(Number.isInteger(snapshot.issue_number) && snapshot.issue_number > 0, 'ISSUE_NUMBER')
  check(typeof snapshot.title === 'string' && snapshot.title.trim().length > 0 && snapshot.title.length <= 200, 'TITLE')
  check(Array.isArray(snapshot.tasks) && snapshot.tasks.length > 0 && snapshot.tasks.length <= 100, 'TASK_LIST')
  check(Array.isArray(snapshot.processed_requests) && snapshot.processed_requests.length <= 512, 'REQUEST_LEDGER')
  const ids = new Set()
  const receipts = new Set()
  for (const r of snapshot.processed_requests) {
    check(plain(r) && UUID.test(r.request_id) && typeof r.fingerprint === 'string' &&
      typeof r.actor === 'string' && /^[a-zA-Z0-9-]{1,39}$/.test(r.actor) &&
      /^[a-f0-9]{64}$/.test(r.fingerprint) && plain(r.receipt), 'REQUEST_RECORD')
    check(!receipts.has(r.request_id), 'DUPLICATE_REQUEST_ID')
    receipts.add(r.request_id)
  }
  for (const task of snapshot.tasks) {
    check(plain(task) && TASK.test(task.task_id) && !ids.has(task.task_id), 'TASK_ID')
    ids.add(task.task_id)
    check(Number.isInteger(task.issue_number) && task.issue_number > 0, 'TASK_ISSUE')
    check(typeof task.title === 'string' && task.title.length > 0 && task.title.length <= 200, 'TASK_TITLE')
    check(TASK_STATES.has(task.status), 'TASK_STATUS')
    check(Array.isArray(task.depends_on) && task.depends_on.every(id => TASK.test(id)), 'DEPENDENCIES')
    check(Array.isArray(task.allowed_paths) && task.allowed_paths.length <= 20 &&
      task.allowed_paths.every(safePath), 'ALLOWED_PATHS')
    if(task.checkpoint!==undefined){
      verifyCheckpoint(task.checkpoint)
      check(typeof task.checkpoint.recorded_at==='string' &&
        WORKER.test(task.checkpoint.worker_id),'CHECKPOINT_METADATA')
    }
    if(task.handoff_history!==undefined){
      check(Array.isArray(task.handoff_history) && task.handoff_history.length<=32,'HANDOFF_HISTORY')
      for(const h of task.handoff_history){
        check(plain(h) && ['handoff','takeover'].includes(h.type) &&
          WORKER.test(h.from_worker) && WORKER.test(h.to_worker) &&
          typeof h.actor==='string' && /^[a-zA-Z0-9-]{1,39}$/.test(h.actor) &&
          typeof h.at==='string' && Number.isFinite(Date.parse(h.at)) &&
          singleLine(h.reason,4,300) && HEX_SHA.test(h.head_sha) &&
          Number.isInteger(h.previous_generation) && h.previous_generation>=1 &&
          h.generation===h.previous_generation+1,'HANDOFF_RECORD')
      }
    }
    if (CLAIMED_STATES.has(task.status)) {
      check(plain(task.claim) && UUID.test(task.claim.claim_id) &&
        typeof task.claim.worker_id === 'string' && /^[a-zA-Z0-9_-]{3,64}$/.test(task.claim.worker_id) &&
        typeof task.claim.actor === 'string' && /^[a-zA-Z0-9-]{1,39}$/.test(task.claim.actor) &&
        (task.claim.generation === undefined || (Number.isInteger(task.claim.generation) && task.claim.generation>=1)), 'ACTIVE_CLAIM')
    } else check(task.claim === null, 'UNEXPECTED_CLAIM')
  }
  const graph = new Map(snapshot.tasks.map(t => [t.task_id, t.depends_on]))
  const visiting = new Set()
  const visited = new Set()
  function visit(id) {
    check(graph.has(id), 'UNKNOWN_DEPENDENCY')
    if (visited.has(id)) return
    check(!visiting.has(id), 'DEPENDENCY_CYCLE')
    visiting.add(id)
    for (const dep of graph.get(id)) {
      check(dep !== id, 'SELF_DEPENDENCY')
      visit(dep)
    }
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of ids) visit(id)
  if (snapshot.status === 'CLOSED') {
    check(snapshot.tasks.every(t => ['DONE', 'CANCELED'].includes(t.status)), 'INCOMPLETE_REQUIREMENT')
  }
  return snapshot
}

function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  if (plain(value)) return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}'
  return JSON.stringify(value)
}

function fingerprint(command) {
  return createHash('sha256').update(canonical(command)).digest('hex')
}

function owned(task, command, actor) {
  check(CLAIMED_STATES.has(task.status), 'NOT_CLAIMED')
  check(task.claim?.claim_id === command.claim_id &&
    task.claim?.worker_id === command.worker_id &&
    task.claim?.actor === actor, 'STALE_OR_FOREIGN_CLAIM')
}

export function availableTasks(snapshot) {
  validateSnapshot(snapshot)
  return snapshot.tasks.filter(t => t.status === 'READY' &&
    t.depends_on.every(id => snapshot.tasks.find(d => d.task_id === id).status === 'DONE') &&
    !snapshot.tasks.some(other => other.task_id !== t.task_id &&
      CLAIMED_STATES.has(other.status) && scopesOverlap(t.allowed_paths, other.allowed_paths)))
}

export function applyCommand(original, command, context) {
  validateSnapshot(original)
  check(plain(command) && plain(context), 'INVALID_COMMAND')
  check(REQ.test(command.requirement_id) && command.requirement_id === original.requirement_id, 'WRONG_REQUIREMENT')
  check(UUID.test(command.request_id), 'REQUEST_ID')
  check(typeof context.actor === 'string' && /^[a-zA-Z0-9-]{1,39}$/.test(context.actor), 'INVALID_ACTOR')
  check(typeof context.now === 'string' && !Number.isNaN(Date.parse(context.now)), 'INVALID_TIME')
  check(typeof command.type === 'string', 'COMMAND_TYPE')
  check(Object.keys(command).every(key => [
    'type', 'requirement_id', 'request_id', 'task_id', 'worker_id',
    'claim_id', 'note', 'pr_number', 'head_sha', 'checkpoint',
    'new_worker_id', 'expected_version', 'expected_claim_id', 'expected_head_sha'
  ].includes(key)), 'UNEXPECTED_COMMAND_FIELD')
  const hash = fingerprint(command)
  const previous = original.processed_requests.find(r => r.request_id === command.request_id)
  if (previous) {
    check(previous.actor === context.actor, 'REQUEST_ACTOR_MISMATCH')
    check(previous.fingerprint === hash, 'REQUEST_ID_COLLISION')
    return { snapshot: original, receipt: { ...previous.receipt, replayed: true } }
  }
  check(original.status === 'ACTIVE' || command.type === 'close', 'REQUIREMENT_NOT_ACTIVE')
  const next = structuredClone(original)
  const task = next.tasks.find(t => t.task_id === command.task_id)
  const type = command.type
  if (type !== 'close') {
    check(TASK.test(command.task_id) && task, 'UNKNOWN_TASK')
  }
  const requireOwner = () => {
    owned(task, command, context.actor)
  }
  let receipt = { type, task_id: command.task_id ?? null, request_id: command.request_id }
  switch (type) {
    case 'claim': {
      check(task.status === 'READY', 'TASK_NOT_READY')
      check(typeof command.worker_id === 'string' && /^[a-zA-Z0-9_-]{3,64}$/.test(command.worker_id), 'WORKER_ID')
      check(task.depends_on.every(id => next.tasks.find(d => d.task_id === id).status === 'DONE'), 'DEPENDENCY_BLOCKED')
      check(!next.tasks.some(other => other.task_id !== task.task_id &&
        CLAIMED_STATES.has(other.status) && scopesOverlap(task.allowed_paths, other.allowed_paths)), 'SCOPE_CONFLICT')
      task.claim = { claim_id: randomUUID(), worker_id: command.worker_id, actor: context.actor, claimed_at: context.now, generation: 1 }
      task.status = 'CLAIMED'
      receipt.claim_id = task.claim.claim_id
      break
    }
    case 'start':
      requireOwner()
      check(task.status === 'CLAIMED', 'INVALID_TRANSITION')
      task.status = 'IN_PROGRESS'
      break
    case 'progress':
      requireOwner()
      check(task.status === 'IN_PROGRESS', 'INVALID_TRANSITION')
      check(typeof command.note === 'string' && command.note.length >= 1 && command.note.length <= 500, 'PROGRESS_NOTE')
      if (command.head_sha !== undefined) check(HEX_SHA.test(command.head_sha), 'COMMIT_SHA')
      task.last_note = command.note
      if (command.head_sha) task.head_sha = command.head_sha
      break
    case 'pause':
      requireOwner()
      check(['CLAIMED', 'IN_PROGRESS', 'BLOCKED'].includes(task.status), 'INVALID_TRANSITION')
      task.status = 'PAUSED'
      break
    case 'block':
      requireOwner()
      check(['CLAIMED', 'IN_PROGRESS'].includes(task.status), 'INVALID_TRANSITION')
      check(typeof command.note === 'string' && command.note.length >= 1 && command.note.length <= 500, 'BLOCK_REASON')
      task.last_note = command.note
      task.status = 'BLOCKED'
      break
    case 'resume':
      requireOwner()
      check(['PAUSED', 'BLOCKED'].includes(task.status), 'INVALID_TRANSITION')
      task.status = 'IN_PROGRESS'
      break
    case 'checkpoint': {
      requireOwner()
      check(plain(command.checkpoint),'CHECKPOINT_REQUIRED')
      check(!Object.keys(command.checkpoint).some(k=>['recorded_at','worker_id'].includes(k)),
        'CHECKPOINT_METADATA_RESERVED')
      verifyCheckpoint(command.checkpoint)
      check(task.head_sha===undefined || task.head_sha===command.checkpoint.head_sha,
        'CHECKPOINT_STALE_HEAD')
      check(task.pr_number===undefined || task.pr_number===command.checkpoint.pr_number,
        'CHECKPOINT_STALE_PR')
      task.checkpoint={...command.checkpoint,recorded_at:context.now,
        worker_id:task.claim.worker_id}
      receipt.checkpoint_head_sha=task.checkpoint.head_sha
      break
    }
    case 'handoff':
    case 'takeover': {
      check(CLAIMED_STATES.has(task.status),'NOT_CLAIMED')
      check(task.checkpoint!==undefined,'RECOVERY_CHECKPOINT_REQUIRED')
      check(Number.isInteger(command.expected_version) &&
        command.expected_version===original.version,'STALE_RECOVERY_VERSION')
      check(task.checkpoint.worker_id===task.claim.worker_id,'RECOVERY_CHECKPOINT_OWNER_MISMATCH')
      check(WORKER.test(command.new_worker_id) &&
        command.new_worker_id!==task.claim.worker_id,'RECOVERY_TARGET_WORKER')
      check(singleLine(command.note,4,300),'RECOVERY_REASON')
      check(HEX_SHA.test(command.expected_head_sha) &&
        command.expected_head_sha===task.checkpoint.head_sha &&
        (task.head_sha===undefined || task.head_sha===command.expected_head_sha),
        'STALE_RECOVERY_HEAD')
      if(type==='handoff'){
        requireOwner()
      }else{
        check(context.recoveryAuthorized===true,'RECOVERY_OWNER_APPROVAL_REQUIRED')
        check(UUID.test(command.expected_claim_id) &&
          command.expected_claim_id===task.claim.claim_id &&
          command.worker_id===task.claim.worker_id,'STALE_RECOVERY_CLAIM')
      }
      const old=task.claim
      const generation=(old.generation??1)+1
      const history=task.handoff_history??[]
      check(history.length<32,'HANDOFF_HISTORY_FULL')
      history.push({type,from_worker:old.worker_id,to_worker:command.new_worker_id,
        actor:context.actor,at:context.now,reason:command.note,
        head_sha:task.checkpoint.head_sha,previous_generation:old.generation??1,generation})
      task.handoff_history=history
      task.claim={claim_id:randomUUID(),worker_id:command.new_worker_id,
        actor:context.actor,claimed_at:context.now,generation}
      receipt.claim_id=task.claim.claim_id
      receipt.generation=generation
      receipt.previous_worker_id=old.worker_id
      receipt.new_worker_id=task.claim.worker_id
      break
    }
    case 'release':
      requireOwner()
      check(WORKING_STATES.has(task.status), 'INVALID_TRANSITION')
      task.claim = null
      task.status = 'READY'
      break
    case 'submit':
      requireOwner()
      check(task.status === 'IN_PROGRESS', 'INVALID_TRANSITION')
      check(Number.isInteger(command.pr_number) && command.pr_number > 0, 'PR_NUMBER')
      check(HEX_SHA.test(command.head_sha), 'COMMIT_SHA')
      task.pr_number = command.pr_number
      task.head_sha = command.head_sha
      task.status = 'IN_REVIEW'
      break
    case 'rework':
      requireOwner()
      check(task.status === 'IN_REVIEW', 'INVALID_TRANSITION')
      check(typeof command.note === 'string' && command.note.length >= 1 && command.note.length <= 500, 'REWORK_REASON')
      task.last_note = command.note
      task.status = 'IN_PROGRESS'
      break
    case 'accept':
      check(task.status === 'IN_REVIEW', 'INVALID_TRANSITION')
      check(context.reviewerAuthorized === true && context.ciVerified === true &&
        context.mergedIntoIntegration === true && command.pr_number === task.pr_number &&
        command.head_sha === task.head_sha, 'REVIEW_EVIDENCE_REQUIRED')
      task.claim = null
      task.status = 'DONE'
      break
    case 'close':
      check(context.reviewerAuthorized === true && context.acceptanceApproved === true &&
        context.integrationReviewVerified === true && Number.isInteger(command.pr_number) &&
        HEX_SHA.test(command.head_sha), 'REQUIREMENT_APPROVAL_REQUIRED')
      check(next.tasks.every(t => ['DONE', 'CANCELED'].includes(t.status)), 'INCOMPLETE_REQUIREMENT')
      next.status = 'CLOSED'
      break
    default:
      throw new CollabError('UNKNOWN_COMMAND')
  }
  next.version += 1
  next.updated_at = context.now
  receipt = { ...receipt, version: next.version, status: task?.status ?? next.status, replayed: false }
  // Never evict deduplication receipts silently: an old request could otherwise be replayed.
  check(next.processed_requests.length < 512, 'REQUEST_LEDGER_FULL')
  next.processed_requests.push({ request_id: command.request_id, fingerprint: hash, actor: context.actor, receipt })
  validateSnapshot(next)
  return { snapshot: next, receipt }
}
