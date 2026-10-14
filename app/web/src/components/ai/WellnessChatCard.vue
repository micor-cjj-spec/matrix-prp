<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { apiClient, type ApiResponse } from '@/api/client'
import { wellnessApi, type Food, type UsdaCandidate } from '@/api/wellness'
import { cloneJson } from '@/utils/cloneJson'

type Item = { foodId: number; name: string; grams: number; calories: number | null }
type DraftValues = {
  date: string; mealType?: string; items?: Item[]; note?: string
  sourceMealId?: number; sourceDate?: string; targets?: string[]
}
type Draft = { draftId: string; action: string; description: string; modelUsed: string; expiresAt: string; values: DraftValues }
type DraftView = { draft: Draft; status: 'PENDING' | 'CONSUMED' | 'EXPIRED' }
type Outcome = { route: string }
const props = defineProps<{ draftId: string }>()
const emit = defineEmits<{ saved: [] }>()
const loading = ref(true)
const saving = ref(false)
const error = ref('')
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
const types: Record<string, string> = { BREAKFAST: '早餐', LUNCH: '午餐', DINNER: '晚餐', SNACK: '加餐' }
const items = computed(() => values.value.items ?? [])
const canConfirm = computed(() => !loading.value && !saving.value && !resolving.value &&
  status.value === 'PENDING' && draft.value?.action === 'meal.create' &&
  items.value.length > 0 && items.value.every((item, i) =>
    Number(item.grams) > 0 && (Number(item.foodId) > 0
      ? Number.isFinite(calorieDensity[i])
      : Boolean(selectedCandidate(i)))))
const total = computed(() => items.value.reduce((sum, item, i) => sum + portion(item, i), 0))
const batchCalories = computed(() => items.value.reduce((sum, item) => sum + (Number(item.calories) || 0), 0))
const canConfirmBatch = computed(() => !loading.value && !saving.value &&
  status.value === 'PENDING' && draft.value?.action === 'meal.copy_batch' &&
  (values.value.targets?.length ?? 0) >= 1 &&
  (values.value.targets?.length ?? 0) <= 7 &&
  !!values.value.sourceMealId && !!values.value.sourceDate &&
  items.value.length > 0 && items.value.every(item => item.foodId > 0 && item.grams > 0))
function selectedCandidate(index: number) {
  return matches[index]?.find(candidate => candidate.fdcId === chosen[index])
}
function portion(item: Item, index: number) {
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
  const unresolved = items.value.map((item, i) => ({ item, i })).filter(({ item }) => !item.foodId)
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
    if (status.value === 'PENDING' && draft.value.action === 'meal.create')
      await searchMissingFoods()
  } catch { error.value = '读取记录草稿失败或无权访问'; }
  finally { loading.value = false }
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
    await apiClient.patch('/wellness/ai/drafts/' + draft.value.draftId, corrected)
    await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm', {})
    status.value = 'CONSUMED'
    emit('saved')
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } }; message?: string }
    error.value = err.response?.data?.message || err.message || '保存失败，请检查食品来源和克重'
  } finally { saving.value = false }
}
async function confirmBatch() {
  if (!canConfirmBatch.value || !draft.value) return
  saving.value = true
  error.value = ''
  try {
    // Batch data is intentionally read-only; the server rechecks source and each destination.
    await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm', {})
    status.value = 'CONSUMED'
    emit('saved')
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } }; message?: string }
    error.value = err.response?.data?.message || err.message || '批量保存失败，请重新检查来源和目标日期'
  } finally { saving.value = false }
}
onMounted(() => { void load() })
</script>

<template>
  <section class="health-chat-card" aria-label="AI 饮食确认卡">
    <strong>🍽️ {{ draft?.action === 'meal.copy_batch' ? '批量饮食记录' : 'AI 饮食记录' }}</strong>
    <p v-if="loading">正在读取记录并查询食品营养库…</p>
    <template v-else-if="draft">
      <p v-if="status === 'CONSUMED'" class="health-chat-success">✓ 已确认保存到健康中心</p>
      <p v-else-if="status !== 'PENDING'">草稿已过期，请重新告诉 PRP 助手需要记录什么。</p>
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
            <span>{{ item.name }} · {{ item.grams }} g</span>
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
          <div class="health-chat-food-title"><b>{{ item.name }}</b><span>{{ item.foodId && !Number.isFinite(calorieDensity[i]) ? '热量待读取' : portion(item, i).toFixed(0) + ' kcal' }}</span></div>
          <label>可食用克重 <input v-model.number="item.grams" type="number" min="0.1" max="3000" step="0.1" inputmode="decimal" :disabled="saving" /> g</label>
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
          <p v-if="Number(item.grams)<=0" class="health-chat-alert">请补充实际或估算重量，不能凭空生成营养数据</p>
          <p v-if="foodLoadingErrors[i] && item.foodId" class="health-chat-alert">{{ foodLoadingErrors[i] }}</p>
        </div>
        <div class="health-chat-total"><span>预计总摄入</span><b>{{ total.toFixed(0) }} kcal</b></div>
        <p class="health-chat-note">营养为参考估算；调味油、品牌和份量可能造成差异。确认后将按食品库数据重新计算并保存。</p>
        <button class="health-chat-confirm" type="button" :disabled="!canConfirm" @click="confirm">
          {{ saving ? '正在确认保存…' : resolving ? '正在检索食品…' : '确认并保存记录' }}
        </button>
        <p v-if="!canConfirm && !resolving && !saving" class="health-chat-note">缺少食品匹配或有效克重时不能保存。可补充信息重新描述，或先在健康中心建立食品。</p>
      </template>
      <p v-else>AI 解析为其他健康记录类型，请在健康中心核实后录入。<RouterLink to="/wellness">打开健康中心</RouterLink></p>
      <p v-if="status === 'CONSUMED'"><RouterLink :to="'/wellness?date=' + values.date">查看当天健康记录 →</RouterLink></p>
    </template>
    <p v-if="error" class="health-chat-alert" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.health-chat-card{display:grid;gap:11px;margin:10px 0;padding:14px;max-width:520px;min-width:0;border:1px solid #d9e4f4;border-radius:16px;background:#f8fbff;font-size:14px;overflow-wrap:anywhere}
.health-chat-card p{margin:0;line-height:1.65}
.health-chat-card label{display:grid;gap:5px;min-width:0;color:#475569;font-size:12px}
.health-chat-card input,.health-chat-card select{font:inherit;font-size:16px;width:100%;min-width:0;max-width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:8px;padding:7px;background:#fff;color:#1e293b}
.health-chat-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;min-width:0}
.health-chat-food{display:grid;gap:6px;padding:11px 0;border-bottom:1px solid #dce5f1;min-width:0}
.health-chat-food-title,.health-chat-total{display:flex;justify-content:space-between;align-items:center;gap:10px}
.health-chat-note{font-size:12px;color:#64748b}
.health-chat-alert{font-size:12px;color:#a63b36}
.health-chat-success{color:#06784b;font-weight:600}
.health-batch-days{margin:4px 0 0;padding-left:22px;line-height:1.8;color:#334155}
.health-chat-total b{font-size:21px;color:#1d4ed8}
.health-chat-confirm{width:100%;padding:11px;border:0;border-radius:10px;background:#287fba;color:#fff;font:inherit;font-weight:600;cursor:pointer}
.health-chat-confirm:disabled{opacity:.55;cursor:not-allowed}
@media(max-width:420px){.health-chat-row{grid-template-columns:1fr 1fr}.health-chat-card{padding:11px}}
</style>
