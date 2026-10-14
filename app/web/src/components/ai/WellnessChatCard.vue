<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { apiClient, type ApiResponse } from '@/api/client'
import { wellnessApi, type Food, type UsdaCandidate, type DishTemplate } from '@/api/wellness'
import { cloneJson } from '@/utils/cloneJson'

type Item = {
  foodId: number; name: string; grams: number; calories: number | null
  mode?: 'catalog' | 'manual' | 'template'; manualCalories?: number | null
  templateId?: number | null; saveToFavorites?: boolean; merchantName?: string
  portionLabel?: string; portionCount?: number | null
  sourceType?: 'USER_ESTIMATE' | 'AI_ESTIMATE' | 'LABEL' | 'OTHER'
  sourceNote?: string
}
type MultiMeal = { mealType: string; totalCalories: number; items: Item[]; note?: string }
type DraftValues = {
  date: string; mealType?: string; items?: Item[]; note?: string
  sourceMealId?: number; sourceDate?: string; targets?: string[]
  meals?: MultiMeal[]; alreadyExistingTypes?: string[]
}
type Draft = { draftId: string; action: string; description: string; modelUsed: string; expiresAt: string; values: DraftValues }
type DraftView = { draft: Draft; status: 'PENDING' | 'CONSUMED' | 'EXPIRED' }
type Outcome = { route: string }
const props = defineProps<{ draftId: string }>()
const emit = defineEmits<{ saved: [] }>()
const loading = ref(true)
const saving = ref(false)
const saveOutcomeUnknown = ref(false)
const checkingSaveOutcome = ref(false)
const error = ref('')
// Global API requests can remain at 8s; only explicit draft writes need extra time.
const WRITE_TIMEOUT_MS = 45000
const STATUS_TIMEOUT_MS = 15000
const draft = ref<Draft | null>(null)
const status = ref('PENDING')
const values = ref<DraftValues>({ date: '' })
const matches = reactive<Record<number, UsdaCandidate[]>>({})
const chosen = reactive<Record<number, number>>({})
const resolving = ref(false)
const sourceAvailable = ref(false)
const foodLoadingErrors = reactive<Record<number, string>>({})
const originalCalories = reactive<Record<number, { grams: number; kcal: number }>>({})
const calorieDensity = reactive<Record<number, number>>({})
const suggestedDishes = reactive<Record<number, DishTemplate[]>>({})
const allPersonalDishes = ref<DishTemplate[]>([])
function usePersonalDish(index: number, templateId: number) {
  const dish = allPersonalDishes.value.find(x => x.id === Number(templateId))
  const item = items.value[index]
  if (!dish || !item) return
  item.mode = 'template'
  item.templateId = dish.id
  item.foodId = 0
  item.name = dish.dishName
  item.grams = 0
  item.manualCalories = Number(dish.caloriesPerServing)
  item.merchantName = dish.merchantName
  item.portionLabel = dish.portionLabel
  item.portionCount = dish.portionCount
  item.sourceType = dish.sourceType
  item.sourceNote = dish.sourceNote || ''
  item.saveToFavorites = false
}
function normalizeDish(text: string) { return text.replace(/[\\s（）()]/g, '').toLowerCase() }
async function loadDishSuggestions() {
  try {
    allPersonalDishes.value = await wellnessApi.dishes()
    items.value.forEach((item, i) => {
      const name = normalizeDish(item.name)
      suggestedDishes[i] = allPersonalDishes.value.filter(d => {
        const dishName = normalizeDish(d.dishName)
        return name.length >= 2 && (name.includes(dishName) || dishName.includes(name))
      }).slice(0, 8)
    })
  } catch {
    allPersonalDishes.value = []
  }
}

const types: Record<string, string> = { BREAKFAST: '早餐', LUNCH: '午餐', DINNER: '晚餐', SNACK: '加餐' }
const items = computed(() => values.value.items ?? [])
function isManual(item: Item) { return item.mode === 'manual' || item.mode === 'template' }
function validManualCalories(item: Item) {
  const n = Number(item.manualCalories)
  return (item.mode !== 'template' || !!item.templateId) &&
    item.manualCalories !== null && item.manualCalories !== undefined &&
    Number.isFinite(n) && n > 0 && n <= 20000 && Math.abs(n * 100 - Math.round(n * 100)) < 1e-6 &&
    !!item.name?.trim() && item.name.trim().length <= 120 &&
    Number.isFinite(Number(item.grams)) && Number(item.grams) >= 0 && Number(item.grams) <= 3000
}
const canConfirm = computed(() => !loading.value && !saving.value && !saveOutcomeUnknown.value &&
  status.value === 'PENDING' && draft.value?.action === 'meal.create' &&
  items.value.length > 0 && items.value.every((item, i) =>
    isManual(item) ? validManualCalories(item) :
      !resolving.value && Number(item.grams) > 0 && (Number(item.foodId) > 0
        ? Number.isFinite(calorieDensity[i])
        : Boolean(selectedCandidate(i)))))
