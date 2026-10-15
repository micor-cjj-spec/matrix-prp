<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient, type ApiResponse } from '@/api/client'
import { wellnessApi, type Meal, type Exercise, type BodyMetric } from '@/api/wellness'
import WellnessChatCard from '@/components/ai/WellnessChatCard.vue'

type DraftState = {
  status: 'PENDING' | 'CONSUMED' | 'EXPIRED'
  draft: { draftId: string; action: string; values: { date?: string } }
}
type Target = { type: 'meal' | 'exercise' | 'metric'; recordId: number; record: Meal | Exercise | BodyMetric | null; deleted: boolean }
type ItemEdit = { foodId: number | null; name: string; grams: number; calories: number | null }
type MealEdit = { id: number; mealDate: string; mealType: string; note: string; items: ItemEdit[] }
type ExerciseEdit = { id: number; performedOn: string; name: string; durationMinutes: number; estimatedKcal: number | null; note: string }
type MetricEdit = { id: number; measuredOn: string; weightKg: number; bodyFatPct: number | null; waistCm: number | null }
const props = defineProps<{ modelValue: boolean; draftId: string | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; changed: [] }>()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const state = ref<DraftState | null>(null)
const targets = ref<Target[]>([])
const meals = ref<MealEdit[]>([])
const exercises = ref<ExerciseEdit[]>([])
const metrics = ref<MetricEdit[]>([])
const types = { BREAKFAST: '早餐', LUNCH: '午餐', DINNER: '晚餐', SNACK: '加餐' }
const fallback = computed(() => '/wellness' + (state.value?.draft.values.date
  ? '?date=' + encodeURIComponent(state.value.draft.values.date) : ''))
let serial = 0

function toMealEdit(meal: Meal): MealEdit {
  return { id: meal.id, mealDate: meal.mealDate, mealType: meal.mealType,
    note: meal.note || '', items: meal.items.map(food => ({
      foodId: food.foodId > 0 ? food.foodId : null,
      name: food.foodName, grams: Number(food.grams),
      calories: food.foodId > 0 ? null : Number(food.calories),
    })) }
}
async function reload() {
  if (!props.modelValue || !props.draftId || !/^[0-9a-fA-F-]{36}$/.test(props.draftId)) return
  const current = ++serial
  loading.value = true
  error.value = ''
  state.value = null
  try {
    const view = await apiClient.get<ApiResponse<DraftState>>('/wellness/ai/drafts/' + encodeURIComponent(props.draftId))
    if (current !== serial) return
    state.value = view.data.data
    targets.value = []; meals.value = []; exercises.value = []; metrics.value = []
    if (state.value.status === 'CONSUMED') {
      const response = await apiClient.get<ApiResponse<Target[]>>('/wellness/ai/drafts/' + encodeURIComponent(props.draftId) + '/targets')
      if (current !== serial) return
      targets.value = response.data.data
      for (const target of targets.value) {
        if (target.deleted || !target.record) continue
        if (target.type === 'meal') meals.value.push(toMealEdit(target.record as Meal))
        else if (target.type === 'exercise') {
          const item = target.record as Exercise
          exercises.value.push({ id: item.id, performedOn: item.performedOn, name: item.name,
            durationMinutes: item.durationMinutes,
            estimatedKcal: item.estimatedKcal == null ? null : Number(item.estimatedKcal),
            note: item.note || '' })
        } else if (target.type === 'metric') {
          const item = target.record as BodyMetric
          metrics.value.push({ id: item.id, measuredOn: item.measuredOn, weightKg: Number(item.weightKg),
            bodyFatPct: item.bodyFatPct == null ? null : Number(item.bodyFatPct),
            waistCm: item.waistCm == null ? null : Number(item.waistCm) })
        }
      }
    }
  } catch {
    if (current === serial) error.value = '读取操作记录失败，请核实登录状态后重试'
  } finally { if (current === serial) loading.value = false }
}
watch(() => [props.modelValue, props.draftId], () => { if (props.modelValue) void reload() }, { immediate: true })
function close() { if (!saving.value) emit('update:modelValue', false) }
function onVisibleChanged(visible: boolean) { if (!visible) close() }
async function saved() { emit('changed'); await reload() }
function errorMessage(e: unknown): string {
  const err = e as { response?: { status?: number; data?: { message?: string } } }
  if (err.response?.status === 404) return '原记录已删除，不能自动重新创建'
  if (err.response?.status === 409) return '记录已变化或该日期存在相同餐次，请重新打开核对'
  if (!err.response?.status || err.response.status >= 500) return '保存结果暂时不确定，请重新打开核实，不要连续提交'
  return err.response.data?.message || '保存失败，请核对字段'
}
async function updateMeal(item: MealEdit) {
  if (saving.value) return
  saving.value = true; error.value = ''
  try {
    const result = await wellnessApi.updateMealSnapshots(item.id, {
      mealDate: item.mealDate, mealType: item.mealType, note: item.note,
      items: item.items.map(food => ({
        foodId: food.foodId, name: food.foodId ? null : food.name,
        grams: food.grams, calories: food.foodId ? null : food.calories,
      })),
    })
    const index = meals.value.findIndex(m => m.id === item.id)
    if (index !== -1) meals.value[index] = toMealEdit(result)
    emit('changed'); ElMessage.success('修改已保存到健康中心')
  } catch (e) { error.value = errorMessage(e) }
  finally { saving.value = false }
}
async function updateExercise(item: ExerciseEdit) {
  if (saving.value) return
  saving.value = true; error.value = ''
  try {
    await wellnessApi.updateExercise(item.id, {
      performedOn: item.performedOn, name: item.name, durationMinutes: item.durationMinutes,
      estimatedKcal: item.estimatedKcal, note: item.note,
    })
    emit('changed'); ElMessage.success('运动记录已更新')
  } catch (e) { error.value = errorMessage(e) }
  finally { saving.value = false }
}
async function updateMetric(item: MetricEdit) {
  if (saving.value) return
  saving.value = true; error.value = ''
  try {
    await wellnessApi.updateMetric(item.id, {
      measuredOn: item.measuredOn, weightKg: item.weightKg,
      bodyFatPct: item.bodyFatPct, waistCm: item.waistCm,
    })
    emit('changed'); ElMessage.success('身体指标已更新')
  } catch (e) { error.value = errorMessage(e) }
  finally { saving.value = false }
}
</script>

