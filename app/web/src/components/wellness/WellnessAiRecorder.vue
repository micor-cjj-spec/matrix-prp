<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient, type ApiResponse } from '@/api/client'

type Draft = { draftId: string; action: string; description: string; modelUsed: string; values: Record<string, unknown> }
type Outcome = { action: string; route: string; saved: unknown }
const props = defineProps<{ initialText?: string }>()
const emit = defineEmits<{ recorded: [result: Outcome] }>()
const text = ref('')
const file = ref<File | null>(null)
const busy = ref(false)
const confirming = ref(false)
const draft = ref<Draft | null>(null)
const error = ref('')
const done = ref('')
watch(() => props.initialText, value => { if (value?.trim()) { text.value = value; draft.value = null } }, { immediate: true })
function fileChanged(e: Event) {
  const incoming = (e.target as HTMLInputElement).files?.[0]
  file.value = null; draft.value = null
  if (!incoming) return
  if (!['image/jpeg','image/png','image/webp'].includes(incoming.type) || incoming.size > 3_000_000) {
    ElMessage.warning('图片仅支持 JPEG、PNG、WebP，最大 3MB')
    return
  }
  file.value = incoming
}
async function plan() {
  if (busy.value || (!text.value.trim() && !file.value)) return
  busy.value = true; draft.value = null; error.value = ''; done.value = ''
  const form = new FormData()
  form.append('text', text.value.trim() || '识别这张餐食照片，估算可食部分量，供我确认后记录今天午餐')
  if (file.value) form.append('image', file.value)
  try {
    const r = await apiClient.post<ApiResponse<Draft>>('/wellness/ai/prepare', form, { timeout: 60000 })
    draft.value = r.data.data
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || '无法识别。请补充重量、使用食物库中的名称或检查模型配置。'
  } finally { busy.value = false }
}
async function save() {
  if (!draft.value || confirming.value) return
  confirming.value = true; error.value = ''
  try {
    const r = await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/drafts/' + draft.value.draftId + '/confirm', {})
    done.value = r.data.data.route
    emit('recorded', r.data.data)
    draft.value = null
    file.value = null
    ElMessage.success('已保存到健康中心')
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } }
    error.value = err.response?.data?.message || '保存失败，草稿可能过期或已被确认'
  } finally { confirming.value = false }
}
</script>

<template>
  <section class="prp-wellness-ai">
    <header><strong>✨ AI 健康快速记录</strong><small>先生成草稿，确认后入库</small></header>
    <textarea v-model="text" rows="3" maxlength="1500" :disabled="busy || confirming"
      aria-label="文字健康记录" placeholder="例：今天午餐200g米饭、150g鸡胸肉；今天跑步30分钟；体重86.5kg" />
    <div class="prp-wellness-ai-actions">
      <label>📷 餐食照片 <input type="file" accept="image/jpeg,image/png,image/webp" @change="fileChanged" /></label>
      <button :disabled="busy || confirming || (!text.trim() && !file)" @click="plan">{{ busy ? '识别中…' : 'AI 生成草稿' }}</button>
    </div>
    <small v-if="file">待识别图片：{{ file.name }}（{{ Math.ceil(file.size/1024) }}KB）</small>
    <p class="prp-wellness-ai-note">发送的文字和图片将交由所选 AI 服务商处理；PRP 不保存原始照片。图片无法精确估重和油量，请核对草稿。若未匹配到食物，请先从食物库导入或自建。</p>
    <p v-if="error" role="alert" class="prp-wellness-ai-error">{{ error }}</p>
    <div v-if="draft" class="prp-wellness-ai-preview">
      <strong>{{ draft.description }}</strong>
      <small>模型：{{ draft.modelUsed }}</small>
      <div v-if="Array.isArray(draft.values.items)" class="prp-wellness-ai-items">
        <div v-for="(item,index) in (draft.values.items as Array<{name: string;grams: number;calories: number}>)" :key="index">
          <span>{{ item.name }} · {{ item.grams }}g</span><b>{{ item.calories }} kcal</b>
        </div>
      </div>
      <div v-else class="prp-wellness-ai-values">
        <span v-for="(value,key) in draft.values" :key="key">{{ key }}: {{ value }}</span>
      </div>
      <p>请核对内容；如要修改，可在上方改写描述并重新生成。确认后仅保存一次。</p>
      <div class="prp-wellness-ai-actions">
        <button :disabled="confirming" @click="save">{{ confirming ? '保存中…' : '确认录入' }}</button>
        <button class="secondary" @click="draft=null">取消</button>
      </div>
    </div>
    <router-link v-if="done" :to="done">✅ 已保存，查看当天健康数据 →</router-link>
  </section>
</template>
<style scoped>
.prp-wellness-ai{display:grid;gap:12px;min-width:0;padding:14px;border:1px solid var(--el-border-color,#ddd);border-radius:12px;background:var(--el-bg-color,#fff)}
.prp-wellness-ai header,.prp-wellness-ai-actions,.prp-wellness-ai-items>div{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.prp-wellness-ai small,.prp-wellness-ai-note,.prp-wellness-ai-preview p{font-size:12px;color:var(--el-text-color-secondary,#777);line-height:1.5}
.prp-wellness-ai textarea{box-sizing:border-box;width:100%;min-width:0;padding:10px;font:inherit;font-size:16px;border-radius:8px;border:1px solid var(--el-border-color,#ddd);color:var(--el-text-color-primary,#222);background:var(--el-bg-color,#fff)}
.prp-wellness-ai-actions label{font-size:13px;max-width:100%}
.prp-wellness-ai-actions input{max-width:100%;font-size:12px}
.prp-wellness-ai-actions button{border:0;border-radius:8px;background:#267ab0;color:white;padding:10px 14px;cursor:pointer;font-size:14px}
.prp-wellness-ai-actions button:disabled{opacity:.6}
.prp-wellness-ai-actions button.secondary{background:var(--el-fill-color-dark,#eee);color:var(--el-text-color-primary,#222)}
.prp-wellness-ai-error{color:var(--el-color-danger,#c33);font-size:13px}
.prp-wellness-ai-preview{border:1px solid var(--el-color-primary-light-5,#ccddee);border-radius:8px;display:grid;gap:8px;padding:12px}
.prp-wellness-ai-items{display:grid;gap:6px;font-size:13px}
.prp-wellness-ai-values{display:flex;gap:6px;flex-wrap:wrap}
.prp-wellness-ai-values span{background:var(--el-fill-color-light,#eee);padding:4px;font-size:12px}
</style>
