import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dateInTimeZone } from '../src/utils/wellnessDate.ts'

test('health business day follows the saved profile timezone across UTC midnight', () => {
  const at = new Date('2026-11-22T00:30:00.000Z')
  assert.equal(dateInTimeZone('Asia/Shanghai', at), '2026-11-22')
  assert.equal(dateInTimeZone('America/Los_Angeles', at), '2026-11-21')
  assert.equal(dateInTimeZone('UTC', at), '2026-11-22')
})

test('health business day handles the next-day boundary without device-time assumptions', () => {
  const at = new Date('2026-11-22T17:00:00.000Z')
  assert.equal(dateInTimeZone('Asia/Shanghai', at), '2026-11-23')
  assert.equal(dateInTimeZone('America/Los_Angeles', at), '2026-11-22')
})

test('invalid timezone falls back to the existing device-date behavior', () => {
  const at = new Date('2026-11-22T00:30:00.000Z')
  const expected = [at.getFullYear(), String(at.getMonth() + 1).padStart(2, '0'),
    String(at.getDate()).padStart(2, '0')].join('-')
  assert.equal(dateInTimeZone('invalid/zone', at), expected)
})

test('initial health load reads the profile before daily data and respects an explicit date query', () => {
  const view = readFileSync(new URL('../src/views/WellnessView.vue', import.meta.url), 'utf8')
  const section = view.split('async function loadAll() {')[1]?.split('onMounted(loadAll)')[0]
  assert.ok(section, 'expected loadAll()')
  assert.ok(section.indexOf('await wellnessApi.profile()') < section.indexOf('loadDay(),'),
    'loadDay must not start before the profile timezone is available')
  assert.match(section, /routeDateSelected.*date\.value === today/s)
  assert.match(section, /date\.value = wellnessToday\(\)/)
  assert.match(view, /goalForm\.effectiveFrom = wellnessToday\(\)/)
})