<template>
  <el-dialog :model-value="modelValue" title="AI 健康记录" :width="'min(96vw, 700px)'"
    append-to-body :close-on-click-modal="false" :close-on-press-escape="!saving"
    class="prp-ai-action-dialog" @update:model-value="onVisibleChanged">
    <div class="ai-action-body">
      <p v-if="loading">正在加载记录…</p>
      <p v-if="error" class="ai-action-error" role="alert">{{ error }}</p>
      <template v-if="!loading && state">
        <WellnessChatCard v-if="state.status === 'PENDING' && draftId"
          :key="draftId" :draft-id="draftId" @saved="saved" />
        <template v-else-if="state.status === 'CONSUMED'">
          <p class="ai-action-ok">✓ 已保存。下方修改真实业务数据，不会新增重复记录。</p>
          <p v-if="!targets.length" class="ai-action-hint">
            这条历史记录尚未建立可靠的记录 ID 关联，请到健康中心修改。
            <RouterLink :to="fallback" @click="close">打开健康中心 →</RouterLink>
          </p>
          <p v-for="target in targets.filter(t => t.deleted)" :key="target.recordId" class="ai-action-error">
            记录 #{{ target.recordId }} 已删除，不会重新创建。
          </p>
          <section v-for="meal in meals" :key="'meal-' + meal.id" class="ai-action-section">
            <h3>饮食记录 #{{ meal.id }}</h3>
            <div class="ai-action-two">
              <label>日期<input v-model="meal.mealDate" type="date" :disabled="saving" /></label>
              <label>餐次<select v-model="meal.mealType" :disabled="saving">
                <option v-for="(name, key) in types" :key="key" :value="key">{{ name }}</option>
              </select></label>
            </div>
            <div v-for="(food, i) in meal.items" :key="i" class="ai-action-food">
              <label>食物名称<input v-model.trim="food.name" maxlength="120" :disabled="saving || food.foodId !== null" /></label>
              <div class="ai-action-two">
                <label>重量（克）<input v-model.number="food.grams" type="number" min="0" max="3000" step="0.1" :disabled="saving" /></label>
                <label>热量（kcal）<input v-if="food.foodId === null" v-model.number="food.calories" type="number" min="0.01" max="20000" step="0.01" :disabled="saving" />
                  <input v-else value="由食品库复算" disabled /></label>
              </div>
            </div>
            <label>备注<textarea v-model="meal.note" maxlength="500" rows="2" :disabled="saving" /></label>
            <p class="ai-action-hint">食品库模式由服务器按实际重量重新计算热量；自定义热量保留本次快照。</p>
            <button type="button" class="ai-action-submit" :disabled="saving" @click="updateMeal(meal)">保存修改</button>
          </section>
          <section v-for="exercise in exercises" :key="'exercise-' + exercise.id" class="ai-action-section">
            <h3>运动记录 #{{ exercise.id }}</h3>
            <label>日期<input v-model="exercise.performedOn" type="date" :disabled="saving" /></label>
            <label>运动项目<input v-model.trim="exercise.name" maxlength="100" :disabled="saving" /></label>
            <div class="ai-action-two">
              <label>时长（分钟）<input v-model.number="exercise.durationMinutes" type="number" min="1" max="1440" :disabled="saving" /></label>
              <label>估算消耗（kcal）<input v-model.number="exercise.estimatedKcal" type="number" min="0" max="20000" :disabled="saving" /></label>
            </div>
            <label>备注<textarea v-model="exercise.note" maxlength="500" rows="2" :disabled="saving" /></label>
            <button class="ai-action-submit" type="button" :disabled="saving" @click="updateExercise(exercise)">保存修改</button>
          </section>
          <section v-for="metric in metrics" :key="'metric-' + metric.id" class="ai-action-section">
            <h3>身体指标 #{{ metric.id }}</h3>
            <label>日期<input v-model="metric.measuredOn" type="date" :disabled="saving" /></label>
            <div class="ai-action-two">
              <label>体重（kg）<input v-model.number="metric.weightKg" type="number" min="0.1" max="500" step="0.1" :disabled="saving" /></label>
              <label>体脂率（%）<input v-model.number="metric.bodyFatPct" type="number" min="0" max="100" step="0.1" :disabled="saving" /></label>
            </div>
            <label>腰围（cm）<input v-model.number="metric.waistCm" type="number" min="0" max="300" step="0.1" :disabled="saving" /></label>
            <button class="ai-action-submit" type="button" :disabled="saving" @click="updateMetric(metric)">保存修改</button>
          </section>
        </template>
        <p v-else class="ai-action-hint">草稿已过期，未写入健康中心。请重新生成记录。</p>
      </template>
      <button v-if="!loading && error && !state" type="button" class="ai-action-submit" @click="reload">重新读取</button>
    </div>
    <template #footer><el-button :disabled="saving" @click="close">关闭</el-button></template>
  </el-dialog>
