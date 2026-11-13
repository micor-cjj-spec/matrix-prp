<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import WellnessAiRecorder from '@/components/wellness/WellnessAiRecorder.vue'
import WellnessAiChange from '@/components/wellness/WellnessAiChange.vue'
import PersonalDishManager from '@/components/wellness/PersonalDishManager.vue'
import {
  wellnessApi, type UsdaCandidate, type Food, type Meal, type MealInput, type MealSnapshotItem, type Exercise, type ExerciseInput,
  type BodyMetric, type BodyMetricInput, type DailySummary, type TrendPoint, type MealAnalysisDetails,
  type Goal, type Profile,
} from '@/api/wellness'

const localDate = () => {
  const d = new Date()
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
}
const route = useRoute()
const today = localDate()
const initialDate = route.query.date
const date = ref(typeof initialDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(initialDate) ? initialDate : today)
watch(() => route.query.date, (next) => {
  if (typeof next === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(next)) {
    date.value = next
    void loadDay()
  }
})
const activeTab = ref('today')
const loading = ref(false)
const saving = ref(false)
const summary = ref<DailySummary | null>(null)
const meals = ref<Meal[]>([])
const exercises = ref<Exercise[]>([])
const metrics = ref<BodyMetric[]>([])
const goals = ref<Goal[]>([])
const trend = ref<TrendPoint[]>([])
const trendDays = ref(14)
const foods = ref<Food[]>([])
const frequentFoods = ref<Food[]>([])
const profile = reactive<Profile>({ heightCm: null, timezone: 'Asia/Shanghai' })
const selectedGoal = computed(() => summary.value?.goal)
const calories = computed(() => summary.value?.calories === null || summary.value?.calories === undefined ? null : Number(summary.value.calories))
const dailyGoal = computed(() => Number(selectedGoal.value?.dailyCalories || 0))
const pct = computed(() => dailyGoal.value && calories.value !== null ? Math.min(100, Math.round(calories.value / dailyGoal.value * 100)) : 0)
const maxTrend = computed(() => Math.max(1, ...trend.value.map(x => Number(x.calories || 0))))
const weightHistory = computed(() => trend.value.filter(x => x.weightKg !== null))
const weightChart = computed(() => {
  const points = weightHistory.value
  const values = points.map(x => Number(x.weightKg))
  const min = Math.min(...values) - 0.5
  const max = Math.max(...values) + 0.5
  return points.map((p, idx) => ({
    x: points.length === 1 ? 170 : 10 + idx * 320 / (points.length - 1),
    y: 110 - (Number(p.weightKg) - min) / (max - min) * 94,
    label: p.date + ' · ' + p.weightKg + ' kg',
  }))
})
const weightPolyline = computed(() => weightChart.value.map(p => p.x.toFixed(2) + ',' + p.y.toFixed(2)).join(' '))
const label = (kind: string) => ({ BREAKFAST: '早餐', LUNCH: '午餐', DINNER: '晚餐', SNACK: '加餐' }[kind] || kind)
const n = (x: string | number | null | undefined, digits = 0) => x == null ? '—' : Number(x).toFixed(digits)
const total = (meal: Meal) => meal.items.reduce((sum, x) => sum + Number(x.calories), 0)
const mealKinds = ['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK']
// A 0g snapshot on a manually estimated food means unknown weight, not zero intake.
const portionText = (item: Meal['items'][number]) =>
  item.grams == null || (item.foodId <= 0 && Number(item.grams) === 0)
    ? '重量待确认'
    : n(item.grams) + 'g'
const analysisDialog = ref(false)
const analysisLoading = ref(false)
const analysisDetails = ref<MealAnalysisDetails | null>(null)
const analysisError = ref('')
const labelSaving = ref(false)
type LabelCandidate = { caloriesKcal?: number | string; proteinG?: number | string
  carbsG?: number | string; fatG?: number | string; fiberG?: number | string
  sugarG?: number | string; sodiumMg?: number | string }
const labelReview = reactive({
  mealItemId: 0, consumedGrams: null as number | null,
  caloriesPer100g: null as number | null, proteinPer100g: null as number | null,
  carbsPer100g: null as number | null, fatPer100g: null as number | null,
  fiberPer100g: null as number | null, sugarPer100g: null as number | null,
  sodiumMgPer100g: null as number | null, userVerified: false,
})
const labelPreview = computed(() =>
  labelReview.consumedGrams != null && labelReview.caloriesPer100g != null
    ? (Number(labelReview.consumedGrams) * Number(labelReview.caloriesPer100g) / 100).toFixed(2)
    : '—')
const numericLabel = (x: string | number | undefined): number | null =>
  x === undefined ? null : Number(x)
function beginLabelReview(name: string, candidate: LabelCandidate) {
  const matched = analysisDetails.value?.meal.items.filter(item =>
    item.foodName === name && item.foodId <= 0) ?? []
  if (matched.length !== 1) {
    ElMessage.warning('包装食物名称与已确认餐食不一致或有重名，请先核对餐食明细')
    return
  }
  Object.assign(labelReview, {
    mealItemId: matched[0].id,
    consumedGrams: Number(matched[0].grams) > 0 ? Number(matched[0].grams) : null,
    caloriesPer100g: numericLabel(candidate.caloriesKcal),
    proteinPer100g: numericLabel(candidate.proteinG),
    carbsPer100g: numericLabel(candidate.carbsG),
    fatPer100g: numericLabel(candidate.fatG),
    fiberPer100g: numericLabel(candidate.fiberG),
    sugarPer100g: numericLabel(candidate.sugarG),
    sodiumMgPer100g: numericLabel(candidate.sodiumMg),
    userVerified: false,
  })
}
async function submitLabelReview() {
  if (!analysisDetails.value || labelSaving.value || !labelReview.mealItemId) return
  if (!labelReview.userVerified || labelReview.consumedGrams == null ||
      ![labelReview.caloriesPer100g, labelReview.proteinPer100g,
        labelReview.carbsPer100g, labelReview.fatPer100g].every(x => x != null && Number.isFinite(x))) {
    ElMessage.warning('请核对每100g热量、三大营养素和实际食用克数，并勾选人工核实')
    return
  }
  const id = analysisDetails.value.meal.id
  labelSaving.value = true
  try {
    analysisDetails.value = await wellnessApi.verifyMealLabel(id, {
      mealItemId: labelReview.mealItemId, consumedGrams: Number(labelReview.consumedGrams),
      caloriesPer100g: Number(labelReview.caloriesPer100g),
      proteinPer100g: Number(labelReview.proteinPer100g),
      carbsPer100g: Number(labelReview.carbsPer100g),
      fatPer100g: Number(labelReview.fatPer100g),
      fiberPer100g: labelReview.fiberPer100g,
      sugarPer100g: labelReview.sugarPer100g,
      sodiumMgPer100g: labelReview.sodiumMgPer100g,
      userVerified: true,
    })
    labelReview.mealItemId = 0
    ElMessage.success('已按实际食用克数计算营养，并保存人工核实版本')
    await loadDay()
  } catch (error) {
    const message = (error as { response?: { data?: { message?: string } } }).response?.data?.message
    ElMessage.error(message || '营养标签核实失败，请核对字段和包装信息')
  } finally {
    labelSaving.value = false
  }
}
async function openAnalysis(meal: Meal) {
  analysisDetails.value = null
  analysisError.value = ''
  labelReview.mealItemId = 0
  analysisDialog.value = true
  analysisLoading.value = true
  try {
    analysisDetails.value = await wellnessApi.mealAnalysis(meal.id)
  } catch {
    analysisError.value = '无法读取该餐次的分析详情；请确认健康 V2 接口已经部署。'
  } finally {
    analysisLoading.value = false
  }
}
const nutrientSourceLabel = (source: string) => source === 'FOOD_CATALOG'
  ? '食品库参考' : source === 'USER_LABEL' ? '用户核实的包装营养标签'
  : source === 'USER_ESTIMATE' ? '本次食物估算' : '来源待核对'
