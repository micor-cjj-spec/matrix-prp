import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { reactive, ref } from 'vue'
import { cloneJson } from '../src/utils/cloneJson.ts'

test('clones Vue proxy forms without browser DataCloneError', () => {
  const state = ref({
    date: '2026-10-14',
    mealType: 'BREAKFAST',
    items: [{ name: '全麦面包', foodId: 12, grams: 60, calories: 148 }],
    note: 'source: USDA FDC 2705385',
  })
  assert.throws(() => structuredClone(state.value), { name: 'DataCloneError' })
  const corrected = cloneJson(state.value)
  assert.deepEqual(corrected, {
    date: '2026-10-14', mealType: 'BREAKFAST',
    items: [{ name: '全麦面包', foodId: 12, grams: 60, calories: 148 }],
    note: 'source: USDA FDC 2705385',
  })
  assert.equal(Object.getPrototypeOf(corrected), Object.prototype)
  corrected.items[0].grams = 70
  assert.equal(state.value.items[0].grams, 60)
})

test('nested Vue proxies clone to ordinary JSON, preserving nullable fields', () => {
  const source = reactive({
    date: '2026-10-14',
    items: reactive([{ foodId: 1, grams: 100 }]),
    weightKg: null,
    bodyFatPct: null,
  })
  const result = cloneJson(source)
  assert.deepEqual(result, {
    date: '2026-10-14', items: [{ foodId: 1, grams: 100 }],
    weightKg: null, bodyFatPct: null,
  })
  assert.doesNotThrow(() => structuredClone(result))
})

test('all health draft paths clone reactive state as JSON, not structuredClone', () => {
  const paths = [
    '../src/components/ai/WellnessChatCard.vue',
    '../src/components/wellness/WellnessAiRecorder.vue',
    '../src/components/wellness/WellnessAiChange.vue',
  ]
  for (const path of paths) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    assert.match(source, /import \{ cloneJson \} from '@\/utils\/cloneJson'/, path)
    assert.doesNotMatch(source, /structuredClone\s*\(/, path)
  }
  const chat = readFileSync(new URL(paths[0], import.meta.url), 'utf8')
  const capture = readFileSync(new URL(paths[1], import.meta.url), 'utf8')
  assert.match(chat, /const corrected = cloneJson\(values\.value\)/)
  assert.match(capture, /const v = cloneJson\(values\.value\)/)
})