</template>
<style>
.prp-ai-action-dialog .el-dialog__body{max-height:min(72vh,740px);overflow-y:auto;overscroll-behavior:contain;padding:10px 20px}
.prp-ai-action-dialog .health-chat-card{margin:0;max-width:none;padding:0;background:transparent;border:0}
.prp-ai-action-dialog .ai-action-body{font-size:14px;line-height:1.65;color:#30435b}
.prp-ai-action-dialog .ai-action-ok{color:#168053}
.prp-ai-action-dialog .ai-action-error{color:#b42318;overflow-wrap:anywhere}
.prp-ai-action-dialog .ai-action-hint{font-size:12px;color:#64748b}
.prp-ai-action-dialog .ai-action-section{border-top:1px solid #e2e8f0;margin-top:15px;padding-top:15px;display:grid;gap:12px}
.prp-ai-action-dialog h3{margin:0;font-size:15px}
.prp-ai-action-dialog label{display:grid;gap:5px;color:#475569;font-size:13px;min-width:0}
.prp-ai-action-dialog input,.prp-ai-action-dialog select,.prp-ai-action-dialog textarea{box-sizing:border-box;width:100%;min-width:0;min-height:40px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;font:inherit;font-size:16px}
.prp-ai-action-dialog input:disabled{background:#f5f7fb}
.prp-ai-action-dialog .ai-action-two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.prp-ai-action-dialog .ai-action-food{display:grid;gap:8px;padding:12px;background:#f7f9fc;border-radius:9px}
.prp-ai-action-dialog .ai-action-submit{background:#2563eb;border:0;color:white;border-radius:8px;padding:10px 15px;min-height:42px;font-weight:600;cursor:pointer}
.prp-ai-action-dialog .ai-action-submit:disabled{opacity:.55;cursor:not-allowed}
@media(max-width:550px){.prp-ai-action-dialog .ai-action-two{grid-template-columns:1fr}.prp-ai-action-dialog .el-dialog__body{padding:8px 14px}}
</style>
