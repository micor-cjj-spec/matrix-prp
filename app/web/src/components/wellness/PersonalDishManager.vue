<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { wellnessApi, type DishTemplate, type DishTemplateInput } from '@/api/wellness'

const dishes = ref<DishTemplate[]>([])
const query = ref('')
const busy = ref(false)
const dialogOpen = ref(false)
const editingId = ref<number | null>(null)
const sources = { USER_ESTIMATE: '个人估算', AI_ESTIMATE: 'AI 辅助估算', LABEL: '包装/商家标签', OTHER: '其他' }
const form = reactive<DishTemplateInput>({
  merchantName: '', dishName: '', portionLabel: '', portionCount: null,
  caloriesPerServing: 0, sourceType: 'USER_ESTIMATE', sourceNote: '',
})
async function load() {
  try { dishes.value = await wellnessApi.dishes(query.value.trim()) }
  catch { ElMessage.error('读取个人常吃餐品失败') }
}
function open(dish?: DishTemplate) {
  editingId.value = dish?.id ?? null
  Object.assign(form, {
    merchantName: dish?.merchantName ?? '', dishName: dish?.dishName ?? '',
    portionLabel: dish?.portionLabel ?? '', portionCount: dish?.portionCount ?? null,
    caloriesPerServing: Number(dish?.caloriesPerServing ?? 0),
    sourceType: dish?.sourceType ?? 'USER_ESTIMATE', sourceNote: dish?.sourceNote ?? '',
  })
  dialogOpen.value = true
}
async function save() {
  const kcal = Number(form.caloriesPerServing)
  if (!form.dishName.trim() || form.dishName.length > 120 || !Number.isFinite(kcal) ||
      kcal <= 0 || kcal > 20000 || Math.abs(kcal * 100 - Math.round(kcal * 100)) > 1e-6) {
    ElMessage.warning('请填写餐品名称和有效的每份热量')
    return
  }
  busy.value = true
  try {
    const data = { ...form, caloriesPerServing: kcal,
      portionCount: form.portionCount || null }
    if (editingId.value) await wellnessApi.updateDish(editingId.value, data)
    else await wellnessApi.addDish(data)
    dialogOpen.value = false
    ElMessage.success('常吃餐品已保存；历史摄入热量不会更改')
    await load()
  } catch { ElMessage.error('保存失败，请检查是否已存在相同商家、餐品和规格') }
  finally { busy.value = false }
}
async function remove(dish: DishTemplate) {
  try {
    await ElMessageBox.confirm(
      '删除常吃餐品不会删除历史饮食记录。确认删除「' + dish.dishName + '」吗？',
      '删除个人餐品', { type: 'warning' },
    )
    await wellnessApi.deleteDish(dish.id)
    await load()
    ElMessage.success('已删除常吃餐品')
  } catch { /* Cancel or request failure: do not mutate UI optimistically. */ }
}
onMounted(() => { void load() })
</script>

<template>
  <section class="personal-dish-section">
    <header class="personal-dish-head">
      <div>
        <h2>我的常吃餐品</h2>
        <p>保存常点商家和整份参考热量，与每 100g 标准食品库分开</p>
      </div>
      <el-button type="primary" @click="open()">新增常吃餐品</el-button>
    </header>
    <div class="personal-dish-search">
      <el-input v-model="query" clearable placeholder="搜索商家或餐品" @keyup.enter="load" @clear="load"/>
      <el-button @click="load">搜索</el-button>
    </div>
    <p v-if="!dishes.length" class="personal-dish-empty">暂无匹配的常吃餐品。你也可以在聊天记录确认时选择「同时保存到常吃餐品」。</p>
    <div class="personal-dish-grid">
      <article v-for="dish in dishes" :key="dish.id" class="personal-dish-tile">
        <div class="personal-dish-tile-title">
          <strong>{{ dish.dishName }}</strong>
          <span>{{ Number(dish.caloriesPerServing).toFixed(0) }} kcal/份</span>
        </div>
        <p>{{ dish.merchantName || '未指定商家' }} · {{ dish.portionLabel || '标准份' }}<template v-if="dish.portionCount"> · {{ dish.portionCount }} 个</template></p>
        <p class="personal-dish-source">{{ sources[dish.sourceType] || '其他来源' }}{{ dish.sourceNote ? ' · ' + dish.sourceNote : '' }}</p>
        <div class="personal-dish-actions">
          <el-button link type="primary" @click="open(dish)">修改参考热量</el-button>
          <el-button link type="danger" @click="remove(dish)">删除</el-button>
        </div>
      </article>
    </div>
    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑常吃餐品' : '新增常吃餐品'"
      width="min(520px, calc(100vw - 22px))" append-to-body destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="餐品名称（必填）"><el-input v-model="form.dishName" maxlength="120" placeholder="例如：红油馄饨" /></el-form-item>
        <el-form-item label="商家"><el-input v-model="form.merchantName" maxlength="100" placeholder="例如：楼下沙县小吃" /></el-form-item>
        <el-form-item label="规格"><el-input v-model="form.portionLabel" maxlength="100" placeholder="例如：大碗" /></el-form-item>
        <el-form-item label="数量"><el-input-number v-model="form.portionCount" :min="1" :max="9999" :step="1" /></el-form-item>
        <el-form-item label="每份热量 kcal（必填）"><el-input-number v-model="form.caloriesPerServing" :min="0.01" :max="20000" :precision="2" /></el-form-item>
        <el-form-item label="数据来源">
          <el-select v-model="form.sourceType">
            <el-option v-for="(label, key) in sources" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源说明（可选）"><el-input v-model="form.sourceNote" maxlength="255" placeholder="例如：与 ChatGPT 讨论估算" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen=false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存个人餐品</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.personal-dish-section{padding:18px;margin-top:14px;border:1px solid #e1e8f1;background:#fff;border-radius:16px}
.personal-dish-head,.personal-dish-tile-title{display:flex;justify-content:space-between;align-items:center;gap:12px}
.personal-dish-head h2{font-size:17px;margin:0 0 6px}
.personal-dish-head p,.personal-dish-tile p{font-size:13px;color:#6b7b91;margin:3px 0;line-height:1.6}
.personal-dish-search{display:flex;gap:8px;margin:14px 0}
.personal-dish-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.personal-dish-tile{padding:13px;border-radius:12px;border:1px solid #dce5f2;min-width:0}
.personal-dish-tile strong{overflow-wrap:anywhere}
.personal-dish-tile-title span{white-space:nowrap;color:#2563eb;font-weight:700}
.personal-dish-tile .personal-dish-source{font-size:12px;color:#64748b}
.personal-dish-actions{display:flex;gap:5px}
.personal-dish-empty{font-size:13px;color:#64748b;line-height:1.7}
@media(max-width:600px){.personal-dish-section{padding:12px}.personal-dish-head{align-items:start}.personal-dish-head h2{font-size:15px}.personal-dish-head p{max-width:170px}.personal-dish-head .el-button{white-space:normal}}
</style>
