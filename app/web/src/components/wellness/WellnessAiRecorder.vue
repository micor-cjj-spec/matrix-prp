<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient, type ApiResponse } from '@/api/client'
import { wellnessApi, type Food } from '@/api/wellness'
import { cloneJson } from '@/utils/cloneJson'
import { prepareMealPhoto, photoSizeLabel } from '@/utils/mealPhoto'
import WellnessAiChange from '@/components/wellness/WellnessAiChange.vue'
type Action = 'meal.create' | 'exercise.create' | 'metric.create'
type Item = {
  foodId: number; name: string; grams: number; calories: number | null
  mode?: 'catalog' | 'manual'; manualCalories?: number | null
}
type Values = {
  date: string; mealType?: string; items?: Item[]; note?: string
  name?: string; durationMinutes?: number; estimatedKcal?: string | number | null
  weightKg?: number; bodyFatPct?: string | number | null; waistCm?: string | number | null
}
type Draft = { draftId: string; action: Action; description: string; modelUsed: string; values: Values }
type Outcome = { action: string; route: string; saved: unknown }
const props = defineProps<{ initialText?: string }>()
const emit = defineEmits<{ recorded: [result: Outcome] }>()
const managing = ref(false)
const text = ref('')
const file = ref<File | null>(null)
const draft = ref<Draft | null>(null)
const values = ref<Values>({ date: '' })
const foods = ref<Food[]>([])
const searchBusy = ref(false)
const busy = ref(false)
const confirming = ref(false)
const error = ref('')
const done = ref('')
watch(() => props.initialText, value => {
  if (value?.trim()) {
    text.value = value; draft.value = null
    if (/(修改|更正|改成|删除|撤销|删掉)/u.test(value)) managing.value = true
  }
}, { immediate: true })
const preparingPhoto = ref(false)
let photoSelectionVersion = 0
async function fileChanged(e: Event) {
  const inputElement = e.target as HTMLInputElement
  const source = inputElement.files?.[0]
  inputElement.value = ''
  if (!source) return
  const version = ++photoSelectionVersion
  file.value = null; draft.value = null
  preparingPhoto.value = true
  try {
    const result = await prepareMealPhoto(source)
    if (version !== photoSelectionVersion) return
    file.value = result.file
    if (result.compressed)
      ElMessage.success('照片已在本机重新编码并移除元数据：' + photoSizeLabel(result.originalBytes) +
        ' → ' + photoSizeLabel(result.file.size))
  } catch (error) {
    if (version === photoSelectionVersion)
      ElMessage.warning(error instanceof Error ? error.message : '照片处理失败，请重新选择')
  } finally {
    if (version === photoSelectionVersion) preparingPhoto.value = false
  }
}
async function findFoods(query: string) {
  if (!query.trim()) return
  searchBusy.value = true
  try {
    const found = await wellnessApi.foods(query.trim())
    foods.value = [...new Map([...foods.value, ...found].map(food => [food.id, food])).values()]
    if (!found.length) ElMessage.info('食物库没有匹配项，可先从 USDA 导入或新建')
  } catch { ElMessage.error('食物搜索失败') }
  finally { searchBusy.value = false }
}
function energy(item: Item): string {
  if (item.mode === 'manual') {
    return Number(item.manualCalories) > 0 ? Number(item.manualCalories).toFixed(1) + ' kcal（手动）' : '待人工填写热量'
  }
  const food = foods.value.find(x => x.id === Number(item.foodId))
  const grams = Number(item.grams)
  if (!food || !Number.isFinite(grams) || grams <= 0) return '待确认'
  return (Number(food.calories100g) * grams / 100).toFixed(1) + ' kcal'
}
async function plan() {
  if (busy.value || preparingPhoto.value || (!text.value.trim() && !file.value)) return
  busy.value = true; draft.value = null; error.value = ''; done.value = ''
  const form = new FormData()
  form.append('text', text.value.trim() || '请识别照片里的食物和可食部分量，生成今天的午餐记录草稿')
  if (file.value) form.append('image', file.value)
  try {
    const r = await apiClient.post<ApiResponse<Draft>>('/wellness/ai/prepare', form, { timeout: 60000 })
    draft.value = r.data.data
    values.value = cloneJson(r.data.data.values)
    if (values.value.items) {
      await Promise.all([...new Set(values.value.items.map(item => item.name))]
        .map(name => wellnessApi.foods(name).then(found => {
          foods.value = [...new Map([...foods.value, ...found].map(food => [food.id, food])).values()]
        }).catch(() => [])))
    }
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || 'AI 解析失败；请补全克数、尝试其他模型或使用手动录入。'
  } finally { busy.value = false }
}
function correction(): Record<string, unknown> {
  const v = cloneJson(values.value)
  if (draft.value?.action === 'exercise.create')
    v.estimatedKcal = v.estimatedKcal === '' || v.estimatedKcal == null ? null : Number(v.estimatedKcal)
  if (draft.value?.action === 'metric.create') {
    v.bodyFatPct = v.bodyFatPct === '' || v.bodyFatPct == null ? null : Number(v.bodyFatPct)
    v.waistCm = v.waistCm === '' || v.waistCm == null ? null : Number(v.waistCm)
  }
  return v
}
function addIngredient() {
  if (!draft.value || draft.value.action !== 'meal.create' || confirming.value) return
  const current = values.value.items ?? []
  if (current.length >= 30) return
  values.value.items = [...current, { foodId: 0, name: '', grams: 0, calories: null, mode: 'catalog', manualCalories: null }]
}
function removeIngredient(index: number) {
  const current = values.value.items ?? []
  if (confirming.value || current.length <= 1) return
  values.value.items = current.filter((_, i) => i !== index)
}
async function save() {
  if (!draft.value || confirming.value) return
  if (draft.value.action === 'meal.create' &&
      (!values.value.items?.length || values.value.items.length > 30 ||
       values.value.items.some(item =>
         !item.name?.trim() ||
         (item.mode === 'manual'
           ? !Number.isFinite(Number(item.manualCalories)) ||
             Number(item.manualCalories) <= 0 || Number(item.manualCalories) > 20000 ||
             !Number.isFinite(Number(item.grams)) || Number(item.grams) < 0 ||
             Number(item.grams) > 3000
           : !item.foodId || !Number(item.grams) || Number(item.grams) <= 0)))) {
    ElMessage.warning('请核对每种食物：食品库条目需要克数；自定义条目需要本次热量，重量不确定可为 0')
    return
  }
  confirming.value = true; error.value = ''
  try {
    await apiClient.patch('/wellness/ai/drafts/' + encodeURIComponent(draft.value.draftId), correction())
    const r = await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + encodeURIComponent(draft.value.draftId) + '/confirm', {})
    done.value = r.data.data.route
    emit('recorded', r.data.data)
    draft.value = null; file.value = null
    ElMessage.success('健康记录已保存')
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || '保存失败，请检查草稿字段及登录状态'
  } finally { confirming.value = false }
}
</script>

