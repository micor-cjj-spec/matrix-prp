<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { getAiSettings, saveAiKey, removeAiKey, setAiSelection, testAiProvider, fetchAiTelemetry, type AiSettings, type AiTelemetry } from '@/api/aiSettings'

const settings = ref<AiSettings | null>(null)
const providerId = ref('deepseek')
const modelId = ref('deepseek-chat')
const apiKey = ref('')
const busy = ref(false)
const loading = ref(true)
const telemetry = ref<AiTelemetry | null>(null)
const telemetryDays = ref<1 | 7 | 30>(7)
const telemetryLoading = ref(false)
const telemetryError = ref(false)
async function loadTelemetry() {
  telemetryLoading.value = true
  telemetryError.value = false
  try { telemetry.value = await fetchAiTelemetry(telemetryDays.value) }
  catch { telemetry.value = null; telemetryError.value = true }
  finally { telemetryLoading.value = false }
}
function formattedCount(value: number | null | undefined) {
  return value == null ? '未上报' : value.toLocaleString()
}
const provider = computed(() => settings.value?.providers.find(p => p.id === providerId.value))
const saved = computed(() => provider.value?.personalKey ?? false)
const configured = computed(() => provider.value?.configured ?? false)
function switchProvider(id: string) {
  providerId.value = id
  const item = settings.value?.providers.find(p => p.id === id)
  modelId.value = settings.value?.selectedProvider === id
    ? settings.value.selectedModel : (item?.defaultModel ?? '')
  apiKey.value = ''
}
async function load() {
  loading.value = true
  try {
    settings.value = await getAiSettings()
    switchProvider(settings.value.selectedProvider)
  } catch {
    ElMessage.error('无法加载 AI 设置，请确认后端已完成 V9 数据库迁移')
  } finally { loading.value = false }
}
async function save() {
  if (!apiKey.value.trim()) { ElMessage.warning('请填写 API Key'); return }
  busy.value = true
  try {
    settings.value = await saveAiKey(providerId.value, apiKey.value)
    apiKey.value = ''
    ElMessage.success('密钥已加密保存，页面不会回显明文')
  } catch { ElMessage.error('保存失败，请检查服务器加密密钥及数据库配置') }
  finally { busy.value = false }
}
async function remove() {
  try { await ElMessageBox.confirm('删除个人密钥后，此服务商可能无法继续使用。确定删除？', '删除密钥', { type: 'warning' }) }
  catch { return }
  busy.value = true
  try { settings.value = await removeAiKey(providerId.value); apiKey.value = ''; ElMessage.success('已删除个人密钥') }
  catch { ElMessage.error('删除失败') }
  finally { busy.value = false }
}
async function select() {
  if (!modelId.value.trim()) { ElMessage.warning('请选择或输入模型 ID'); return }
  busy.value = true
  try {
    settings.value = await setAiSelection(providerId.value, modelId.value.trim())
    ElMessage.success('默认聊天模型已更新')
  } catch { ElMessage.error('切换失败，请检查模型 ID') }
  finally { busy.value = false }
}
async function test() {
  busy.value = true
  try { await testAiProvider(providerId.value, modelId.value); ElMessage.success('连接成功，已消耗少量 API Token 和调用额度') }
  catch { ElMessage.error('连接失败，请检查 API Key、模型、余额及网络') }
  finally { busy.value = false }
}
onMounted(() => { void load(); void loadTelemetry() })
</script>
<template>
  <AppLayout>
    <div class="ai-settings">
      <RouterLink to="/me" class="back-link">‹ 返回我的</RouterLink>
      <header class="page-header">
        <div><p class="eyebrow">MATRIX AI</p><h1>AI 模型与接口</h1>
          <p>配置个人模型服务商，密钥仅由后端加密保存。支持多模型聊天，不开放服务器执行权限。</p></div>
      </header>
      <el-skeleton v-if="loading" :rows="6" animated />
      <template v-else-if="settings">
        <el-card shadow="never" class="ai-settings-card">
          <template #header><strong>选择 AI 服务商</strong></template>
          <div class="provider-grid">
            <button v-for="item in settings.providers" :key="item.id" type="button"
              class="provider-card" :class="{ active: item.id === providerId }" :aria-pressed="item.id === providerId"
              @click="switchProvider(item.id)">
              <strong>{{ item.name }}</strong>
              <small>{{ item.personalKey ? '已存个人密钥' : item.configured ? '可使用服务器默认配置' : '未配置' }}</small>
            </button>
          </div>
          <div class="form-grid">
            <div>
              <label class="field-label" for="model-input">模型 ID</label>
              <el-select id="model-input" v-model="modelId" filterable allow-create default-first-option
                style="width:100%" placeholder="选择预设或输入自定义模型 ID">
                <el-option v-for="item in provider?.models ?? []" :key="item" :label="item" :value="item" />
              </el-select>
              <p class="help">模型名称以服务商实际可用为准；如有新模型，可直接输入 ID。</p>
            </div>
            <div>
              <label class="field-label" for="personal-api-key">个人 API Key</label>
              <el-input id="personal-api-key" v-model="apiKey" type="password" show-password
                autocomplete="new-password" placeholder="填写密钥以新增或替换，已保存的密钥不会显示" />
              <p class="help">{{ saved ? '已有个人密钥。留空不会覆盖它。' : configured ? '当前使用服务器 DeepSeek 兼容配置。' : '当前尚未配置密钥。' }}</p>
            </div>
          </div>
          <div class="actions">
            <el-button type="primary" :loading="busy" :disabled="!apiKey.trim()" @click="save">保存密钥</el-button>
            <el-button :loading="busy" @click="select">设为聊天默认模型</el-button>
            <el-button :loading="busy" :disabled="!configured" @click="test">测试连接（产生少量费用）</el-button>
            <el-button v-if="saved" type="danger" plain :loading="busy" @click="remove">删除个人密钥</el-button>
          </div>
          <p class="help">当前聊天默认：{{ settings.selectedProvider }} / {{ settings.selectedModel }}。保存密钥不自动切换聊天默认模型。</p>
        </el-card>
        <el-card shadow="never" class="ai-settings-card">
          <template #header>
            <div class="ai-metrics-header">
              <strong>AI 模型调用记录</strong>
              <div class="actions ai-metrics-actions">
                <el-select v-model="telemetryDays" aria-label="统计时间范围" style="width:112px" @change="loadTelemetry">
                  <el-option :value="1" label="近 1 天" />
                  <el-option :value="7" label="近 7 天" />
                  <el-option :value="30" label="近 30 天" />
                </el-select>
                <el-button :loading="telemetryLoading" @click="loadTelemetry">刷新</el-button>
              </div>
            </div>
          </template>
          <p v-if="telemetryError" class="help">调用记录暂不可用，请确认 V23 数据库迁移已完成。</p>
          <el-skeleton v-else-if="telemetryLoading && !telemetry" :rows="3" animated />
          <template v-else-if="telemetry">
            <div class="ai-metrics-grid">
              <div><strong>{{ formattedCount(telemetry.summary.totalRequests) }}</strong><small>调用次数</small></div>
              <div><strong>{{ formattedCount(telemetry.summary.failedRequests) }}</strong><small>失败次数</small></div>
              <div><strong>{{ telemetry.summary.averageElapsedMs == null ? '—' : telemetry.summary.averageElapsedMs + ' ms' }}</strong><small>平均模型耗时</small></div>
              <div><strong>{{ telemetry.summary.averageFirstTokenMs == null ? '—' : telemetry.summary.averageFirstTokenMs + ' ms' }}</strong><small>平均首字延迟</small></div>
              <div><strong>{{ formattedCount(telemetry.summary.inputTokens + telemetry.summary.outputTokens) }}</strong><small>已上报 Token 合计</small></div>
              <div><strong>{{ formattedCount(telemetry.summary.unreportedUsageRequests) }}</strong><small>Token 未上报请求</small></div>
            </div>
            <p class="help">统计范围仅含当前账号经过统一 Gateway 的模型调用及模型连接测试，不含业务工具规划、健康图片解析或刷题专用模型调用。费用暂无可信价格表，不展示金额。</p>
            <el-table :data="telemetry.recent" size="small" style="width:100%" empty-text="暂无调用记录">
              <el-table-column label="调用时间" min-width="145">
                <template #default="{ row }">{{ row.occurredAt.replace('T', ' ').slice(0, 19) }}</template>
              </el-table-column>
              <el-table-column prop="model" label="模型" min-width="140" />
              <el-table-column label="状态" min-width="95">
                <template #default="{ row }">{{ row.status === 'SUCCESS' ? '成功' : (row.failureCategory || '失败') }}</template>
              </el-table-column>
              <el-table-column label="耗时" width="95">
                <template #default="{ row }">{{ row.elapsedMs }} ms</template>
              </el-table-column>
              <el-table-column label="Token" width="110">
                <template #default="{ row }">{{ row.inputTokens == null || row.outputTokens == null ? '未上报' : (row.inputTokens + row.outputTokens).toLocaleString() }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-card>
        <el-card shadow="never" class="ai-settings-card">
          <template #header><strong>OpenClaw / Codex 智能体</strong></template>
          <p class="help">OpenClaw Gateway 与 Codex Worker 将在后续独立阶段接入。当前均处于未启用状态，不会执行系统命令、访问个人财务或健康数据。</p>
          <p class="help">API Key 只会发送至对应模型厂商。服务器需配置独立加密主密钥，且必须先完成 V9 数据库迁移。请妥善保管主密钥，丢失将无法解密已保存的 API Key。</p>
        </el-card>
      </template>
    </div>
  </AppLayout>