const total = computed(() => items.value.reduce((sum, item, i) => sum + portion(item, i), 0))
const batchCalories = computed(() => items.value.reduce((sum, item) => sum + (Number(item.calories) || 0), 0))
const multiMeals = computed(() => values.value.meals ?? [])
const multiCalories = computed(() => multiMeals.value.reduce((sum, meal) => sum + Number(meal.totalCalories || 0), 0))
const canConfirmMulti = computed(() => !loading.value && !saving.value && !saveOutcomeUnknown.value &&
  status.value === 'PENDING' && draft.value?.action === 'meal.create_batch' &&
  multiMeals.value.length > 0 && multiMeals.value.length <= 4 &&
  multiMeals.value.every(meal => meal.items.length > 0 && meal.items.length <= 8 &&
    meal.items.every(item => Number(item.manualCalories) > 0)))
const canConfirmBatch = computed(() => !loading.value && !saving.value && !saveOutcomeUnknown.value &&
  status.value === 'PENDING' && draft.value?.action === 'meal.copy_batch' &&
  (values.value.targets?.length ?? 0) >= 1 &&
  (values.value.targets?.length ?? 0) <= 7 &&
  !!values.value.sourceMealId && !!values.value.sourceDate &&
  items.value.length > 0 && items.value.every(item => item.foodId > 0 && item.grams > 0 ||
    item.foodId === 0 && (item.mode === 'manual' || item.manualCalories != null) &&
      Number(item.calories) > 0 && Number(item.grams) >= 0))
function selectedCandidate(index: number) {
  return matches[index]?.find(candidate => candidate.fdcId === chosen[index])
}
function portion(item: Item, index: number) {
  if (isManual(item)) return validManualCalories(item) ? Number(item.manualCalories) : 0
  const grams = Number(item.grams)
  if (!Number.isFinite(grams) || grams <= 0) return 0
  if (Number(item.foodId) > 0) {
    const density = calorieDensity[index]
    return Number.isFinite(density) ? density * grams / 100 : 0
  }
  const candidate = selectedCandidate(index)
  return candidate ? Number(candidate.calories100g) * grams / 100 : 0
}
async function searchMissingFoods() {
  const unresolved = items.value.map((item, i) => ({ item, i }))
    .filter(({ item }) => !item.foodId && !isManual(item))
  if (!unresolved.length) return
  resolving.value = true
  try {
    sourceAvailable.value = (await wellnessApi.usdaStatus()).configured
    for (const { item, i } of unresolved) {
      // A single trusted source; no model-supplied URLs and no fabricated nutrition.
      if (sourceAvailable.value) {
        try {
          matches[i] = (await wellnessApi.searchUsda(item.name)).slice(0, 5)
          if (matches[i].length) chosen[i] = matches[i][0]!.fdcId
          else foodLoadingErrors[i] = '可靠营养库未找到此食物，请补充品牌或烹饪方式'
        } catch {
          foodLoadingErrors[i] = '食品在线检索失败，不能凭 AI 猜测保存'
        }
      } else foodLoadingErrors[i] = '服务器尚未配置 USDA 食品查询，请联系管理员启用'
    }
  } finally { resolving.value = false }
}
async function load() {
  if (!/^[0-9a-fA-F-]{36}$/.test(props.draftId)) { error.value = '无效的健康草稿'; loading.value = false; return }
  try {
    const response = await apiClient.get<ApiResponse<DraftView>>('/wellness/ai/drafts/' + props.draftId)
    draft.value = response.data.data.draft
    status.value = response.data.data.status
    values.value = cloneJson(response.data.data.draft.values)
    values.value.items?.forEach((item, i) => {
      item.mode = item.mode === 'manual' || item.mode === 'template' ? item.mode : 'catalog'
      if (item.foodId && Number(item.grams) > 0 && item.calories != null)
        originalCalories[i] = { grams: Number(item.grams), kcal: Number(item.calories) }
    })
    if (status.value === 'PENDING' && draft.value.action === 'meal.create') {
      await Promise.all(values.value.items?.map(async (item, i) => {
        if (!item.foodId) return
        try {
          const food = await wellnessApi.food(item.foodId)
          calorieDensity[i] = Number(food.calories100g)
        } catch {
          const previous = originalCalories[i]
          if (previous?.grams > 0) calorieDensity[i] = previous.kcal * 100 / previous.grams
          else foodLoadingErrors[i] = '食品热量读取失败，请重新打开记录卡片'
        }
      }) ?? [])
    }
    if (status.value === 'PENDING' && draft.value.action === 'meal.create') {
      await loadDishSuggestions()
      await searchMissingFoods()
    }
  } catch { error.value = '读取记录草稿失败或无权访问'; }
  finally { loading.value = false }
}
function markSaved() {
  status.value = 'CONSUMED'
  saveOutcomeUnknown.value = false
  error.value = ''
  emit('saved')
}

