import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { availableTasks, validateSnapshot } from './core.mjs'

const REQ = /^REQ-[0-9]{8}-[0-9]{3}$/
const escapeCell = value => String(value ?? '—')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/\|/g, '&#124;').replace(/[\r\n\t]/g, ' ')

export function renderBoard(snapshot, options = {}) {
  validateSnapshot(snapshot)
  const sha = options.state_sha
  if (sha !== undefined && !/^[a-f0-9]{40}$/.test(sha)) {
    throw new Error('INVALID_STATE_SHA')
  }
  const ready = new Set(availableTasks(snapshot).map(t => t.task_id))
  const completed = snapshot.tasks.filter(t => t.status === 'DONE').length
  const claimed = snapshot.tasks.filter(t => ['CLAIMED','IN_PROGRESS','PAUSED','BLOCKED','IN_REVIEW'].includes(t.status)).length
  const lines = [
    `## ${escapeCell(snapshot.requirement_id)} — ${escapeCell(snapshot.title)}`,
    '',
    `Requirement Issue: #${snapshot.issue_number} · Status: **${escapeCell(snapshot.status)}** · State version: **${snapshot.version}**`,
    `Completed: **${completed}/${snapshot.tasks.length}** · Claimed or in review: **${claimed}**`
  ]
  if (sha) lines.push(`State commit: \`${sha}\``)
  lines.push('', '| Task | GitHub Issue | Status | Dependencies | Assigned worker | PR |')
  lines.push('|---|---|---|---|---|---|')
  for (const task of snapshot.tasks) {
    const waiting = task.status === 'READY' && !ready.has(task.task_id)
    const status = waiting ? 'WAITING' : task.status
    lines.push(
      `| ${escapeCell(task.task_id)} · ${escapeCell(task.title)} | #${task.issue_number} | ${status} | ${escapeCell(task.depends_on.join(', ') || 'None')} | ${escapeCell(task.claim?.worker_id)} | ${task.pr_number ? '#'+task.pr_number : '—'} |`
    )
  }
  lines.push('', '_This board is a read-only projection of the Git state branch. Refresh for newer updates. It does not authorize deployment, merge or task acceptance._')
  return lines.join('\n') + '\n'
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  try {
    if (process.argv.length !== 3 || !REQ.test(String(process.argv[2]).split('/').pop().replace(/\.json$/, ''))) {
      throw new Error('EXPECTED_REQUIREMENT_JSON')
    }
    const snapshot = JSON.parse(readFileSync(process.argv[2], 'utf8'))
    process.stdout.write(renderBoard(snapshot, {
      ...(process.env.COLLAB_STATE_SHA ? { state_sha: process.env.COLLAB_STATE_SHA } : {})
    }))
  } catch (error) {
    console.error('PRP_BOARD_ERROR=' + (error?.code ?? error?.message ?? 'INVALID_DATA'))
    process.exitCode = 1
  }
}
