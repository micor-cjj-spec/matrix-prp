import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const oldRoot = join(root, 'app/docker/mysql/init')
const newRoot = join(root, 'app/backend/src/main/resources/db/migration')

// Existing deployed batches. Treat V1-V7 as immutable after this release.
export const mapping = [
  ['001-schema.sql', 'V1__core.sql'],
  ['002-auth.sql', 'V2__auth.sql'],
  ['003-video-library.sql', 'V3__video_library.sql'],
  ['004-notification-center.sql', 'V4__notification_center.sql'],
  ['005-practice-center.sql', 'V5__practice_center.sql'],
  ['006-practice-ai.sql', 'V6__practice_ai.sql'],
  ['007-wellness-center.sql', 'V7__wellness_center.sql'],
]

export function legacyTables() {
  const names = mapping.flatMap(([legacy]) => {
    const sql = readFileSync(join(oldRoot, legacy), 'utf8')
    return [...sql.matchAll(/CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-z][a-z0-9_]*)/gi)]
      .map(match => match[1])
  })
  assert.equal(new Set(names).size, names.length, 'duplicate table name in historical migration scripts')
  return names
}

export function validateMirror() {
  for (const [legacy, versioned] of mapping) {
    assert.equal(readFileSync(join(newRoot, versioned), 'utf8'),
      readFileSync(join(oldRoot, legacy), 'utf8'),
      versioned + ' differs from deployed legacy SQL')
  }
  const policy = JSON.parse(readFileSync(join(root, 'app/deploy/migration-policy.json'), 'utf8'))
  assert.equal(policy.schema_version, 1)
  assert.ok(Array.isArray(policy.rules))
  const futureVersions = new Set()
  const future = policy.rules.map(rule => {
    assert.ok(Number.isInteger(rule.version) && rule.version > 21 && rule.version <= 1000)
    assert.ok(!futureVersions.has(rule.version), 'duplicate future migration version')
    futureVersions.add(rule.version)
    assert.equal(rule.mode, 'create-empty')
    assert.match(rule.file, new RegExp(`^V${rule.version}__[a-zA-Z0-9_]+\\.sql$`))
    assert.match(rule.sha256, /^[a-f0-9]{64}$/)
    const sql = readFileSync(join(newRoot, rule.file), 'utf8').replace(/\r\n/g, '\n')
    assert.equal(createHash('sha256').update(sql).digest('hex'), rule.sha256, 'future migration SQL digest drift')
    return rule.file
  })
  const actual = readdirSync(newRoot).filter(name => /^V[0-9]+__.*\.sql$/.test(name)).sort()
  assert.deepEqual(actual, [...mapping.map(x => x[1]), 'V8__ai_orchestrator.sql', 'V9__ai_provider_settings.sql', 'V10__openclaw_agent_tasks.sql', 'V11__codex_review_jobs.sql', 'V12__repair_legacy_food_seed_encoding.sql', 'V13__finance_ledger_foundation.sql', 'V14__ai_read_tools_and_navigation_cards.sql', 'V15__wellness_common_food_reference.sql', 'V16__wellness_ai_write_drafts.sql', 'V17__wellness_personal_dish_templates.sql', 'V18__ai_conversation_management.sql', 'V19__ai_action_record_targets.sql', 'V20__vocal_training.sql', 'V21__finance_bill_import.sql', ...future].sort(),
    'migration manifest changed: review and explicitly update verification for new migrations')
  assert.equal(legacyTables().length, 31, 'unexpected inventory of original tables')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  validateMirror()
  console.log('PASS: immutable V1-V7 mirror; legacy V8-V21 and declared future migrations registered; 31 legacy tables unchanged.')
}