// A timed-out POST may still have committed on the server. Never assume failure
// or automatically re-submit a financial/health write without checking the draft.
async function refreshSaveOutcome(): Promise<'CONSUMED' | 'PENDING' | 'EXPIRED' | null> {
  if (!draft.value) return null
  try {
    const result = await apiClient.get<ApiResponse<DraftView>>(
      '/wellness/ai/drafts/' + draft.value.draftId, { timeout: STATUS_TIMEOUT_MS })
    const freshStatus = result.data.data.status
    if (freshStatus === 'CONSUMED') markSaved()
    else if (freshStatus === 'EXPIRED') status.value = 'EXPIRED'
    return freshStatus
  } catch { return null }
}
async function handleWriteError(e: unknown) {
  const err = e as { response?: { status?: number; data?: { message?: string } }; message?: string }
  // Any missing response, gateway timeout or server-side 5xx may have committed
  // even though the response was lost. Do not enable a blind retry on HTTP 504.
  const responseStatus = err.response?.status
  const ambiguous = !err.response || responseStatus === 408 || (responseStatus != null && responseStatus >= 500)
  if (ambiguous || responseStatus === 409) {
    const result = await refreshSaveOutcome()
    if (result === 'CONSUMED') return
    if (ambiguous) {
      saveOutcomeUnknown.value = true
      error.value = '保存请求超时或服务器响应异常，结果尚不确定。请先点击「检查保存状态」，不要反复提交。'
      return
    }
  }
  error.value = err.response?.data?.message || err.message || '保存失败，请核对信息后重试'
}
async function recheckSaveOutcome() {
  if (checkingSaveOutcome.value || saving.value) return
  checkingSaveOutcome.value = true
  try {
    const result = await refreshSaveOutcome()
    if (result === 'PENDING') {
      saveOutcomeUnknown.value = false
      error.value = '目前草稿仍待确认。请先核对健康中心该日期的记录；如尚未保存，可再次确认。'
    } else if (result === 'EXPIRED') {
      saveOutcomeUnknown.value = false
      error.value = '草稿已过期，请重新创建记录。'
    } else if (!result) {
      error.value = '暂时无法核实服务器是否保存成功，请稍后再检查；不要重复提交。'
    }
  } finally { checkingSaveOutcome.value = false }
}
async function confirm() {
  if (!canConfirm.value || !draft.value) return
  saving.value = true
  error.value = ''
  try {
    const corrected = cloneJson(values.value)
    const newItems: Item[] = []
    for (let i = 0; i < items.value.length; i++) {
      const item = items.value[i]!
      if (isManual(item)) {
        if (!validManualCalories(item)) throw new Error('请输入本次实际估算的食物名称和总热量')
        // Server owns template lookup; custom snapshots never use the standard food catalog.
        newItems.push({ ...item, foodId: 0, grams: Number(item.grams) || 0,
          mode: item.mode === 'template' ? 'template' : 'manual',
          manualCalories: Number(item.manualCalories) })
        continue
      }
      let foodId = Number(item.foodId)
      if (!foodId) {
        const selected = selectedCandidate(i)
        if (!selected) throw new Error(item.name + ' 尚未匹配可信营养来源')
        // Only after user confirmation: import a user-owned reference, deduplicated by USDA FDC source.
        const alias = /^[\p{L}\p{N} ()（）·-]{1,80}$/u.test(item.name) ? item.name : undefined
        const imported: Food = await wellnessApi.importUsda(selected.fdcId, alias)
        foodId = imported.id
      }
      newItems.push({ ...item, foodId, grams: Number(item.grams) })
    }
    corrected.items = newItems
    await apiClient.patch('/wellness/ai/drafts/' + draft.value.draftId, corrected, { timeout: WRITE_TIMEOUT_MS })
    await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm',
      {}, { timeout: WRITE_TIMEOUT_MS })
    markSaved()
  } catch (e) {
    await handleWriteError(e)
  } finally { saving.value = false }
}
async function confirmMulti() {
  if (!canConfirmMulti.value || !draft.value) return
  saving.value = true
  error.value = ''
  try {
    // Read-only preview. The backend validates every meal, total and duplicate
    // before committing all meals in one transaction.
    await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm',
      {}, { timeout: WRITE_TIMEOUT_MS })
    markSaved()
  } catch (e) {
    await handleWriteError(e)
  } finally { saving.value = false }
}
async function confirmBatch() {
  if (!canConfirmBatch.value || !draft.value) return
  saving.value = true
  error.value = ''
  try {
    // Batch data is intentionally read-only; the server rechecks source and each destination.
    await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm',
      {}, { timeout: WRITE_TIMEOUT_MS })
    markSaved()
  } catch (e) {
    await handleWriteError(e)
  } finally { saving.value = false }
}
onMounted(() => { void load() })
</script>

