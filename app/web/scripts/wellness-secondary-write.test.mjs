import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// Static regression checks for UI write acknowledgments. Real HTTP and iPhone
// failure injection still belongs to dedicated Health V2 stage UAT.
const view = readFileSync(new URL('../src/views/WellnessView.vue', import.meta.url), 'utf8')
function method(name, nextName) {
  const start = view.indexOf('async function ' + name + '(')
  const end = view.indexOf(nextName, start)
  assert.ok(start >= 0 && end > start, 'Missing ' + name)
  return view.slice(start, end)
}

for (const { name, next, mutation, saved, uncertain } of [
  { name: 'saveExercise', next: 'async function deleteExercise', mutation: 'wellnessApi.addExercise', saved: '运动记录已保存', uncertain: '运动记录保存请求未确认' },
  { name: 'deleteExercise', next: 'const metricDialog', mutation: 'wellnessApi.deleteExercise', saved: '运动记录已删除', uncertain: '删除请求未确认' },
  { name: 'saveMetric', next: 'async function deleteMetric', mutation: 'wellnessApi.addMetric', saved: '身体数据已保存', uncertain: '身体数据保存请求未确认' },
  { name: 'deleteMetric', next: 'const goalForm', mutation: 'wellnessApi.deleteMetric', saved: '身体数据已删除', uncertain: '删除请求未确认' },
  { name: 'saveGoal', next: 'async function saveProfile', mutation: 'wellnessApi.saveGoal', saved: '健康目标已保存', uncertain: '目标保存请求未确认' },
]) {
  test(name + ' keeps post-write readback failure distinct from uncertain mutation', () => {
    const body = method(name, next)
    const writeAt = body.indexOf('await ' + mutation)
    const warningAt = body.indexOf("ElMessage.warning('" + saved + '，但页面刷新失败')
    const errorAt = body.indexOf("ElMessage.error('" + uncertain)
    assert.ok(writeAt >= 0 && warningAt > writeAt, name + ': missing post-write warning')
    assert.ok(errorAt > warningAt, name + ': missing distinct uncertain-write error')
    assert.match(body, /loadDay\(true\)/)
    assert.match(body, /catch \{[\s\S]+?ElMessage\.warning\(/)
  })
}
test('new exercise, metric and goal writes have rapid-resubmit guards', () => {
  for (const [name, next] of [['saveExercise', 'async function deleteExercise'],
    ['saveMetric', 'async function deleteMetric'],
    ['saveGoal', 'async function saveProfile']]) {
    assert.match(method(name, next), /if \(saving\.value\) return/)
  }
})

const aiChange = readFileSync(new URL('../src/components/wellness/WellnessAiChange.vue', import.meta.url), 'utf8')
const aiRecorder = readFileSync(new URL('../src/components/wellness/WellnessAiRecorder.vue', import.meta.url), 'utf8')

test('AI record change distinguishes confirmed mutation from failed record-list refresh', () => {
  assert.match(aiChange, /async function refreshRecords\(\): Promise<boolean>/)
  assert.match(aiChange, /return false/)
  assert.match(aiChange, /const refreshed=await refreshRecords\(\)/)
  assert.match(aiChange, /if\(refreshed\) ElMessage\.success/)
  assert.match(aiChange, /已修改或删除，但列表刷新失败/)
  assert.match(aiChange, /confirmStarted/)
  assert.match(aiChange, /confirmOutcomeUncertain\.value=true/)
  assert.match(aiChange, /saving\|\|confirmOutcomeUncertain/)
  assert.match(aiChange, /确认请求结果未核实/)
})

test('AI draft confirmation checks owner-scoped status without replaying a POST', () => {
  const save = aiRecorder.split('async function save() {')[1]?.split('</script>')[0]
  assert.ok(save)
  assert.match(save, /const draftId = draft\.value\.draftId/)
  assert.match(save, /confirmStarted = true/)
  assert.match(save, /apiClient\.get<ApiResponse<\{ status: string \}>>/)
  assert.match(save, /checked\.data\.data\.status === 'CONSUMED'/)
  assert.match(save, /已核实草稿保存成功/)
  assert.match(save, /回读也失败/)
  assert.match(aiRecorder, /confirmOutcomeUncertain\.value = true/)
  assert.match(aiRecorder, /confirming \|\| confirmOutcomeUncertain/)
  assert.equal((save.match(/apiClient\.post<ApiResponse<Outcome>>/g) ?? []).length, 1,
    'failed confirmation must not replay POST automatically')
})
