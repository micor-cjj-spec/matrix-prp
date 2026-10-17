import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

test('future declared SQL registers without changing the legacy manifest; tampering/unlisted SQL fails', () => {
  const parent = realpathSync(tmpdir())
  const scratch = mkdtempSync(join(parent, 'matrix-policy-test-'))
  try {
    mkdirSync(join(scratch, 'app/scripts'), { recursive: true })
    mkdirSync(join(scratch, 'app/deploy'), { recursive: true })
    cpSync(join(root, 'app/docker/mysql/init'), join(scratch, 'app/docker/mysql/init'), { recursive: true })
    const migrations = join(scratch, 'app/backend/src/main/resources/db/migration')
    cpSync(join(root, 'app/backend/src/main/resources/db/migration'), migrations, { recursive: true })
    const verifier = join(scratch, 'app/scripts/verify-db-migrations.mjs')
    writeFileSync(verifier, readFileSync(join(root, 'app/scripts/verify-db-migrations.mjs')))
    const sql = 'CREATE TABLE prp_next_notes (id BIGINT PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;'
    writeFileSync(join(migrations, 'V23__next_notes.sql'), sql)
    const policy = JSON.parse(readFileSync(join(root, 'app/deploy/migration-policy.json'), 'utf8'))
    policy.rules.push({ version: 23, file: 'V23__next_notes.sql',
      sha256: createHash('sha256').update(sql).digest('hex'), mode: 'create-empty', tables: ['prp_next_notes'] })
    writeFileSync(join(scratch, 'app/deploy/migration-policy.json'), JSON.stringify(policy))
    const run = () => spawnSync(process.execPath, [verifier], { encoding: 'utf8' })
    const valid = run()
    assert.equal(valid.status, 0, valid.stderr)
    writeFileSync(join(migrations, 'V23__next_notes.sql'), sql + '\nDROP TABLE prp_users;')
    assert.notEqual(run().status, 0, 'Changed SQL must fail its declared digest')
    writeFileSync(join(migrations, 'V23__next_notes.sql'), sql)
    writeFileSync(join(migrations, 'V24__unlisted.sql'), sql.replace('prp_next_notes', 'prp_unlisted'))
    assert.notEqual(run().status, 0, 'Unlisted migration must fail the registered inventory')
  } finally {
    assert.equal(dirname(scratch), parent)
    assert.ok(scratch.startsWith(join(parent, 'matrix-policy-test-')))
    rmSync(scratch, { recursive: true, force: true })
  }
})