<template>
  <section class="health-chat-card" aria-label="AI 饮食确认卡">
    <strong>🍽️ {{ draft?.action === 'meal.create_batch' ? (multiMeals.length === 1 ? '饮食记录' : '多餐次饮食记录') : draft?.action === 'meal.copy_batch' ? '批量饮食记录' : 'AI 饮食记录' }}</strong>
    <p v-if="loading">正在读取记录并查询食品营养库…</p>
    <template v-else-if="draft">
      <p v-if="status === 'CONSUMED'" class="health-chat-success">✓ 已确认保存到健康中心</p>
      <p v-if="status === 'PENDING' && draft.modelUsed === 'conversation/estimate-preview'" class="health-chat-note">
        根据本会话中的餐食描述生成。热量如来自此前 AI 估算，只作为参考，请确认或修改后再保存；不会自动写入。
      </p>
      <p v-else-if="status !== 'PENDING'">草稿已过期，请重新告诉 PRP 助手需要记录什么。</p>
      <template v-else-if="draft.action === 'meal.create_batch'">
        <p class="health-chat-note">日期：{{ values.date }} · 仅使用你明确填写的本次热量，未使用 AI 猜测。</p>
        <p v-if="values.alreadyExistingTypes?.length" class="health-chat-note">
          已存在的餐次（{{ values.alreadyExistingTypes.map(t => types[t] || t).join('、') }}）已跳过，请到健康中心核实原记录。
        </p>
        <div v-for="meal in multiMeals" :key="meal.mealType" class="health-chat-food">
          <div class="health-chat-food-title">
            <b>{{ types[meal.mealType] || meal.mealType }}</b>
            <span>{{ Number(meal.totalCalories).toFixed(0) }} kcal</span>
          </div>
          <div v-for="(item, i) in meal.items" :key="i" class="health-chat-food-title">
            <span>{{ item.name }}{{ Number(item.grams) > 0 ? ' · ' + item.grams + ' g' : '' }}</span>
            <span>{{ Number(item.manualCalories).toFixed(0) }} kcal</span>
          </div>
        </div>
        <div class="health-chat-total"><span>{{ multiMeals.length === 1 ? '本次估算热量' : '本次计划新增总热量' }}</span><b>{{ multiCalories.toFixed(0) }} kcal</b></div>
        <p class="health-chat-note">多餐次将在同一数据库事务中写入，任一餐次已存在则整个操作停止，不覆盖历史数据。需要修改明细请重新发送准确的食物和热量。</p>
        <button type="button" class="health-chat-confirm" :disabled="!canConfirmMulti" @click="confirmMulti">
          {{ saving ? '正在核实并保存…' : '确认保存 ' + multiMeals.length + ' 个餐次' }}
        </button>
      </template>
      <template v-else-if="draft.action === 'meal.copy_batch'">
        <div class="health-chat-food">
          <b>来源：{{ values.sourceDate }} 已保存的{{ types[values.mealType ?? ''] || '餐次' }}</b>
          <p class="health-chat-note">以下食物和份量来自你在健康中心已保存的真实记录，不是 AI 猜测。确认时会再次验证原始记录。</p>
        </div>
        <div class="health-chat-food">
          <b>计划新增 {{ values.targets?.length ?? 0 }} 天记录</b>
          <ul class="health-batch-days">
            <li v-for="date in values.targets ?? []" :key="date">
              {{ date }} · {{ types[values.mealType ?? ''] || '餐次' }}
            </li>
          </ul>
        </div>
        <div class="health-chat-food">
          <b>每一天复制的食品</b>
          <div v-for="(item, i) in items" :key="i" class="health-chat-food-title">
            <span>{{ item.name }} · {{ item.grams > 0 ? item.grams + ' g' : '重量未记录' }}{{ item.foodId === 0 ? '（本次热量估算）' : '' }}</span>
            <span>{{ Number(item.calories ?? 0).toFixed(0) }} kcal</span>
          </div>
        </div>
        <div class="health-chat-total"><span>每日预计热量</span><b>{{ batchCalories.toFixed(0) }} kcal</b></div>
        <p class="health-chat-note">只新增上面列出的日期，不修改来源餐次；目标日期若已存在同类记录，会整体停止保存以防重复。</p>
        <button type="button" class="health-chat-confirm" :disabled="!canConfirmBatch" @click="confirmBatch">
          {{ saving ? '正在批量保存…' : '确认保存 ' + (values.targets?.length ?? 0) + ' 天记录' }}
        </button>
      </template>
      <template v-else-if="draft.action === 'meal.create'">
        <div class="health-chat-row">
          <label>日期 <input v-model="values.date" type="date" :disabled="saving" /></label>
          <label>餐次 <select v-model="values.mealType" :disabled="saving">
            <option v-for="(name, key) in types" :key="key" :value="key">{{ name }}</option>
          </select></label>
        </div>
        <div v-for="(item, i) in items" :key="i" class="health-chat-food">
          <div class="health-chat-food-title"><b>{{ item.name }}</b><span>{{ !isManual(item) && item.foodId && !Number.isFinite(calorieDensity[i]) ? '热量待读取' : portion(item, i).toFixed(0) + ' kcal' }}</span></div>
          <label v-if="suggestedDishes[i]?.length">匹配到你的常吃餐品（手动选择后才使用）
            <select :value="item.mode === 'template' ? item.templateId ?? '' : ''"
              :disabled="saving" @change="usePersonalDish(i, Number(($event.target as HTMLSelectElement).value))">
              <option value="">选择常吃餐品</option>
              <option v-for="dish in suggestedDishes[i]" :key="dish.id" :value="dish.id">
                {{ dish.merchantName || '个人餐品' }} · {{ dish.dishName }} {{ dish.portionLabel }} · {{ dish.caloriesPerServing }} kcal/份
              </option>
            </select>
          </label>
          <label>热量来源
            <select v-model="item.mode" :disabled="saving">
              <option value="catalog">使用食品库 / USDA 营养数据</option>
              <option value="manual">本次自定义热量（不入食品库）</option>
              <option v-if="item.mode === 'template'" value="template">引用个人常吃餐品</option>
            </select>
          </label>
          <template v-if="isManual(item)">
            <label>食物名称
              <input v-model.trim="item.name" type="text" maxlength="120" :disabled="saving" placeholder="如：红油馄饨" />
            </label>
            <label>本次摄入总热量（kcal）
              <input v-model.number="item.manualCalories" type="number" min="0.01" max="20000" step="0.01"
                inputmode="decimal" :disabled="saving || item.mode === 'template'" placeholder="如：650" />
            </label>
            <label>可食用克重（可选）
              <span class="health-chat-number-unit">
                <input v-model.number="item.grams" type="number" min="0" max="3000" step="0.1"
                  inputmode="decimal" :disabled="saving" placeholder="不清楚可留 0" />
                <span class="health-chat-unit">g</span>
              </span>
            </label>
            <p class="health-chat-note">仅保存本次餐次的食物名称与总热量，不新增食品库数据；蛋白质、碳水、脂肪未知，不代表为 0。</p>
            <template v-if="item.mode === 'manual'">
              <label class="health-chat-check">
                <input v-model="item.saveToFavorites" type="checkbox" :disabled="saving" />
                同时保存到「我的常吃餐品」
              </label>
              <template v-if="item.saveToFavorites">
                <label>商家名称（可留空）
                  <input v-model.trim="item.merchantName" maxlength="100" :disabled="saving" placeholder="例如：楼下沙县小吃" />
                </label>
                <label>份量规格（整份热量，不是每 100g）
                  <input v-model.trim="item.portionLabel" maxlength="100" :disabled="saving" placeholder="例如：大碗" />
                </label>
                <label>数量（可选）
                  <input v-model.number="item.portionCount" type="number" min="1" max="9999"
                    :disabled="saving" placeholder="例如：17 个" />
                </label>
                <label>热量参考来源
                  <select v-model="item.sourceType" :disabled="saving">
                    <option value="USER_ESTIMATE">我自己的估算</option>
                    <option value="AI_ESTIMATE">AI 辅助估算</option>
                    <option value="LABEL">包装 / 商家标注</option>
                    <option value="OTHER">其他来源</option>
                  </select>
                </label>
                <label>来源说明（可选）
                  <input v-model.trim="item.sourceNote" maxlength="255" :disabled="saving" placeholder="例如：与 ChatGPT 讨论估算" />
                </label>
              </template>
            </template>
            <p v-if="item.mode === 'template'" class="health-chat-note">引用你保存的餐品每份参考热量，实际确认后只保存本次快照；更新模板不会修改历史记录。</p>
          </template>
          <template v-else>
          <label>可食用克重
            <span class="health-chat-number-unit">
              <input v-model.number="item.grams" type="number" min="0.1" max="3000" step="0.1"
                inputmode="decimal" :disabled="saving" />
              <span class="health-chat-unit">g</span>
            </span>
          </label>
          <p v-if="Number(item.foodId)>0" class="health-chat-note">已匹配个人/公共食品库，热量由服务器复核</p>
          <template v-else>
            <p class="health-chat-note">食品库暂无，自动查询 USDA FoodData Central（营养值按每 100g）</p>
            <label v-if="matches[i]?.length">建议匹配
              <select v-model.number="chosen[i]" :disabled="saving">
                <option v-for="candidate in matches[i]" :key="candidate.fdcId" :value="candidate.fdcId">
                  {{ candidate.name }} · {{ candidate.calories100g }} kcal/100g
                </option>
              </select>
            </label>
            <p v-if="selectedCandidate(i)" class="health-chat-note">来源：{{ selectedCandidate(i)?.source }}；请核对英文食品名、品牌和烹饪状态，确认时才导入个人食品库</p>
            <p v-else class="health-chat-alert">{{ foodLoadingErrors[i] || '查询中…' }}</p>
          </template>
          <p v-if="Number(item.grams)<=0" class="health-chat-alert">请补充实际或估算重量，或者切换到「本次自定义热量」</p>
          <p v-if="foodLoadingErrors[i] && item.foodId" class="health-chat-alert">{{ foodLoadingErrors[i] }}</p>
          </template>
          <p v-if="isManual(item) && !validManualCalories(item)" class="health-chat-alert">请输入有效的食物名称和本次总热量（0～20000 kcal）</p>
        </div>
        <div class="health-chat-total"><span>预计总摄入</span><b>{{ total.toFixed(0) }} kcal</b></div>
        <p class="health-chat-note">食品库模式由服务器复算；自定义模式使用你填的本次总热量，不写入食品库，未知营养素不做推断。</p>
        <button class="health-chat-confirm" type="button" :disabled="!canConfirm" @click="confirm">
          {{ saving ? '正在确认保存…' : resolving ? '正在检索食品…' : '确认并保存记录' }}
        </button>
        <p v-if="!canConfirm && !saving" class="health-chat-note">没有匹配到食品？可以切换为「本次自定义热量」，输入估算千卡后直接保存，不必等待 USDA。</p>
      </template>
      <p v-else>AI 解析为其他健康记录类型，请在健康中心核实后录入。<RouterLink to="/wellness">打开健康中心</RouterLink></p>
      <p v-if="status === 'CONSUMED'"><RouterLink :to="'/wellness?date=' + values.date">查看当天健康记录 →</RouterLink></p>
    </template>
    <p v-if="error" class="health-chat-alert" role="alert">{{ error }}</p>
    <button v-if="saveOutcomeUnknown" class="health-chat-recheck" type="button"
      :disabled="checkingSaveOutcome || saving" @click="recheckSaveOutcome">
      {{ checkingSaveOutcome ? '正在核实…' : '检查保存状态（防止重复记录）' }}
    </button>
  </section>