const nutritionCoverage = computed(() => {
  const items = meals.value.flatMap(meal => meal.items)
  const known = items.filter(item =>
    item.proteinG != null && item.carbsG != null && item.fatG != null).length
  return {
    known,
    total: items.length,
    percent: items.length ? Math.round(known * 100 / items.length) : null,
    complete: items.length > 0 && known === items.length,
  }
})

async function loadDay() {
  loading.value = true
  try {
    const [a, b, c] = await Promise.all([
      wellnessApi.daily(date.value), wellnessApi.meals(date.value), wellnessApi.exercises(date.value),
    ])
    summary.value = a; meals.value = b; exercises.value = c
  } catch {
    ElMessage.error('获取健康记录失败，请确认服务器已执行健康模块数据库迁移')
  } finally { loading.value = false }
}
function onTabChange(tab: string | number) { if (tab === 'goals') loadGoal() }
async function loadAll() {
  await Promise.all([
    loadDay(),
    wellnessApi.metrics(90).then(x => { metrics.value = x }),
    wellnessApi.goals().then(x => { goals.value = x }),
    wellnessApi.trends(14).then(x => { trend.value = x }),
    wellnessApi.foods().then(x => { foods.value = x }),
    wellnessApi.frequent().then(x => { frequentFoods.value = x }),
    wellnessApi.profile().then(x => { Object.assign(profile, x) }),
  ]).catch(() => { ElMessage.warning('部分健康资料未加载，请检查数据库迁移') })
}
onMounted(loadAll)

const mealDialog = ref(false)
const editingMeal = ref<number | null>(null)
const mealForm = reactive<MealInput>({ mealDate: today, mealType: 'BREAKFAST', note: '', items: [] })
type DraftItem = {
  foodId: number | null; grams: number; manual: boolean
  customName: string; customCalories: number
}
const draftItems = ref<DraftItem[]>([])
function openMeal(kind = 'BREAKFAST', meal?: Meal) {
  editingMeal.value = meal?.id ?? null
  mealForm.mealDate = meal?.mealDate ?? date.value
  mealForm.mealType = meal?.mealType ?? kind
  mealForm.note = meal?.note || ''
  draftItems.value = meal ? meal.items.map(i => ({
    foodId: i.foodId > 0 ? i.foodId : null,
    grams: Number(i.grams), manual: i.foodId <= 0,
    customName: i.foodId <= 0 ? i.foodName : '',
    customCalories: i.foodId <= 0 ? Number(i.calories) : 0,
  })) : [{ foodId: null, grams: 100, manual: false, customName: '', customCalories: 0 }]
  mealDialog.value = true
}
function addItem(foodId: number | null = null) {
  draftItems.value.push({ foodId, grams: 100, manual: false, customName: '', customCalories: 0 })
}
const mealPreview = computed(() => draftItems.value.reduce((sum, item) => {
  const food = foods.value.find(f => f.id === item.foodId)
  return sum + (item.manual ? Number(item.customCalories || 0) :
    food ? Number(food.calories100g) * Number(item.grams || 0) / 100 : 0)
}, 0))
async function searchFoods(q: string) {
  try {
    const found = await wellnessApi.foods(q)
    // Preserve selected entries while searching, so options don't disappear.
    foods.value = [...new Map([...foods.value, ...found].map(x => [x.id, x])).values()]
  } catch { ElMessage.error('食物搜索失败') }
}
async function saveMeal() {
  if (!draftItems.value.length || draftItems.value.length > 30 ||
      draftItems.value.some(item => item.manual
        ? !item.customName.trim() || item.customName.length > 120 ||
          !Number.isFinite(Number(item.customCalories)) || item.customCalories <= 0 ||
          item.customCalories > 20000 || Math.abs(item.customCalories * 100 - Math.round(item.customCalories * 100)) > 1e-6 ||
          !Number.isFinite(item.grams) || item.grams < 0 || item.grams > 3000
        : !item.foodId || !Number.isFinite(item.grams) || item.grams <= 0 || item.grams > 3000)) {
    ElMessage.warning('请完整填写食物、份量或本次热量')
    return
  }
  saving.value = true
  try {
    const key = editingMeal.value === null ? crypto.randomUUID() : undefined
    const hasManual = draftItems.value.some(item => item.manual)
    if (hasManual) {
      const items: MealSnapshotItem[] = draftItems.value.map(item => item.manual
        ? { foodId: null, name: item.customName.trim(), grams: item.grams, calories: item.customCalories }
        : { foodId: item.foodId, name: null, grams: item.grams, calories: null })
      const payload = { mealDate: mealForm.mealDate, mealType: mealForm.mealType, note: mealForm.note,
        items, idempotencyKey: key }
      if (editingMeal.value !== null) await wellnessApi.updateMealSnapshots(editingMeal.value, payload)
      else await wellnessApi.addMealSnapshots(payload)
    } else {
      const items = draftItems.value.map(item => ({ foodId: Number(item.foodId), grams: item.grams }))
      const payload: MealInput = { mealDate: mealForm.mealDate, mealType: mealForm.mealType,
        note: mealForm.note, items, idempotencyKey: key }
      if (editingMeal.value !== null) await wellnessApi.updateMeal(editingMeal.value, payload)
      else await wellnessApi.addMeal(payload)
    }
    ElMessage.success('餐食已保存')
    mealDialog.value = false; date.value = mealForm.mealDate
    await Promise.all([loadDay(), wellnessApi.frequent().then(x => { frequentFoods.value = x }), loadTrend()])
  } catch { ElMessage.error('餐食保存失败') } finally { saving.value = false }
}
async function deleteMeal(meal: Meal) {
  try { await ElMessageBox.confirm('确定删除这条' + label(meal.mealType) + '记录吗？', '确认删除') } catch { return }
  try { await wellnessApi.deleteMeal(meal.id); await Promise.all([loadDay(), loadTrend()]); ElMessage.success('已删除') }
  catch { ElMessage.error('删除失败') }
}
async function copyMeal(meal: Meal) {
  try { await wellnessApi.copyMeal(meal.id, today); date.value = today; await Promise.all([loadDay(), loadTrend()]); ElMessage.success('已复制到今天') }
  catch { ElMessage.error('复制失败') }
}
async function loadTrend() { trend.value = await wellnessApi.trends(trendDays.value) }

