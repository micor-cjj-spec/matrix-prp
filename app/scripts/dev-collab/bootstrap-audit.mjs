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
    matches_integration_pr_shape: canAcceptAsTaskPr && unassigned.length === 0 &&
      overlaps.length === 0 && pr.merged === true,
    task_acceptance_verified: false, // This read-only path never fetches CI/merge/owner proof.
    warnings: [
      ...(canAcceptAsTaskPr ? [] : ['BOOTSTRAP_PR_NOT_TARGETING_INTEGRATION']),
      ...(unassigned.length ? ['UNASSIGNED_CHANGED_FILES'] : []),
      ...(overlaps.length ? ['OVERLAPPING_TASK_PATHS'] : []),
      ...(snapshot.tasks.some(t => t.status !== 'DONE') ? ['TASKS_NOT_ACCEPTED'] : [])
    ]
  }
}


/** REQ-20261031-001 V0->V1 proposal ONLY. Does not commit, mutate or authorize a branch. */
export const SCOPE_MIGRATION_FILES = Object.freeze({
  "T-006": [
    ".github/workflows/prp-collab-board.yml",
    ".github/workflows/prp-collab-issue-projection.yml",
    "app/scripts/dev-collab/board-workflow.test.mjs",
    "app/scripts/dev-collab/board.mjs",
    "app/scripts/dev-collab/board.test.mjs",
    "app/scripts/dev-collab/projection-cli.mjs",
    "app/scripts/dev-collab/projection-workflow.test.mjs",
    "app/scripts/dev-collab/projection.mjs",
    "app/scripts/dev-collab/projection.test.mjs"
  ],
  "T-007": [
    "app/scripts/dev-collab/activation-preflight.mjs",
    "app/scripts/dev-collab/activation-preflight.test.mjs",
    "app/scripts/dev-collab/bootstrap-audit.mjs",
    "app/scripts/dev-collab/bootstrap-audit.test.mjs",
    "app/scripts/dev-collab/review-context.mjs",
    "app/scripts/dev-collab/review-context.test.mjs",
    "app/scripts/dev-collab/review-gate.mjs",
    "app/scripts/dev-collab/review-gate.test.mjs",
    "app/scripts/dev-collab/review-provenance.mjs",
    "app/scripts/dev-collab/review-provenance.test.mjs",
    "app/scripts/dev-collab/state-rule-policy.mjs",
    "app/scripts/dev-collab/state-rule-policy.test.mjs"
  ],
  "T-008": [
    "app/scripts/dev-collab/git-cas.test.mjs",
    "app/scripts/dev-collab/git-transaction.test.mjs",
    "app/scripts/dev-collab/integration-ci-boundary.test.mjs",
    "app/scripts/dev-collab/workflow-boundary.test.mjs",
    "app/scripts/dev-collab/workflow-contract.test.mjs"
  ],
  "T-009": [
    "app/scripts/dev-collab/checkpoint-recovery.test.mjs",
    "app/scripts/dev-collab/recovery-auth.mjs",
    "app/scripts/dev-collab/recovery.mjs",
    "app/scripts/dev-collab/recovery.test.mjs"
  ]
})

function requireMigration(condition,code){
  if(!condition) throw new Error('SCOPE_MIGRATION_'+code)
}
const exactly = (actual,expected) => JSON.stringify(actual) === JSON.stringify(expected)

export function verifyScopeMigrationProposal(before, after) {
  validateSnapshot(before)
  validateSnapshot(after)
  requireMigration(before.requirement_id==='REQ-20261031-001' && before.version===0 &&
    before.status==='ACTIVE' && before.tasks.length===5,'BASE_NOT_V0')
  requireMigration(after.requirement_id===before.requirement_id &&
    after.issue_number===before.issue_number && after.title===before.title &&
    after.status===before.status && after.schema_version===before.schema_version &&
    after.version===before.version+1 && after.tasks.length===9,'UNEXPECTED_STATE_CHANGE')
  requireMigration(exactly(after.processed_requests,before.processed_requests) &&
    before.processed_requests.length===0,'LEDGER_MUST_STAY_EMPTY')
  requireMigration(Number.isFinite(Date.parse(after.updated_at)) &&
    Date.parse(after.updated_at)>Date.parse(before.updated_at),'INVALID_UPDATED_AT')
  for(let i=0;i<5;i++){
    const a=before.tasks[i],b=after.tasks[i]
    requireMigration(a.task_id==='T-'+String(i+1).padStart(3,'0') &&
      a.status==='READY' && a.claim===null &&
      b.task_id===a.task_id && b.status===a.status && b.claim===a.claim &&
      b.issue_number===a.issue_number && b.title===a.title,'HISTORIC_TASK_MODIFIED')
    if(i!==4)requireMigration(exactly(b,a),'HISTORIC_TASK_MODIFIED')
    else {
      requireMigration(exactly(a.allowed_paths,[]) &&
        exactly(a.depends_on,['T-001','T-002','T-003','T-004']) &&
        exactly(b.allowed_paths,['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']) &&
        exactly(b.depends_on,['T-001','T-002','T-003','T-004','T-006','T-007','T-008','T-009']),
        'T005_SCOPE_OR_DEPENDENCIES')
    }
  }
  const expectedIssues={'T-006':141,'T-007':142,'T-008':143,'T-009':146}
  const expectedDeps={'T-006':['T-003'],'T-007':['T-003'],'T-008':['T-003','T-007','T-009'],
    'T-009':['T-003','T-007']}
  for(let i=5;i<9;i++){
    const task=after.tasks[i],id='T-'+String(i+1).padStart(3,'0')
    requireMigration(task.task_id===id && task.issue_number===expectedIssues[id] &&
      task.status==='READY' && task.claim===null &&
      exactly(task.allowed_paths,SCOPE_MIGRATION_FILES[id]) &&
      exactly(task.depends_on,expectedDeps[id]),'UNAUTHORIZED_NEW_TASK_SCOPE')
  }
  const within=(a,b)=>a===b||(a.endsWith('/')&&b.startsWith(a))||(b.endsWith('/')&&a.startsWith(b))
  for(let i=0;i<after.tasks.length;i++){
    for(let j=i+1;j<after.tasks.length;j++){
      const left=after.tasks[i],right=after.tasks[j]
      for(const a of left.allowed_paths)for(const b of right.allowed_paths){
        if(within(a,b))requireMigration(left.task_id==='T-004' &&
          right.task_id==='T-005' && right.depends_on.includes(left.task_id),
          'OVERLAPPING_TASK_WRITE_SCOPES')
      }
    }
  }
  const forbidden=['.github/workflows/ci.yml','.github/workflows/feature-impact.yml',
    '.github/workflows/prp-dev-collab-contract.yml']
  requireMigration(!after.tasks.some(t=>t.allowed_paths.some(a=>
    forbidden.some(f=>a===f||(a.endsWith('/')&&f.startsWith(a))))),
    'CI_GOVERNANCE_SCOPE_IN_TASK')
  return Object.freeze({structurally_valid:true,proposed_version:after.version,
    new_task_ids:['T-006','T-007','T-008','T-009'],authoritative_state_unchanged:true,
    ready_for_direct_merge:false})
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