<template>
  <section class="prp-health-capture">
    <header><strong>✨ AI 健康记录</strong><small>拍照或文字 → 修改草稿 → 确认保存</small></header>
    <div class="capture-actions">
      <button type="button" class="outline" @click="managing=false">新增记录</button>
      <button type="button" class="outline" @click="managing=true">修改 / 删除已有记录</button>
    </div>
    <WellnessAiChange v-if="managing" @changed="result => { done=result.route; managing=false; emit('recorded',result) }" />
    <template v-else>
    <textarea v-model="text" rows="3" maxlength="1500" :disabled="busy || confirming" aria-label="描述健康记录"
      placeholder="例：今天午餐200g米饭、150g鸡胸肉；跑步30分钟；体重86.5kg" />
    <div class="capture-actions">
      <label>📷 餐食照片 <input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" @change="fileChanged" /></label>
      <button :disabled="busy || confirming || preparingPhoto || (!text.trim() && !file)" @click="plan">{{ preparingPhoto ? '照片压缩中…' : busy ? '识别中…' : 'AI 生成草稿' }}</button>
    </div>
    <small v-if="preparingPhoto" role="status">正在本机处理照片，请稍候…</small>
    <small v-if="file">选中图片：{{ file.name }}（{{ photoSizeLabel(file.size) }}）</small>
    <p class="capture-note">上传外卖截图前，请在相册中遮挡姓名、电话、收货地址、订单号及支付信息。图片在本机去除元数据后发送给所选 AI 服务商，PRP 不保存原图；仅确认后的饮食数据参与统计。AI 服务商的数据处理规则请参考其隐私条款。</p>
    <p v-if="error" role="alert" class="capture-error">{{ error }}</p>
    <div v-if="draft" class="capture-draft">
      <strong>{{ draft.description }}</strong>
      <small>识别模型：{{ draft.modelUsed }} · 草稿15分钟内有效</small>
      <label>记录日期 <input v-model="values.date" type="date" /></label>
      <template v-if="draft.action === 'meal.create'">
        <label>餐次
          <select v-model="values.mealType">
            <option value="BREAKFAST">早餐</option><option value="LUNCH">午餐</option>
            <option value="DINNER">晚餐</option><option value="SNACK">加餐</option>
          </select>
        </label>
        <div v-for="(item,index) in values.items" :key="index" class="capture-item">
          <div class="capture-actions"><strong>{{ item.name || '未知食物' }}</strong>
            <small>{{ energy(item) }}</small></div>
          <div class="capture-actions">
            <input v-model="item.name" placeholder="搜索食品名称" aria-label="食物名称" />
            <button type="button" class="outline" :disabled="searchBusy" @click="findFoods(item.name)">查找食品</button>
          </div>
          <label>热量依据
            <select v-model="item.mode" @change="item.mode === 'manual' ? item.foodId = 0 : item.manualCalories = null">
              <option value="catalog">食品库 × 克数</option>
              <option value="manual">本次手动填写热量（未知营养素不按0处理）</option>
            </select>
          </label>
          <label v-if="item.mode !== 'manual'">选择食品库条目
            <select v-model.number="item.foodId">
              <option :value="0">未匹配（请选择条目）</option>
              <option v-for="food in foods" :key="food.id" :value="food.id">
                {{ food.name }} · {{ food.calories100g }} kcal/100g
              </option>
            </select>
          </label>
          <label v-if="item.mode === 'manual'">本次实际热量（kcal，人工输入）
            <input v-model.number="item.manualCalories" type="number" inputmode="decimal" min="0.01" max="20000" step="0.01" />
          </label>
          <label>可食部分量（g）
            <input v-model.number="item.grams" type="number" inputmode="decimal"
              :min="item.mode === 'manual' ? 0 : 0.1" max="3000" step="0.1" />
          </label>
          <small v-if="item.mode === 'manual'">
            克数不确定可填0；此处热量须人工确认。包装标签每100g候选值不自动成为正式营养数据，
            保存后可在“今日饮食 → 分析详情”中核实标签与实际食用克数。
          </small>
          <button v-if="(values.items?.length ?? 0) > 1" type="button" class="outline"
            :disabled="confirming" @click="removeIngredient(index)">移除食物</button>
        </div>
        <div class="capture-actions">
          <small>食物明细 {{ values.items?.length ?? 0 }} / 30，确认所有食材均已录入。</small>
          <button type="button" class="outline" :disabled="confirming || (values.items?.length ?? 0) >= 30"
            @click="addIngredient">+ 补充食物</button>
        </div>
        <label>备注 <input v-model="values.note" maxlength="300" /></label>
        <p class="capture-note">未找到食品库条目时，可手动确认本次热量并保存（未知营养素留空）；有包装标签的食物保存后可在详情中核实每100g数据，自动换算实际摄入。</p>
      </template>
      <template v-else-if="draft.action === 'exercise.create'">
        <label>运动名称 <input v-model="values.name" maxlength="100" /></label>
        <label>时长（分钟） <input v-model.number="values.durationMinutes" type="number" min="1" max="1440" /></label>
        <label>估算消耗 kcal（可留空） <input v-model="values.estimatedKcal" type="number" min="0" max="20000" /></label>
        <label>备注 <input v-model="values.note" maxlength="300" /></label>
      </template>
      <template v-else-if="draft.action === 'metric.create'">
        <label>体重（kg） <input v-model.number="values.weightKg" type="number" step="0.1" min="0.1" max="500" /></label>
        <label>体脂率（%），可选 <input v-model="values.bodyFatPct" type="number" min="0" max="100" step="0.1" /></label>
        <label>腰围（cm），可选 <input v-model="values.waistCm" type="number" min="0" max="300" step="0.1" /></label>
      </template>
      <div class="capture-actions">
        <button :disabled="confirming" @click="save">{{ confirming ? '正在保存…' : '确认并保存记录' }}</button>
        <button type="button" class="outline" @click="draft=null">取消</button>
      </div>
    </div>
    </template>
    <router-link v-if="done" :to="done">✅ 已完成，打开当天健康中心 →</router-link>
  </section>
