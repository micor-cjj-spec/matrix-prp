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


test('home health daily date uses the owner timezone before reading calories', () => {
  const home = readFileSync(new URL('../src/views/DashboardView.vue', import.meta.url), 'utf8')
  const section = home.split('async function loadHomeWellnessDay() {')[1]
    ?? home.split('async function loadHomeWellnessDay(): Promise<DailySummary> {')[1]
  assert.ok(section, 'home health loader is missing')
  const logic = section.split('async function refresh()')[0]
  assert.ok(logic.includes('await wellnessApi.profile()'), 'profile must load first')
  assert.ok(logic.includes('dateInTimeZone(timeZone)'), 'owner business date must be used')
  assert.ok(logic.includes('wellnessApi.daily(dateInTimeZone(timeZone))'),
    'home health daily endpoint must receive the profile-based date')
  assert.ok(logic.indexOf('await wellnessApi.profile()') < logic.indexOf('wellnessApi.daily('),
    'profile request must complete before the health daily request')
  assert.match(logic, /new Intl\.DateTimeFormat\('en-US', \{ timeZone \}\)/,
    'invalid profile timezones must be rejected, not silently converted to device time')
  assert.ok(home.includes('fetchDashboardSummary(), loadHomeWellnessDay()'),
    'task summary must load independently alongside owner-timezone wellness')
  assert.ok(home.includes('wellness.value = null'),
    'failed profile/daily read must clear any stale health totals')
  assert.ok(!home.includes('wellnessApi.daily(today)'),
    'home must not use browser-local task date for health totals')
})
