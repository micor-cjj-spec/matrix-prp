import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { availableTasks, validateSnapshot } from './core.mjs'

function inside(path, scope) {
  return path === scope || (scope.endsWith('/') && path.startsWith(scope))
}

/** Only reports facts from Git and the task snapshot. NEVER claims or changes state. */
export function auditBootstrap(snapshot, pr, files) {
  validateSnapshot(snapshot)
  if (!pr || !Number.isInteger(pr.number) || pr.number < 1 ||
      !Number.isInteger(pr.changed_files) || pr.changed_files < 0 ||
      pr.changed_files > 100 || !Array.isArray(files) ||
      files.length !== pr.changed_files ||
      !files.every(f => typeof f.filename === 'string' && f.filename.length > 0)) {
    throw new Error('INCOMPLETE_BOOTSTRAP_PR_FILES')
  }
  const fileNames = files.map(f => f.filename)
  if (new Set(fileNames).size !== fileNames.length) throw new Error('DUPLICATE_BOOTSTRAP_PR_FILE')
  const byTask = Object.fromEntries(snapshot.tasks.map(task => [
    task.task_id, fileNames.filter(f => task.allowed_paths.some(s => inside(f, s)))
  ]))
  const unassigned = fileNames.filter(name => snapshot.tasks.every(task =>
    !task.allowed_paths.some(scope => inside(name, scope))
  ))
  const overlaps = fileNames.filter(name => snapshot.tasks.filter(task =>
    task.allowed_paths.some(scope => inside(name, scope))
  ).length > 1)
  const canAcceptAsTaskPr = pr.base?.ref === 'integrate/' + snapshot.requirement_id
  return {
    requirement_id: snapshot.requirement_id,
    state_version: snapshot.version,
    state_status: snapshot.status,
    total_tasks: snapshot.tasks.length,
    task_statuses: Object.fromEntries(snapshot.tasks.map(t => [t.task_id, t.status])),
    claim_count: snapshot.tasks.filter(t => Boolean(t.claim)).length,
    ready_task_ids: availableTasks(snapshot).map(t => t.task_id),
    pr_number: pr.number,
    pr_base: pr.base?.ref ?? null,
    pr_draft: pr.draft === true,
    pr_merged: pr.merged === true,
    pr_changed_files: pr.changed_files,
    assigned_files_by_task: byTask,
    unassigned_files: unassigned,
    overlap_files: overlaps,
    eligible_for_task_acceptance: canAcceptAsTaskPr && unassigned.length === 0 &&
      overlaps.length === 0 && pr.merged === true,
    warnings: [
      ...(canAcceptAsTaskPr ? [] : ['BOOTSTRAP_PR_NOT_TARGETING_INTEGRATION']),
      ...(unassigned.length ? ['UNASSIGNED_CHANGED_FILES'] : []),
      ...(overlaps.length ? ['OVERLAPPING_TASK_PATHS'] : []),
      ...(snapshot.tasks.some(t => t.status !== 'DONE') ? ['TASKS_NOT_ACCEPTED'] : [])
    ]
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  try {
    if (process.argv.length !== 5) throw new Error('EXPECTED_STATE_PR_FILES_JSON')
    const [statePath, prPath, filesPath] = process.argv.slice(2)
    const read = p => JSON.parse(readFileSync(p, 'utf8'))
    process.stdout.write(JSON.stringify(auditBootstrap(read(statePath),read(prPath),read(filesPath)),null,2)+'\n')
  } catch (e) {
    console.error('BOOTSTRAP_AUDIT_ERROR=' + String(e?.message || 'FAILED'))
    process.exitCode = 1
  }
}