const usdaDialog = ref(false)
const usdaQuery = ref('')
const usdaConfigured = ref(false)
const usdaResults = ref<UsdaCandidate[]>([])
const usdaSearching = ref(false)
const importingUsda = ref<number | null>(null)
async function openUsda() {
  usdaDialog.value = true
  try { usdaConfigured.value = (await wellnessApi.usdaStatus()).configured }
  catch { usdaConfigured.value = false }
}
async function searchUsda() {
  if (!usdaQuery.value.trim() || usdaSearching.value) return
  usdaSearching.value = true
  try { usdaResults.value = await wellnessApi.searchUsda(usdaQuery.value.trim()) }
  catch { ElMessage.error('USDA 查询失败，请检查服务器 API Key、网络或限流') }
  finally { usdaSearching.value = false }
}
async function importUsdaFood(row: UsdaCandidate) {
  importingUsda.value = row.fdcId
  try {
    const alias = /[\\u3400-\\u9fff]/u.test(usdaQuery.value) ? usdaQuery.value.trim() : undefined
    const food = await wellnessApi.importUsda(row.fdcId, alias)
    foods.value = [...new Map([food, ...foods.value].map(x => [x.id, x])).values()]
    ElMessage.success('已导入个人食物库，可在餐次中使用')
  } catch { ElMessage.error('导入失败，可能缺少可靠的每100g营养字段') }
  finally { importingUsda.value = null }
}
const aiChangeVisible = ref(false)
const aiChangeKind = ref<'meal'|'exercise'|'metric'>('meal')
const aiChangeRecord = ref(0)
const aiChangeKey = ref(0)
function openAiChange(kind: 'meal'|'exercise'|'metric', id: number) {
  aiChangeKind.value = kind
  aiChangeRecord.value = id
  aiChangeKey.value++
  aiChangeVisible.value = true
}
async function savedAiChange() {
  aiChangeVisible.value = false
  await loadAll()
}
const foodDialog = ref(false)
const foodForm = reactive({ name: '', preparation: 'unspecified',
  calories100g: 0, protein100g: 0, carbs100g: 0, fat100g: 0, sourceNote: '' })
async function saveFood() {
  if (!foodForm.name.trim() || foodForm.calories100g < 0) { ElMessage.warning('请输入有效的食物名称和营养信息'); return }
  saving.value = true
  try {
    const x = await wellnessApi.addFood({ ...foodForm })
    foods.value.unshift(x); foodDialog.value = false; ElMessage.success('自定义食物已加入食物库')
  } catch { ElMessage.error('新增食物失败') } finally { saving.value = false }
}

const exerciseDialog = ref(false)
const editExerciseId = ref<number | null>(null)
const exerciseForm = reactive<ExerciseInput>({ performedOn: today, name: '步行', durationMinutes: 30, estimatedKcal: null, note: '' })
function openExercise(x?: Exercise) {
  editExerciseId.value = x?.id ?? null
  Object.assign(exerciseForm, x ? { performedOn: x.performedOn, name: x.name,
    durationMinutes: x.durationMinutes, estimatedKcal: x.estimatedKcal ? Number(x.estimatedKcal) : null, note: x.note || '' }
    : { performedOn: date.value, name: '步行', durationMinutes: 30, estimatedKcal: null, note: '' })
  exerciseDialog.value = true
}
async function saveExercise() {
  if (!exerciseForm.name.trim() || exerciseForm.durationMinutes < 1) { ElMessage.warning('请输入有效的运动名称和时长'); return }
  saving.value = true
  try {
    if (editExerciseId.value !== null) await wellnessApi.updateExercise(editExerciseId.value, { ...exerciseForm })
    else await wellnessApi.addExercise({ ...exerciseForm })
    exerciseDialog.value = false; date.value = exerciseForm.performedOn
    await Promise.all([loadDay(), loadTrend()]); ElMessage.success('运动记录已保存')
  } catch { ElMessage.error('保存运动失败') } finally { saving.value = false }
}
async function deleteExercise(id: number) {
  try { await ElMessageBox.confirm('确定删除这条运动记录吗？', '确认删除') } catch { return }
  try { await wellnessApi.deleteExercise(id); await Promise.all([loadDay(),loadTrend()]); ElMessage.success('已删除') }
  catch { ElMessage.error('删除失败') }
}

const metricDialog = ref(false)
const editMetricId = ref<number | null>(null)
const metricForm = reactive<BodyMetricInput>({ measuredOn: today, weightKg: 0, bodyFatPct: null, waistCm: null })
function openMetric(x?: BodyMetric) {
  editMetricId.value = x?.id ?? null
  Object.assign(metricForm, x ? { measuredOn: x.measuredOn, weightKg: Number(x.weightKg),
    bodyFatPct: x.bodyFatPct === null ? null : Number(x.bodyFatPct),
    waistCm: x.waistCm === null ? null : Number(x.waistCm) }
    : { measuredOn: date.value, weightKg: 0, bodyFatPct: null, waistCm: null })
  metricDialog.value = true
}
async function saveMetric() {
  if (metricForm.weightKg <= 0) { ElMessage.warning('请填写体重'); return }
  saving.value = true
  try {
    if (editMetricId.value !== null) await wellnessApi.updateMetric(editMetricId.value, { ...metricForm })
    else await wellnessApi.addMetric({ ...metricForm })
    metricDialog.value = false
    metrics.value = await wellnessApi.metrics(90)
    await Promise.all([loadDay(),loadTrend()]); ElMessage.success('身体数据已保存')
  } catch { ElMessage.error('保存身体数据失败') } finally { saving.value = false }
}
async function deleteMetric(id: number) {
  try { await ElMessageBox.confirm('确定删除这条身体指标记录吗？', '确认删除') } catch { return }
  try {
    await wellnessApi.deleteMetric(id)
    metrics.value = await wellnessApi.metrics(90)
    await Promise.all([loadDay(),loadTrend()]); ElMessage.success('已删除')
  } catch { ElMessage.error('删除失败') }
}

const goalForm = reactive({ effectiveFrom: today, dailyCalories: 0, dailyProteinG: null as number | null,
  weeklyActivityMinutes: null as number | null })
