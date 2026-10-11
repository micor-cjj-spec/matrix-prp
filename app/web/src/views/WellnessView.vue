<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  wellnessApi, type Food, type Meal, type MealInput, type Exercise, type ExerciseInput,
  type BodyMetric, type BodyMetricInput, type DailySummary, type TrendPoint,
  type Goal, type Profile,
} from '@/api/wellness'

const localDate = () => {
  const d = new Date()
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
}
const today = localDate()
const date = ref(today)
const activeTab = ref('today')
const loading = ref(false)
const saving = ref(false)
const summary = ref<DailySummary | null>(null)
const meals = ref<Meal[]>([])
const exercises = ref<Exercise[]>([])
const metrics = ref<BodyMetric[]>([])
const goals = ref<Goal[]>([])
const trend = ref<TrendPoint[]>([])
const foods = ref<Food[]>([])
const frequentFoods = ref<Food[]>([])
const profile = reactive<Profile>({ heightCm: null, timezone: 'Asia/Shanghai' })
const selectedGoal = computed(() => summary.value?.goal)
const calories = computed(() => summary.value?.calories === null || summary.value?.calories === undefined ? null : Number(summary.value.calories))
const dailyGoal = computed(() => Number(selectedGoal.value?.dailyCalories || 0))
const pct = computed(() => dailyGoal.value && calories.value !== null ? Math.min(100, Math.round(calories.value / dailyGoal.value * 100)) : 0)
const maxTrend = computed(() => Math.max(1, ...trend.value.map(x => Number(x.calories || 0))))
const label = (kind: string) => ({ BREAKFAST: '早餐', LUNCH: '午餐', DINNER: '晚餐', SNACK: '加餐' }[kind] || kind)
const n = (x: string | number | null | undefined, digits = 0) => x == null ? '—' : Number(x).toFixed(digits)
const total = (meal: Meal) => meal.items.reduce((sum, x) => sum + Number(x.calories), 0)
const mealKinds = ['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK']

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
type DraftItem = { foodId: number | null; grams: number }
const draftItems = ref<DraftItem[]>([])
function openMeal(kind = 'BREAKFAST', meal?: Meal) {
  editingMeal.value = meal?.id ?? null
  mealForm.mealDate = meal?.mealDate ?? date.value
  mealForm.mealType = meal?.mealType ?? kind
  mealForm.note = meal?.note || ''
  draftItems.value = meal ? meal.items.map(i => ({ foodId: i.foodId, grams: Number(i.grams) })) : [{ foodId: null, grams: 100 }]
  mealDialog.value = true
}
function addItem(foodId: number | null = null) { draftItems.value.push({ foodId, grams: 100 }) }
const mealPreview = computed(() => draftItems.value.reduce((sum, item) => {
  const food = foods.value.find(f => f.id === item.foodId)
  return sum + (food ? Number(food.calories100g) * Number(item.grams || 0) / 100 : 0)
}, 0))
async function searchFoods(q: string) {
  try {
    const found = await wellnessApi.foods(q)
    // Preserve selected entries while searching, so options don't disappear.
    foods.value = [...new Map([...foods.value, ...found].map(x => [x.id, x])).values()]
  } catch { ElMessage.error('食物搜索失败') }
}
async function saveMeal() {
  const items = draftItems.value.filter((x): x is { foodId: number; grams: number } => x.foodId !== null && x.grams > 0)
  if (!items.length || items.length !== draftItems.value.length) { ElMessage.warning('请完整选择食物和有效重量'); return }
  saving.value = true
  try {
    const payload: MealInput = { mealDate: mealForm.mealDate, mealType: mealForm.mealType,
      note: mealForm.note, items, idempotencyKey: editingMeal.value ? undefined : crypto.randomUUID() }
    if (editingMeal.value !== null) await wellnessApi.updateMeal(editingMeal.value, payload)
    else await wellnessApi.addMeal(payload)
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
async function loadTrend() { trend.value = await wellnessApi.trends(14) }

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
      <el-tabs v-model="activeTab" class="wellness-tabs" @tab-change="tab => { if (tab === 'goals') loadGoal() }">
        <el-tab-pane label="今日概览" name="today">
          <section class="metric-grid">
            <article class="tile hero">
              <span>今日摄入</span>
              <strong>{{ calories === null ? '未记录' : n(calories) + ' kcal' }}</strong>
              <p v-if="dailyGoal">目标 {{ n(dailyGoal) }} kcal · {{ pct }}%</p>
              <p v-else>尚未设置每日热量目标</p>
              <el-progress v-if="dailyGoal && calories !== null" :percentage="pct" :show-text="false" />
            </article>
            <article class="tile"><span>蛋白质</span><strong>{{ n(summary?.proteinG, 1) }} <small>g</small></strong><p>今日摄入合计</p></article>
            <article class="tile"><span>运动时长</span><strong>{{ n(summary?.exerciseMinutes) }} <small>分钟</small></strong><p>消耗估算 {{ n(summary?.exerciseEstimatedKcal) }} kcal</p></article>
            <article class="tile"><span>最近体重</span><strong>{{ n(summary?.latestWeightKg, 1) }} <small>kg</small></strong><p>仅显示所选日期及之前的记录</p></article>
          </section>
          <div class="actions">
            <el-button type="primary" @click="openMeal()">记录饮食</el-button>
            <el-button @click="openExercise()">记录运动</el-button>
            <el-button @click="openMetric()">记录体重</el-button>
          </div>
          <section class="panel">
            <div class="panel-head"><h2>{{ date }} 饮食记录</h2><el-button link type="primary" @click="activeTab='meals'">管理餐次</el-button></div>
            <div v-if="!meals.length" class="empty">当天还没有饮食记录，不代表摄入为零。</div>
            <div v-for="meal in meals" :key="meal.id" class="entry">
              <div><b>{{ label(meal.mealType) }}</b><p>{{ meal.items.map(x => x.foodName + ' ' + n(x.grams) + 'g').join('、') }}</p></div>
              <strong>{{ n(total(meal)) }} kcal</strong>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>近 14 天摄入趋势</h2><span class="muted">未记录不计为 0</span></div>
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
                <p v-for="item in meal.items" :key="item.id">{{ item.foodName }} · {{ n(item.grams) }}g · {{ n(item.calories) }} kcal</p>
                <p v-if="meal.note">{{ meal.note }}</p>
              </div>
              <div class="entry-actions"><el-button link type="primary" @click="openMeal(meal.mealType,meal)">编辑</el-button>
                <el-button link @click="copyMeal(meal)">复制到今天</el-button>
                <el-button link type="danger" @click="deleteMeal(meal)">删除</el-button></div>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>常吃食物</h2><el-button @click="foodDialog=true">新增自定义食物</el-button></div>
            <div v-if="!frequentFoods.length" class="empty">添加餐次后，常吃食物会自动出现在这里。</div>
            <div class="chips"><el-tag v-for="food in frequentFoods" :key="food.id" class="food-chip" @click="openMeal('SNACK'); draftItems=[{foodId:food.id,grams:100}]">
              {{ food.name }} · {{ n(food.calories100g) }} kcal/100g
            </el-tag></div>
          </section>
        </el-tab-pane>

        <el-tab-pane label="运动" name="exercise">
          <section class="panel">
            <div class="panel-head"><h2>运动记录</h2><el-button type="primary" @click="openExercise()">添加运动</el-button></div>
            <div v-if="!exercises.length" class="empty">当天还没有运动记录。</div>
            <div v-for="exercise in exercises" :key="exercise.id" class="entry">
              <div class="grow"><strong>{{ exercise.name }} · {{ exercise.durationMinutes }} 分钟</strong>
                <p>消耗估算：{{ n(exercise.estimatedKcal) }} kcal · {{ exercise.note || '无备注' }}</p></div>
              <div class="entry-actions"><el-button link @click="openExercise(exercise)">编辑</el-button>
                <el-button link type="danger" @click="deleteExercise(exercise.id)">删除</el-button></div>
            </div>
            <p class="muted">运动消耗为可选估算值，不会自动增加每日摄入额度或当作热量缺口。</p>
          </section>
        </el-tab-pane>

        <el-tab-pane label="身体指标" name="metrics">
          <section class="panel">
            <div class="panel-head"><h2>身体数据 · 最近 90 天</h2><el-button type="primary" @click="openMetric()">新增测量</el-button></div>
            <div v-if="!metrics.length" class="empty">尚未记录身体指标。</div>
            <div v-for="metric in metrics" :key="metric.id" class="entry">
              <div class="grow"><strong>{{ metric.measuredOn }} · {{ n(metric.weightKg, 1) }} kg</strong>
                <p>体脂率 {{ n(metric.bodyFatPct, 1) }}% · 腰围 {{ n(metric.waistCm, 1) }}cm</p></div>
              <div class="entry-actions"><el-button link @click="openMetric(metric)">编辑</el-button>
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

      <el-dialog v-model="mealDialog" :title="editingMeal===null?'新增餐次':'编辑餐次'" width="min(96vw,640px)" destroy-on-close>
        <el-form label-position="top">
          <div class="form-row">
            <el-form-item label="日期"><el-date-picker v-model="mealForm.mealDate" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="餐次"><el-select v-model="mealForm.mealType"><el-option v-for="kind in mealKinds" :key="kind" :label="label(kind)" :value="kind" /></el-select></el-form-item>
          </div>
          <div v-for="(item,idx) in draftItems" :key="idx" class="food-row">
            <el-select v-model="item.foodId" filterable remote :remote-method="searchFoods" placeholder="搜索食物">
              <el-option v-for="food in foods" :key="food.id" :value="food.id" :label="food.name + ' · ' + n(food.calories100g) + ' kcal/100g'" />
            </el-select>
            <el-input-number v-model="item.grams" :min="1" :max="10000" :precision="1" /><span class="muted">g</span>
            <el-button link type="danger" @click="draftItems.splice(idx,1)">移除</el-button>
          </div>
          <el-button @click="addItem()">+ 添加食物</el-button>
          <el-button link type="primary" @click="foodDialog=true">没有找到？创建食物</el-button>
          <el-form-item label="备注"><el-input v-model="mealForm.note" maxlength="500" /></el-form-item>
          <p class="meal-total">本餐估算：{{ n(mealPreview) }} kcal</p>
          <p class="muted">示例食物营养值为参考数据。烹饪油、配料、品牌营养标签请按实际情况确认。</p>
        </el-form>
        <template #footer><el-button @click="mealDialog=false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveMeal()">保存餐次</el-button></template>
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
.meal-total{font-size:18px;font-weight:700;margin-top:18px}.chips{display:flex;flex-wrap:wrap;gap:8px}.food-chip{cursor:pointer}
@media(max-width:900px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.wellness-page{padding:14px 12px 36px}.head{align-items:start;flex-wrap:wrap}
.head h1{font-size:21px}.metric-grid{gap:8px}.tile{padding:12px;min-height:118px}.tile strong{font-size:20px}
.panel{padding:14px}.entry{align-items:start;flex-wrap:wrap}.entry-actions{width:100%;justify-content:flex-start}
.food-row{flex-wrap:wrap}.food-row .el-select{flex-basis:100%}.form-row{grid-template-columns:1fr}
.bars{gap:3px}.bar-track{height:125px}}
</style>
