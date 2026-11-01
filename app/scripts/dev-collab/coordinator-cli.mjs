#!/usr/bin/env node
import { readFileSync, writeFileSync, renameSync } from 'node:fs'
import { dirname, basename, join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { applyCommand, CollabError } from './core.mjs'
import { trustedReviewContext, ghApi } from './review-context.mjs'
import { trustedRecoveryContext, verifyRecoveryGitBranch } from './recovery-auth.mjs'

const ALLOWED = new Set(['claim', 'start', 'progress', 'pause', 'block', 'resume', 'release', 'submit', 'rework', 'accept', 'close', 'checkpoint', 'handoff', 'takeover'])

async function execute() {
  if (process.argv.length !== 4) throw new CollabError('CLI_ARGUMENTS')
  const [statePath, receiptPath] = process.argv.slice(2)
  const env = process.env
  if (!ALLOWED.has(env.COLLAB_ACTION)) throw new CollabError('ACTION_NOT_EXPOSED')
  if (!/^REQ-[0-9]{8}-[0-9]{3}$/.test(env.COLLAB_REQ_ID || '')) throw new CollabError('REQUIREMENT_ID')
  if (basename(statePath) !== env.COLLAB_REQ_ID + '.json' ||
      basename(dirname(statePath)) !== 'requirements') throw new CollabError('STATE_PATH')
  const command = {
    type: env.COLLAB_ACTION,
    requirement_id: env.COLLAB_REQ_ID,
    request_id: env.COLLAB_REQUEST_ID
  }
  if (env.COLLAB_TASK_ID) command.task_id = env.COLLAB_TASK_ID
  if (env.COLLAB_WORKER_ID) command.worker_id = env.COLLAB_WORKER_ID
  if (env.COLLAB_CLAIM_ID) command.claim_id = env.COLLAB_CLAIM_ID
  if (env.COLLAB_NOTE) command.note = env.COLLAB_NOTE
  if (env.COLLAB_PR_NUMBER) command.pr_number = Number(env.COLLAB_PR_NUMBER)
  if (env.COLLAB_HEAD_SHA) command.head_sha = env.COLLAB_HEAD_SHA
  const recovery = env.COLLAB_RECOVERY_PAYLOAD || ''
  if(['checkpoint','handoff','takeover'].includes(env.COLLAB_ACTION)){
    if(!recovery || recovery.length>2048)throw new CollabError('RECOVERY_PAYLOAD_REQUIRED')
    let value
    try{value=JSON.parse(recovery)}catch{throw new CollabError('INVALID_RECOVERY_JSON')}
    if(value===null || typeof value!=='object' || Array.isArray(value))
      throw new CollabError('INVALID_RECOVERY_PAYLOAD')
    if(env.COLLAB_ACTION==='checkpoint') command.checkpoint=value
    else{
      const allowed=env.COLLAB_ACTION==='handoff'
        ? ['new_worker_id','expected_version','expected_head_sha']
        : ['new_worker_id','expected_version','expected_claim_id','expected_head_sha','checkpoint']
      if(!Object.keys(value).every(k=>allowed.includes(k)))
        throw new CollabError('RECOVERY_PAYLOAD_FIELDS')
      Object.assign(command,value)
    }
  }else if(recovery){
    throw new CollabError('UNEXPECTED_RECOVERY_PAYLOAD')
  }
  const raw = JSON.parse(readFileSync(statePath, 'utf8'))
  // First permit authenticated receipt replay without trying to re-approve an already completed task.
  const isKnownReplay = raw.processed_requests?.some(x => x.request_id === command.request_id)
  const reviewContext = !isKnownReplay && (env.COLLAB_ACTION === 'accept' || env.COLLAB_ACTION === 'close')
    ? trustedReviewContext(raw, command, env, ghApi)
    : {}
  const recoveryContext = !isKnownReplay && env.COLLAB_ACTION==='takeover'
    ? trustedRecoveryContext(env)
    : {}
  const recoveryGitContext = env.COLLAB_ACTION==='takeover' && !isKnownReplay &&
    command.checkpoint !== undefined && recoveryContext.recoveryAuthorized===true
    ? verifyRecoveryGitBranch(command.checkpoint, env)
    : {}
  const { snapshot, receipt } = applyCommand(raw, command, {
    actor: env.GITHUB_ACTOR,
    now: new Date().toISOString(),
    ...reviewContext,
    ...recoveryContext,
    ...recoveryGitContext
  })
  const tmp = join(dirname(statePath), '.state-' + randomUUID() + '.tmp')
  writeFileSync(tmp, JSON.stringify(snapshot, null, 2) + '\n', { mode: 0o600, flag: 'wx' })
  renameSync(tmp, statePath)
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 })
}

execute().catch(error => {
  const code = error instanceof CollabError ? error.code : 'STATE_UPDATE_FAILED'
  console.error('PRP_COLLAB_ERROR=' + code)
  process.exitCode = 1
})
