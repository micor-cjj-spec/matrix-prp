import { spawnSync } from 'node:child_process'
import { legacyTables, validateMirror } from './verify-db-migrations.mjs'

// Read-only prerequisite; never applies DDL, baselines, or modifies existing data.
validateMirror()
const name = process.env.MATRIX_PRP_DB_NAME || 'matrix_prp'
const host = process.env.MATRIX_PRP_DB_HOST || '127.0.0.1'
const port = process.env.MATRIX_PRP_DB_PORT || '3306'
const user = process.env.MATRIX_PRP_DB_USER || 'matrix_prp'
if (!process.env.MYSQL_PWD) throw new Error('MYSQL_PWD is required; do not pass passwords in command arguments')
if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) throw new Error('Unsafe database name')

function query(sql) {
  const result = spawnSync('mysql', [
    '--batch', '--skip-column-names', '--raw', '--default-character-set=utf8mb4',
    '--host=' + host, '--port=' + port, '--user=' + user, '--database=' + name,
    '--execute=' + sql,
  ], { encoding: 'utf8', env: process.env, timeout: 15000, maxBuffer: 1024 * 1024 })
  if (result.error || result.status !== 0) {
    throw new Error('MySQL read-only preflight failed: ' +
      (result.error?.message || result.stderr || result.status))
  }
  return result.stdout.trim().split('\n').filter(Boolean)
}

const tables = new Set(query("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'"))
if (tables.has('flyway_schema_history')) {
  throw new Error('Flyway history already exists. Use flyway info/validate; do not baseline a second time.')
}
const missing = legacyTables().filter(table => !tables.has(table))
if (missing.length) throw new Error('Partial legacy installation: DO NOT baseline V7. Missing tables: ' + missing.join(', '))

const columns = new Set(query("SELECT CONCAT(TABLE_NAME, '.', COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()"))
const critical = [
  'prp_users.id', 'prp_users.password_hash', 'prp_users.enabled',
  'prp_tasks.user_id', 'prp_records.user_id', 'prp_finance_transactions.user_id',
  'prp_video_assets.storage_key', 'prp_push_subscriptions.endpoint_hash',
  'prp_practice_questions.fingerprint', 'prp_practice_ai_usage.usage_date',
  'prp_wellness_meals.idempotency_key', 'prp_wellness_goals.effective_from',
]
const missingColumns = critical.filter(column => !columns.has(column))
if (missingColumns.length) throw new Error('Unsafe legacy column mismatch: ' + missingColumns.join(', '))

console.log('PASS: 31 required historical tables and critical columns found; no Flyway history.')
console.log('This is a read-only preflight, NOT a complete schema diff or restorable backup verification.')
console.log('After verifying an actual restore, an operator may manually baseline at version 7.')
