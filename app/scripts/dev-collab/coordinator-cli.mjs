#!/usr/bin/env node
import { readFileSync, writeFileSync, renameSync } from 'node:fs'
import { dirname, basename, join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { applyCommand, CollabError } from './core.mjs'

const ALLOWED = new Set(['claim', 'start', 'progress', 'pause', 'block', 'resume', 'release', 'submit'])

function execute() {
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
    task_id: env.COLLAB_TASK_ID,
    request_id: env.COLLAB_REQUEST_ID
  }
  if (env.COLLAB_WORKER_ID) command.worker_id = env.COLLAB_WORKER_ID
  if (env.COLLAB_CLAIM_ID) command.claim_id = env.COLLAB_CLAIM_ID
  if (env.COLLAB_NOTE) command.note = env.COLLAB_NOTE
  if (env.COLLAB_PR_NUMBER) command.pr_number = Number(env.COLLAB_PR_NUMBER)
  if (env.COLLAB_HEAD_SHA) command.head_sha = env.COLLAB_HEAD_SHA
  const raw = JSON.parse(readFileSync(statePath, 'utf8'))
  const { snapshot, receipt } = applyCommand(raw, command, {
    actor: env.GITHUB_ACTOR,
    now: new Date().toISOString()
  })
  const tmp = join(dirname(statePath), '.state-' + randomUUID() + '.tmp')
  writeFileSync(tmp, JSON.stringify(snapshot, null, 2) + '\n', { mode: 0o600, flag: 'wx' })
  renameSync(tmp, statePath)
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 })
}

try {
  execute()
} catch (error) {
  const code = error instanceof CollabError ? error.code : 'STATE_UPDATE_FAILED'
  console.error('PRP_COLLAB_ERROR=' + code)
  process.exitCode = 1
}