</template>
<style scoped>
.ai-settings{max-width:1050px;margin:auto}.back-link{display:inline-block;margin-bottom:18px;color:#4675bf;text-decoration:none}
.ai-settings-card{margin-bottom:16px}
.ai-metrics-header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.ai-metrics-actions{margin:0;align-items:center}
.ai-metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:10px 0}
.ai-metrics-grid>div{display:grid;gap:5px;border:1px solid #e4e9f2;border-radius:10px;padding:12px}
.ai-metrics-grid strong{font-size:18px;overflow-wrap:anywhere}
.ai-metrics-grid small{color:#6b7890}.provider-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:24px}
.provider-card{display:grid;gap:7px;text-align:left;border:1px solid #dce6f2;background:#f9fbff;border-radius:12px;padding:16px;cursor:pointer}
.provider-card.active{border:2px solid #3176e6;background:#ecf3ff}.provider-card small{color:#74839b}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field-label{display:block;margin-bottom:8px;font-size:13px;font-weight:700}
.help{font-size:12px;line-height:1.7;color:#687a95}.actions{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.actions .el-button{margin-left:0}
@media(max-width:760px){.ai-metrics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-grid,.form-grid{grid-template-columns:1fr 1fr}.provider-card{padding:11px}.actions .el-button{flex:1;min-width:140px}}
@media(max-width:440px){.form-grid{grid-template-columns:1fr}}
</style>