function loadGoal() {
  const current = goals.value.find(x => x.effectiveFrom <= date.value)
  goalForm.effectiveFrom = today
  goalForm.dailyCalories = current ? Number(current.dailyCalories) : 0
  goalForm.dailyProteinG = current?.dailyProteinG == null ? null : Number(current.dailyProteinG)
  goalForm.weeklyActivityMinutes = current?.weeklyActivityMinutes ?? null
}
async function saveGoal() {
  if (!goalForm.dailyCalories || goalForm.dailyCalories < 100) { ElMessage.warning('请先填写每日摄入目标'); return }
  saving.value = true
  try {
    await wellnessApi.saveGoal({ ...goalForm })
    goals.value = await wellnessApi.goals(); await loadDay()
    ElMessage.success('健康目标已保存')
  } catch { ElMessage.error('保存目标失败') } finally { saving.value = false }
}
async function saveProfile() {
  saving.value = true
  try { Object.assign(profile, await wellnessApi.saveProfile({ ...profile })); ElMessage.success('个人设置已保存') }
  catch { ElMessage.error('保存个人设置失败，请检查时区名称') } finally { saving.value = false }
}
</script>

<template>
  <AppLayout>
    <div class="wellness-page" v-loading="loading">
      <div class="head">
        <div><h1>健康中心</h1><p>饮食、运动与身体指标，记录每一天</p></div>
        <el-date-picker v-model="date" type="date" value-format="YYYY-MM-DD" :clearable="false" @change="loadDay" />
      </div>
      <el-tabs v-model="activeTab" class="wellness-tabs" @tab-change="onTabChange">
        <el-tab-pane label="AI 快速记录" name="ai">
          <WellnessAiRecorder @recorded="loadAll" />
        </el-tab-pane>
        <el-tab-pane label="今日概览" name="today">
          <section class="metric-grid">
            <article class="tile hero">
              <span>今日摄入</span>
              <strong>{{ calories === null ? '未记录' : n(calories) + ' kcal' }}</strong>
              <p v-if="dailyGoal">目标 {{ n(dailyGoal) }} kcal · {{ pct }}%</p>
              <p v-else>尚未设置每日热量目标</p>
              <el-progress v-if="dailyGoal && calories !== null" :percentage="pct" :show-text="false" />
            </article>
            <article class="tile"><span>蛋白质</span><strong>{{ n(summary?.proteinG, 1) }} <small>g</small></strong><p>碳水 {{ n(summary?.carbsG,1) }}g · 脂肪 {{ n(summary?.fatG,1) }}g</p></article>
            <article class="tile"><span>运动时长</span><strong>{{ n(summary?.exerciseMinutes) }} <small>分钟</small></strong><p>消耗估算 {{ n(summary?.exerciseEstimatedKcal) }} kcal</p></article>
            <article class="tile"><span>最近体重</span><strong>{{ n(summary?.latestWeightKg, 1) }} <small>kg</small></strong><p>仅显示所选日期及之前的记录</p></article>
          </section>
          <section class="panel nutrition-panel" aria-label="营养信息完整度">
            <div class="panel-head">
              <h2>营养分析</h2>
              <el-tag size="small" :type="nutritionCoverage.complete ? 'success' : 'info'">
                {{ nutritionCoverage.percent === null ? '暂无餐食数据' : '完整度 ' + nutritionCoverage.percent + '%' }}
              </el-tag>
            </div>
            <p class="muted">仅统计已记录餐次。图片识别与外卖估算不能保证营养数据完整，未知数据不按 0 处理。</p>
            <el-progress v-if="nutritionCoverage.percent !== null"
              :percentage="nutritionCoverage.percent" :show-text="false" :stroke-width="8"
              :aria-label="'营养素完整的食物条目 ' + nutritionCoverage.known + ' / ' + nutritionCoverage.total" />
            <div class="nutrient-grid">
              <div><span>蛋白质</span><strong>{{ n(summary?.proteinG, 1) }} <small>g</small></strong></div>
              <div><span>碳水化合物</span><strong>{{ n(summary?.carbsG, 1) }} <small>g</small></strong></div>
              <div><span>脂肪</span><strong>{{ n(summary?.fatG, 1) }} <small>g</small></strong></div>
            </div>
            <p v-if="nutritionCoverage.total && !nutritionCoverage.complete" class="coverage-tip">
              {{ nutritionCoverage.total - nutritionCoverage.known }} 项食物缺少至少一种营养素，全天宏量营养素暂不能完整汇总。
            </p>
            <p v-else-if="!nutritionCoverage.total" class="muted">添加餐食后显示营养素统计与数据完整度。</p>
          </section>
          <div class="actions">
            <el-button type="primary" @click="activeTab='ai'">📷 拍照 / AI 记录</el-button>
            <el-button @click="openMeal()">记录饮食</el-button>
            <el-button @click="openExercise()">记录运动</el-button>
            <el-button @click="openMetric()">记录体重</el-button>
          </div>
          <section class="panel">
            <div class="panel-head"><h2>{{ date }} 饮食记录</h2><el-button link type="primary" @click="activeTab='meals'">管理餐次</el-button></div>
            <div v-if="!meals.length" class="empty">当天还没有饮食记录，不代表摄入为零。</div>
            <div v-for="meal in meals" :key="meal.id" class="entry">
              <div><b>{{ label(meal.mealType) }}</b><p>{{ meal.items.map(x => x.foodName + ' · ' + portionText(x)).join('、') }}</p></div>
              <strong>{{ n(total(meal)) }} kcal</strong>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>近期摄入趋势</h2><el-select v-model="trendDays" style="width:112px" @change="loadTrend">
              <el-option :value="7" label="近7天"/><el-option :value="14" label="近14天"/>
              <el-option :value="30" label="近30天"/><el-option :value="90" label="近90天"/>
            </el-select></div>
            <p class="muted">未记录不计为 0；不同天数可切换趋势窗口。</p>
            <div class="bars">
              <div v-for="point in trend" :key="point.date" class="bar-column" :title="point.date + ': ' + (point.calories === null ? '未记录' : n(point.calories) + ' kcal')">
                <div class="bar-track"><div v-if="point.calories !== null" class="bar-value" :style="{ height: Math.max(3, Number(point.calories) / maxTrend * 100) + '%' }"></div></div>
                <small>{{ point.date.slice(8) }}</small>
              </div>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane label="饮食" name="meals">
          <section class="panel">
            <div class="panel-head"><h2>餐次明细</h2><el-button type="primary" @click="openMeal()">新增餐次</el-button></div>
            <p class="muted">点击编辑可修改每一种食物的重量。查看历史日期后可复制到今天。</p>
            <div v-if="!meals.length" class="empty">暂无记录</div>
            <div v-for="meal in meals" :key="meal.id" class="entry">
              <div class="grow"><strong>{{ label(meal.mealType) }} · {{ n(total(meal)) }} kcal</strong>
                <p v-for="item in meal.items" :key="item.id">{{ item.foodName }} · {{ portionText(item) }} · {{ n(item.calories) }} kcal
                    <span v-if="item.proteinG == null || item.carbsG == null || item.fatG == null" class="nutrient-unknown"> · 营养素未完整识别</span>
                    <span v-else> · 蛋白质 {{ n(item.proteinG, 1) }}g / 碳水 {{ n(item.carbsG, 1) }}g / 脂肪 {{ n(item.fatG, 1) }}g</span>
                  </p>
                <p v-if="meal.note">{{ meal.note }}</p>
              </div>
              <div class="entry-actions"><el-button link type="primary" @click="openAnalysis(meal)">分析详情</el-button>
                <el-button link type="primary" @click="openAiChange('meal',meal.id)">AI 变更</el-button>
                 <el-button link type="primary" @click="openMeal(meal.mealType,meal)">编辑</el-button>
                <el-button link @click="copyMeal(meal)">复制到今天</el-button>
                <el-button link type="danger" @click="deleteMeal(meal)">删除</el-button></div>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>常吃食物</h2><span><el-button @click="openUsda()">USDA 食品库</el-button> <el-button @click="foodDialog=true">新增自定义食物</el-button></span></div>
            <div v-if="!frequentFoods.length" class="empty">添加餐次后，常吃食物会自动出现在这里。</div>
            <div class="chips"><el-tag v-for="food in frequentFoods" :key="food.id" class="food-chip" @click="openMeal('SNACK'); draftItems=[{foodId:food.id,grams:100,manual:false,customName:'',customCalories:0}]">
              {{ food.name }} · {{ n(food.calories100g) }} kcal/100g
            </el-tag></div>
          </section>
          <PersonalDishManager />
        </el-tab-pane>

        <el-tab-pane label="运动" name="exercise">
          <section class="panel">
            <div class="panel-head"><h2>运动记录</h2><el-button type="primary" @click="openExercise()">添加运动</el-button></div>
            <div v-if="!exercises.length" class="empty">当天还没有运动记录。</div>
            <div v-for="exercise in exercises" :key="exercise.id" class="entry">
              <div class="grow"><strong>{{ exercise.name }} · {{ exercise.durationMinutes }} 分钟</strong>
                <p>消耗估算：{{ n(exercise.estimatedKcal) }} kcal · {{ exercise.note || '无备注' }}</p></div>
              <div class="entry-actions"><el-button link type="primary" @click="openAiChange('exercise',exercise.id)">AI 变更</el-button>
                 <el-button link @click="openExercise(exercise)">编辑</el-button>
                <el-button link type="danger" @click="deleteExercise(exercise.id)">删除</el-button></div>
            </div>
            <p class="muted">运动消耗为可选估算值，不会自动增加每日摄入额度或当作热量缺口。</p>
          </section>
        </el-tab-pane>

        <el-tab-pane label="身体指标" name="metrics">
          <section class="panel">
            <div class="panel-head"><h2>体重趋势 · 近 {{ trendDays }} 天</h2><span class="muted">单位：kg</span></div>
            <div v-if="!weightChart.length" class="empty">尚无这个时间范围内的体重测量。</div>
            <template v-else>
              <svg class="weight-chart" viewBox="0 0 340 130" role="img" aria-label="体重趋势曲线">
                <line x1="8" y1="114" x2="332" y2="114" stroke="currentColor" opacity=".2"/>
                <polyline :points="weightPolyline" fill="none" stroke="#4b91e1" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round"/>
                <circle v-for="(point,idx) in weightChart" :key="idx" :cx="point.x" :cy="point.y"
                  r="4" fill="#4b91e1"><title>{{ point.label }}</title></circle>
              </svg>
              <div class="weight-labels"><span>{{ weightHistory[0]?.date }} · {{ n(weightHistory[0]?.weightKg,1) }}kg</span>
                <span>{{ weightHistory[weightHistory.length-1]?.date }} · {{ n(weightHistory[weightHistory.length-1]?.weightKg,1) }}kg</span></div>
            </template>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>身体数据 · 最近 90 天</h2><el-button type="primary" @click="openMetric()">新增测量</el-button></div>
            <div v-if="!metrics.length" class="empty">尚未记录身体指标。</div>
            <div v-for="metric in metrics" :key="metric.id" class="entry">
              <div class="grow"><strong>{{ metric.measuredOn }} · {{ n(metric.weightKg, 1) }} kg</strong>
                <p>体脂率 {{ n(metric.bodyFatPct, 1) }}% · 腰围 {{ n(metric.waistCm, 1) }}cm</p></div>
              <div class="entry-actions"><el-button link type="primary" @click="openAiChange('metric',metric.id)">AI 变更</el-button>
                 <el-button link @click="openMetric(metric)">编辑</el-button>
                <el-button link type="danger" @click="deleteMetric(metric.id)">删除</el-button></div>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane label="目标设置" name="goals">
          <section class="panel form-panel">
            <h2>目标配置</h2><p class="muted">目标从生效日期开始使用，历史报表保留过去的目标。请依据自身需要设定，不提供默认的减重热量处方。</p>
            <el-form label-position="top">
              <el-form-item label="生效日期"><el-date-picker v-model="goalForm.effectiveFrom" type="date" value-format="YYYY-MM-DD" /></el-form-item>
              <el-form-item label="每日热量目标（kcal）"><el-input-number v-model="goalForm.dailyCalories" :min="0" :max="10000" /></el-form-item>
              <el-form-item label="每日蛋白质目标（g，可选）"><el-input-number v-model="goalForm.dailyProteinG" :min="0" :max="1000" /></el-form-item>
              <el-form-item label="每周运动目标（分钟，可选）"><el-input-number v-model="goalForm.weeklyActivityMinutes" :min="0" :max="10080" /></el-form-item>
              <el-button type="primary" :loading="saving" @click="saveGoal()">保存健康目标</el-button>
            </el-form>
            <h3>历史目标</h3>
            <div v-for="goal in goals" :key="goal.id" class="entry">{{ goal.effectiveFrom }} · {{ n(goal.dailyCalories) }} kcal/天</div>
            <el-divider />
            <h3>个人设置</h3>
            <el-form label-position="top">
              <el-form-item label="身高（cm，可选）"><el-input-number v-model="profile.heightCm" :min="30" :max="300" :precision="1" /></el-form-item>
              <el-form-item label="时区（IANA 名称）"><el-input v-model="profile.timezone" placeholder="Asia/Shanghai" /></el-form-item>
              <el-button :loading="saving" @click="saveProfile()">保存个人设置</el-button>
            </el-form>
          </section>
        </el-tab-pane>
      </el-tabs>


      <el-dialog v-model="analysisDialog" title="餐食识别与营养分析" width="min(96vw,760px)"
        append-to-body destroy-on-close>
        <div class="nutrition-detail" v-loading="analysisLoading">
          <p v-if="analysisError" role="alert" class="coverage-tip">{{ analysisError }}</p>
          <template v-else-if="analysisDetails">
            <p class="muted">仅展示已保存的结构化数据，不保存照片或外卖订单原图。旧餐食可能没有 AI 分析历史。</p>
            <div class="nutrition-coverage-summary">
              <strong>{{ label(analysisDetails.meal.mealType) }} · {{ analysisDetails.meal.mealDate }}</strong>
              <span>蛋白质已知 {{ analysisDetails.nutritionCompleteness.knownProteinCount }} / {{ analysisDetails.nutritionCompleteness.foodCount }} 项</span>
              <span>碳水已知 {{ analysisDetails.nutritionCompleteness.knownCarbsCount }} / {{ analysisDetails.nutritionCompleteness.foodCount }} 项</span>
              <span>脂肪已知 {{ analysisDetails.nutritionCompleteness.knownFatCount }} / {{ analysisDetails.nutritionCompleteness.foodCount }} 项</span>
            </div>
            <h3>最终保存的食物</h3>
            <div v-for="item in analysisDetails.meal.items" :key="item.id" class="nutrition-detail-food">
              <strong>{{ item.foodName }}</strong>
              <p>{{ portionText(item) }} · {{ n(item.calories) }} kcal</p>
              <p>蛋白质 {{ n(item.proteinG,1) }}g · 碳水 {{ n(item.carbsG,1) }}g · 脂肪 {{ n(item.fatG,1) }}g</p>
              <small>{{ nutrientSourceLabel(analysisDetails.nutrients.find(x => x.mealItemId === item.id)?.sourceType ?? '') }}</small>
            </div>
            <h3>AI 原始识别及分析依据</h3>
            <el-collapse v-if="analysisDetails.analyses.length">
              <el-collapse-item v-for="version in analysisDetails.analyses" :key="version.id"
                :name="String(version.id)" :title="'第 ' + version.versionNumber + ' 版 · ' + (version.sourceType === 'IMAGE' ? '图片识别' : '文本识别')">
                <p class="muted">首次识别结果（仅保留脱敏食物业务字段）：</p>
                <p v-for="(item, index) in (version.rawExtraction.items ?? [])" :key="index">
                  {{ item.name }} · {{ item.estimatedGrams == null ? '重量未知' : n(item.estimatedGrams) + 'g（初始识别）' }}
                </p>
                <div v-if="version.rawExtraction.sourceContext" class="nutrition-source-context">
                  <p class="muted">
                    识别类型：
                    {{ version.rawExtraction.sourceContext.kind === 'ORDER_SCREENSHOT' ? '外卖订单' :
                      version.rawExtraction.sourceContext.kind === 'NUTRITION_LABEL' ? '营养标签' : '食物照片' }}
                    <span v-if="version.rawExtraction.sourceContext.merchantName">
                      · {{ version.rawExtraction.sourceContext.merchantName }}
                    </span>
                  </p>
                  <div v-for="(sourceItem, sourceIndex) in (version.rawExtraction.sourceContext.lineItems ?? [])"
                    :key="sourceIndex" class="nutrition-source-row">
                    <strong>{{ sourceItem.name }}</strong>
                    <p v-if="version.rawExtraction.sourceContext.kind === 'ORDER_SCREENSHOT'">
                      订单购买数量：{{ sourceItem.purchasedQuantity ?? '未知' }}
                      <span v-if="sourceItem.portionLabel"> · {{ sourceItem.portionLabel }}</span>
                    </p>
                    <template v-if="version.rawExtraction.sourceContext.kind === 'NUTRITION_LABEL'">
                      <p>包装净含量：{{ sourceItem.packageGrams == null ? '未知' : n(sourceItem.packageGrams) + 'g' }}</p>
                      <p v-if="sourceItem.labelPer100gCandidate">
                        标签候选值（每100g）：
                        热量 {{ n(sourceItem.labelPer100gCandidate.caloriesKcal,1) }} kcal
                        · 蛋白质 {{ n(sourceItem.labelPer100gCandidate.proteinG,1) }}g
                        · 碳水 {{ n(sourceItem.labelPer100gCandidate.carbsG,1) }}g
                        · 脂肪 {{ n(sourceItem.labelPer100gCandidate.fatG,1) }}g
                      </p>
                      <p v-if="sourceItem.labelVerified === false" class="coverage-tip">
                        以下属于首次图片识别候选，未自动计入正式营养数据；如已核对包装可人工确认。
                      </p>
                      <el-button v-if="sourceItem.labelPer100gCandidate"
                        size="small" type="primary" plain
                        @click="beginLabelReview(sourceItem.name, sourceItem.labelPer100gCandidate)">
                        核对标签并计算实际摄入
                      </el-button>
                    </template>
                  </div>
                  <p v-if="version.rawExtraction.sourceContext.kind === 'ORDER_SCREENSHOT'" class="coverage-tip">
                    订单购买数量仅用于溯源；最终摄入量请以用户确认后的重量和餐食记录为准。
                  </p>
                </div>
                <p v-if="version.analysis.method === 'USER_VERIFIED_LABEL' && version.analysis.userInput"
                  class="nutrition-verified">
                  已人工核对：食用 {{ n(version.analysis.userInput.consumedGrams) }}g
                  · 计算热量 {{ n(version.analysis.calculated?.caloriesKcal,2) }} kcal
                  · 蛋白质 {{ n(version.analysis.calculated?.proteinG,2) }}g
                  · 碳水 {{ n(version.analysis.calculated?.carbsG,2) }}g
                  · 脂肪 {{ n(version.analysis.calculated?.fatG,2) }}g
                </p>
                <p v-else class="muted">确认后营养分析（记录当时的估算及食品库数据，后续编辑可能改变当前餐食）：</p>
                <p v-for="(item, index) in (version.analysis.items ?? [])" :key="index">
                  {{ item.foodName }} · {{ item.weightGrams == null ? '重量未知' : n(item.weightGrams) + 'g' }}
                  · {{ n(item.caloriesKcal) }} kcal · {{ nutrientSourceLabel(item.source) }}
                </p>
              </el-collapse-item>
            </el-collapse>
            <div v-else class="empty">这条餐食还没有保存 AI 识别历史，可以继续查看已有的正式营养数据。</div>
            <section v-if="labelReview.mealItemId" class="nutrition-label-review">
              <h3>核实包装营养标签</h3>
              <p class="muted">请对照包装逐项校对每100g的数值，并填写真正食用的克数。
                可修改 AI 识别错误的数字。仅保存核实后的结构化信息，不保存图片。</p>
              <div class="nutrition-review-fields">
                <label>实际吃下（g）
                  <el-input-number v-model="labelReview.consumedGrams" :min="0.1" :max="3000" :precision="2" />
                </label>
                <label>热量（kcal/100g）
                  <el-input-number v-model="labelReview.caloriesPer100g" :min="0.01" :max="900" :precision="2" />
                </label>
                <label>蛋白质（g/100g）
                  <el-input-number v-model="labelReview.proteinPer100g" :min="0" :max="100" :precision="2" />
                </label>
                <label>碳水（g/100g）
                  <el-input-number v-model="labelReview.carbsPer100g" :min="0" :max="100" :precision="2" />
                </label>
                <label>脂肪（g/100g）
                  <el-input-number v-model="labelReview.fatPer100g" :min="0" :max="100" :precision="2" />
                </label>
                <label>膳食纤维（g/100g，可选）
                  <el-input-number v-model="labelReview.fiberPer100g" :min="0" :max="100" :precision="2" />
                </label>
                <label>糖（g/100g，可选）
                  <el-input-number v-model="labelReview.sugarPer100g" :min="0" :max="100" :precision="2" />
                </label>
                <label>钠（mg/100g，可选）
                  <el-input-number v-model="labelReview.sodiumMgPer100g" :min="0" :max="50000" :precision="2" />
                </label>
              </div>
              <p>按当前输入计算，本次热量约 <strong>{{ labelPreview }} kcal</strong></p>
              <el-checkbox v-model="labelReview.userVerified">
                我已对照包装核实每100g数据，并确认实际食用克数；不是直接信任 AI 候选值
              </el-checkbox>
              <div class="entry-actions">
                <el-button type="primary" :loading="labelSaving" :disabled="!labelReview.userVerified"
                  @click="submitLabelReview">保存人工核实营养</el-button>
                <el-button :disabled="labelSaving" @click="labelReview.mealItemId=0">取消</el-button>
              </div>
            </section>
          </template>
        </div>
        <template #footer><el-button @click="analysisDialog=false">关闭</el-button></template>
      </el-dialog>
      <el-dialog v-model="aiChangeVisible" title="AI 修改 / 删除健康记录" width="min(96vw,680px)" destroy-on-close append-to-body>
        <WellnessAiChange :key="aiChangeKey" :initial-kind="aiChangeKind" :initial-id="aiChangeRecord"
          :initial-date="date" @changed="savedAiChange" />
      </el-dialog>
      <el-dialog v-model="mealDialog" :title="editingMeal===null?'新增餐次':'编辑餐次'" width="min(96vw,640px)" destroy-on-close>
        <el-form label-position="top">
          <div class="form-row">
            <el-form-item label="日期"><el-date-picker v-model="mealForm.mealDate" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="餐次"><el-select v-model="mealForm.mealType"><el-option v-for="kind in mealKinds" :key="kind" :label="label(kind)" :value="kind" /></el-select></el-form-item>
          </div>
          <div v-for="(item,idx) in draftItems" :key="idx" class="food-row">
            <el-checkbox v-model="item.manual">本次自定义热量</el-checkbox>
            <template v-if="item.manual">
              <el-input v-model="item.customName" maxlength="120" placeholder="食物名称，例如红油馄饨" />
              <el-input-number v-model="item.customCalories" :min="0.01" :max="20000" :precision="2" />
              <span class="muted">本次 kcal</span>
              <el-input-number v-model="item.grams" :min="0" :max="3000" :precision="1" />
              <span class="muted">g，可填 0</span>
            </template>
            <template v-else>
              <el-select v-model="item.foodId" filterable remote :remote-method="searchFoods" placeholder="搜索食物">
                <el-option v-for="food in foods" :key="food.id" :value="food.id" :label="food.name + ' · ' + n(food.calories100g) + ' kcal/100g'" />
              </el-select>
              <el-input-number v-model="item.grams" :min="0.1" :max="3000" :precision="1" />
              <span class="muted">g</span>
            </template>
            <el-button link type="danger" @click="draftItems.splice(idx,1)">移除</el-button>
          </div>
          <el-button @click="addItem()">+ 添加食物</el-button>
          <el-button link type="primary" @click="foodDialog=true">没有找到？创建食物</el-button>
          <el-form-item label="备注"><el-input v-model="mealForm.note" maxlength="500" /></el-form-item>
          <p class="meal-total">本餐估算：{{ n(mealPreview) }} kcal</p>
          <p class="muted">自定义热量只保存在本餐次明细，不进入食品参考库；不确定重量可填 0，未知蛋白质、碳水和脂肪不会显示为 0。</p>
        </el-form>
        <template #footer><el-button @click="mealDialog=false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveMeal()">保存餐次</el-button></template>
      </el-dialog>

      <el-dialog v-model="usdaDialog" title="USDA 食品搜索（公开 CC0 数据）" width="min(96vw,650px)" append-to-body>
        <p class="muted">本地食物可离线使用；外部查询仅在服务器配置 USDA API Key 后启用。常见单一食材可以直接输入中文搜索（自动映射为英文）；复杂中式菜肴建议先自建条目或使用准确的包装营养标签。营养值按每100g参考。</p>
        <p v-if="!usdaConfigured" class="muted">尚未配置 MATRIX_PRP_USDA_API_KEY，联系管理员配置后即可搜索。</p>
        <div class="form-row">
          <el-input v-model="usdaQuery" placeholder="例：chicken breast, yogurt, rice" maxlength="80"
            :disabled="!usdaConfigured" @keyup.enter="searchUsda" />
          <el-button type="primary" :loading="usdaSearching" :disabled="!usdaConfigured" @click="searchUsda">搜索</el-button>
        </div>
        <div v-for="candidate in usdaResults" :key="candidate.fdcId" class="entry">
          <div class="grow">
            <strong>{{ candidate.name }}</strong>
            <p>{{ n(candidate.calories100g) }} kcal · 蛋白质 {{ n(candidate.protein100g,1) }}g · 碳水 {{ n(candidate.carbs100g,1) }}g · 脂肪 {{ n(candidate.fat100g,1) }}g / 100g</p>
            <small class="muted">{{ candidate.source }}</small>
          </div>
          <el-button :loading="importingUsda === candidate.fdcId" @click="importUsdaFood(candidate)">导入</el-button>
        </div>
        <p class="muted">来源：USDA FoodData Central (CC0)。不同状态、品牌和烹饪方式有较大差异，记录前请核实。</p>
      </el-dialog>
      <el-dialog v-model="foodDialog" title="新增自定义食物" width="min(96vw,520px)" append-to-body>
        <el-form label-position="top">
          <el-form-item label="食物名称"><el-input v-model="foodForm.name" maxlength="120" /></el-form-item>
          <el-form-item label="状态"><el-select v-model="foodForm.preparation">
            <el-option label="未指定" value="unspecified"/><el-option label="生" value="raw"/><el-option label="熟" value="cooked"/>
          </el-select></el-form-item>
          <p class="muted">以下数值均按每 100g 可食部填写</p>
          <div class="form-row">
            <el-form-item label="热量 kcal"><el-input-number v-model="foodForm.calories100g" :min="0" :max="900" /></el-form-item>
            <el-form-item label="蛋白质 g"><el-input-number v-model="foodForm.protein100g" :min="0" :max="100" /></el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="碳水 g"><el-input-number v-model="foodForm.carbs100g" :min="0" :max="100" /></el-form-item>
            <el-form-item label="脂肪 g"><el-input-number v-model="foodForm.fat100g" :min="0" :max="100" /></el-form-item>
          </div>
          <el-form-item label="数据来源/备注"><el-input v-model="foodForm.sourceNote" maxlength="255" placeholder="如包装标签、手动估计"/></el-form-item>
        </el-form>
        <template #footer><el-button @click="foodDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveFood()">保存食物</el-button></template>
      </el-dialog>

      <el-dialog v-model="exerciseDialog" :title="editExerciseId===null?'添加运动':'编辑运动'" width="min(96vw,500px)">
        <el-form label-position="top">
          <el-form-item label="运动日期"><el-date-picker v-model="exerciseForm.performedOn" type="date" value-format="YYYY-MM-DD"/></el-form-item>
          <el-form-item label="项目名称"><el-input v-model="exerciseForm.name" placeholder="步行、跑步、力量训练等"/></el-form-item>
          <el-form-item label="运动时长（分钟）"><el-input-number v-model="exerciseForm.durationMinutes" :min="1" :max="1440" /></el-form-item>
          <el-form-item label="估算消耗 kcal（选填）"><el-input-number v-model="exerciseForm.estimatedKcal" :min="0" :max="20000"/></el-form-item>
          <el-form-item label="备注"><el-input v-model="exerciseForm.note" maxlength="500" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="exerciseDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveExercise()">保存</el-button></template>
      </el-dialog>

      <el-dialog v-model="metricDialog" :title="editMetricId===null?'记录身体指标':'编辑身体指标'" width="min(96vw,500px)">
        <el-form label-position="top">
          <el-form-item label="测量日期"><el-date-picker v-model="metricForm.measuredOn" type="date" value-format="YYYY-MM-DD"/></el-form-item>
          <el-form-item label="体重（kg）"><el-input-number v-model="metricForm.weightKg" :min="0" :max="500" :precision="2"/></el-form-item>
          <el-form-item label="体脂率（% ，选填）"><el-input-number v-model="metricForm.bodyFatPct" :min="0" :max="100" :precision="2"/></el-form-item>
          <el-form-item label="腰围（cm，选填）"><el-input-number v-model="metricForm.waistCm" :min="0" :max="300" :precision="1"/></el-form-item>
        </el-form>
        <template #footer><el-button @click="metricDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveMetric()">保存</el-button></template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<style scoped>