</template>

<style scoped>
.prp-health-capture{display:grid;gap:12px;min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;padding:14px;border:1px solid var(--el-border-color,#ddd);border-radius:14px;background:var(--el-bg-color,#fff);color:var(--el-text-color-primary,#222)}
.prp-health-capture header,.capture-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;min-width:0}
.prp-health-capture header small{flex:1 1 180px;min-width:0;overflow-wrap:anywhere}
.prp-health-capture small,.capture-note{font-size:12px;line-height:1.5;color:var(--el-text-color-secondary,#777)}
.prp-health-capture textarea,.prp-health-capture input:not([type=file]),.prp-health-capture select{font:inherit;font-size:16px;color:inherit;min-width:0;width:100%;box-sizing:border-box;padding:8px;border-radius:8px;border:1px solid var(--el-border-color,#ddd);background:var(--el-bg-color,#fff)}
.prp-health-capture textarea{resize:vertical}
.prp-health-capture label{font-size:13px;display:grid;gap:5px;min-width:0}
.prp-health-capture input[type=file]{font-size:12px;max-width:100%}
.capture-actions button{border:0;border-radius:8px;background:#287fba;color:#fff;padding:9px 12px;cursor:pointer;font-size:14px}
.capture-actions button.outline{background:var(--el-fill-color-light,#eee);color:var(--el-text-color-primary,#222)}
.capture-actions button:disabled{opacity:.6;cursor:not-allowed}
.capture-error{color:var(--el-color-danger,#c33);font-size:13px}
.capture-draft,.capture-item{display:grid;min-width:0;gap:10px;border:1px solid var(--el-border-color-lighter,#e6e6e6);border-radius:10px;padding:12px}
.capture-item{background:var(--el-fill-color-extra-light,#fafafa)}
</style>