</template>

<style scoped>
.health-chat-card{
  display:grid;gap:14px;width:100%;max-width:520px;min-width:0;
  box-sizing:border-box;margin:10px 0;padding:16px;
  border:1px solid #d9e4f4;border-radius:16px;background:#f8fbff;
  font-size:14px;line-height:1.6;overflow-wrap:anywhere;
}
.health-chat-card p{margin:0;line-height:1.6}
.health-chat-card label{
  display:grid;grid-template-columns:minmax(0,1fr);gap:7px;
  min-width:0;margin:0;color:#51637c;font-size:13px;font-weight:500;
}
.health-chat-card input:not([type="checkbox"]),
.health-chat-card select{
  display:block;box-sizing:border-box;width:100%;min-width:0;max-width:100%;
  height:44px;min-height:44px;margin:0;padding:9px 12px;
  border:1px solid #cbd5e1;border-radius:10px;
  background:#fff;color:#1e293b;font:inherit;font-size:16px;line-height:1.35;
  box-shadow:none;
}
.health-chat-card input[type="date"]{-webkit-min-logical-width:0}
.health-chat-card input:focus-visible,
.health-chat-card select:focus-visible{
  outline:2px solid #93c5fd;outline-offset:1px;border-color:#4386f3;
}
.health-chat-card input:disabled,.health-chat-card select:disabled{background:#eff3f8;color:#64748b}
.health-chat-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;min-width:0}
.health-chat-food{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;padding:16px 0;border-bottom:1px solid #dce5f1;min-width:0}
.health-chat-food-title,.health-chat-total{
  display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:6px 12px;min-width:0;
}
.health-chat-food-title b{min-width:0;flex:1 1 135px}
.health-chat-food-title span{flex:none;white-space:nowrap;font-variant-numeric:tabular-nums}
.health-chat-number-unit{display:flex;align-items:center;min-width:0;gap:9px}
.health-chat-number-unit input{flex:1 1 auto;width:0!important;min-width:0!important}
.health-chat-unit{flex:0 0 18px;color:#64748b;font-size:13px;text-align:left}
.health-chat-check{
  display:flex!important;flex-direction:row;align-items:center;gap:9px;
  font-size:13px!important;min-height:36px;cursor:pointer;
}
.health-chat-check input[type="checkbox"]{flex:0 0 auto;width:18px;height:18px;accent-color:#287fba}
.health-chat-note{font-size:12px;color:#64748b}
.health-chat-alert{font-size:12px;color:#a63b36;line-height:1.65!important}
.health-chat-success{color:#06784b;font-weight:600}
.health-batch-days{margin:4px 0 0;padding-left:22px;line-height:1.8;color:#334155}
.health-chat-total{padding:6px 0 0}
.health-chat-total b{font-size:22px;color:#1d4ed8;font-variant-numeric:tabular-nums;white-space:nowrap}
.health-chat-confirm{
  width:100%;min-height:48px;padding:11px;border:0;border-radius:11px;
  background:#287fba;color:#fff;font:inherit;font-size:15px;font-weight:600;cursor:pointer;
}
.health-chat-recheck{
  width:100%;min-height:44px;padding:10px;border:1px solid #93c5fd;
  border-radius:10px;background:#eef6ff;color:#1d4ed8;font:inherit;font-weight:600;cursor:pointer;
}
.health-chat-confirm:disabled,.health-chat-recheck:disabled{opacity:.55;cursor:not-allowed}
@media(max-width:600px){
  .health-chat-card{max-width:100%;gap:12px;padding:13px;border-radius:14px}
  .health-chat-card,.health-chat-card *{box-sizing:border-box;min-width:0}
  .health-chat-card input:not([type="checkbox"]),.health-chat-card select{width:100%;min-width:0;max-width:100%}
  .health-chat-card input[type="date"]{min-width:0;-webkit-min-logical-width:0}
  .health-chat-food-title b{flex-basis:0;overflow-wrap:anywhere}
  .health-chat-food-title span{max-width:100%;white-space:normal;overflow-wrap:anywhere}
  .health-chat-row{grid-template-columns:minmax(0,1fr);gap:12px}
  .health-chat-food{gap:11px;padding:13px 0}
}
</style>