.wellness-page{max-width:1280px;margin:0 auto;padding:22px 26px 48px}
.head,.panel-head,.entry,.actions{display:flex;align-items:center;justify-content:space-between;gap:14px}
.head{margin-bottom:16px}.head h1{margin:0;font-size:25px}.head p,.muted,.tile p,.entry p{color:var(--el-text-color-secondary);font-size:13px}
.wellness-tabs{margin-top:8px}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.tile,.panel{border:1px solid var(--el-border-color-light);border-radius:13px;background:var(--el-bg-color);padding:18px}
.tile{min-height:136px;display:flex;flex-direction:column;gap:9px}.tile>span{font-size:13px;color:var(--el-text-color-secondary)}
.tile strong{font-size:24px;font-weight:750}.tile strong small{font-size:14px;font-weight:400}.tile p{margin:0}.tile.hero{background:var(--el-color-primary-light-9)}
.actions{justify-content:flex-start;margin:18px 0;flex-wrap:wrap}.panel{margin:14px 0}.panel h2{font-size:17px;margin:0 0 12px}.panel h3{font-size:15px;margin:20px 0}
.entry{border-top:1px solid var(--el-border-color-lighter);padding:13px 0}.entry p{margin:4px 0;line-height:1.5}.grow{flex:1;min-width:0}.entry-actions{display:flex;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.empty{padding:24px;text-align:center;color:var(--el-text-color-secondary);background:var(--el-fill-color-light);border-radius:10px}
.bars{height:175px;display:flex;align-items:end;gap:7px;padding-top:12px}.bar-column{height:100%;min-width:0;flex:1;display:flex;flex-direction:column;align-items:center;gap:6px}
.bar-track{width:100%;height:148px;display:flex;align-items:end;background:var(--el-fill-color-lighter);border-radius:5px;overflow:hidden}
.bar-value{background:var(--el-color-primary);width:100%;border-radius:4px 4px 0 0}.bar-column small{color:var(--el-text-color-secondary)}
.form-panel{max-width:640px}.form-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.food-row{display:flex;align-items:center;gap:9px;margin-bottom:10px}.food-row .el-select{flex:1;min-width:0}.food-row .el-input-number{width:140px}
.meal-total{font-size:18px;font-weight:700;margin-top:18px}
.nutrition-panel{background:var(--el-bg-color-page);border-radius:16px}
.nutrition-detail{display:flex;flex-direction:column;gap:10px;min-height:120px;overflow-wrap:anywhere}
.nutrition-detail h3{margin:12px 0 2px;font-size:15px}
.nutrition-detail .muted{margin:0}
.nutrition-source-context{border:1px dashed var(--el-border-color);border-radius:12px;padding:12px;background:var(--el-fill-color-light)}
.nutrition-source-row{padding:7px 0;border-top:1px solid var(--el-border-color-lighter)}
.nutrition-source-row p{font-size:13px;color:var(--el-text-color-secondary);margin:5px 0}
.nutrition-label-review{padding:14px;border:1px solid var(--el-border-color);border-radius:12px;background:var(--el-fill-color-light);display:grid;gap:12px}
.nutrition-review-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px}
.nutrition-review-fields label{display:grid;gap:6px;font-size:13px}
.nutrition-review-fields .el-input-number{width:100%}
.nutrition-verified{font-size:13px;color:var(--el-color-success)}
.nutrition-detail-food{padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:12px}
.nutrition-detail-food p{margin:5px 0;color:var(--el-text-color-secondary);font-size:13px}
.nutrition-detail-food small{color:var(--el-color-info)}
.nutrition-coverage-summary{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-radius:12px;background:var(--el-fill-color-light);padding:12px}
.nutrition-coverage-summary span{font-size:12px;color:var(--el-text-color-secondary)}
.nutrition-panel .panel-head h2{margin:0}
.nutrient-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}
.nutrient-grid>div{min-width:0;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:var(--el-bg-color);display:flex;flex-direction:column;gap:8px}
.nutrient-grid span{font-size:12px;color:var(--el-text-color-secondary)}
.nutrient-grid strong{font-size:20px;line-height:1.25;overflow-wrap:anywhere}
.nutrient-grid strong small{font-size:12px;font-weight:400}
.coverage-tip{margin:12px 0 0;font-size:12px;color:var(--el-color-warning-dark-2)}
.nutrient-unknown{color:var(--el-text-color-secondary);font-size:12px}
.weight-chart{width:100%;height:170px;background:var(--el-fill-color-lighter);border-radius:8px}
.weight-labels{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--el-text-color-secondary);flex-wrap:wrap;margin-top:7px}.chips{display:flex;flex-wrap:wrap;gap:8px}.food-chip{cursor:pointer}
@media(max-width:900px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.wellness-page{padding:14px 12px 36px}.head{align-items:start;flex-wrap:wrap}
.head h1{font-size:21px}.metric-grid{gap:8px}.tile{padding:12px;min-height:118px}.tile strong{font-size:20px}
.panel{padding:14px}.entry{align-items:start;flex-wrap:wrap}.entry-actions{width:100%;justify-content:flex-start}
.food-row{flex-wrap:wrap}.food-row .el-select{flex-basis:100%}.form-row{grid-template-columns:1fr}
.nutrient-grid{grid-template-columns:1fr}.nutrient-grid>div{gap:4px;padding:10px}
.bars{gap:3px}.bar-track{height:125px}}
</style>
