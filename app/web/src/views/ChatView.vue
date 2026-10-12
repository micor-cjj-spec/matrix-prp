<script setup lang="ts">
import { onMounted, onBeforeUnmount, computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { getAiSettings, setAiSelection, type AiSettings } from '@/api/aiSettings'
import { fetchUsage, listConversations, listMessages, streamChat, type AiUsage, type ChatMessage, type Conversation } from '@/api/ai'

const conversations = ref<Conversation[]>([])
const messages = ref<ChatMessage[]>([])
const selectedId = ref<string | null>(null)
const input = ref('')
const sending = ref(false)
const usage = ref<AiUsage | null>(null)
const aiSettings = ref<AiSettings | null>(null)
const currentProvider = ref('deepseek')
const currentModel = ref('deepseek-chat')
const savingModel = ref(false)
const models = computed(() => aiSettings.value?.providers.find(p => p.id === currentProvider.value)?.models ?? [])
async function loadModels() {
  try {
    aiSettings.value = await getAiSettings()
    currentProvider.value = aiSettings.value.selectedProvider
    currentModel.value = aiSettings.value.selectedModel
  } catch { ElMessage.warning('AI 模型配置暂时无法读取') }
}
async function saveModel() {
  savingModel.value = true
  try { aiSettings.value = await setAiSelection(currentProvider.value, currentModel.value) }
  catch { ElMessage.error('切换模型失败，请检查设置'); await loadModels() }
  finally { savingModel.value = false }
}
async function changeProvider(id: string) {
  if (sending.value) return
  currentProvider.value = id
  currentModel.value = aiSettings.value?.providers.find(p => p.id === id)?.defaultModel ?? ''
  await saveModel()
}
async function changeModel(id: string) {
  if (sending.value) return
  currentModel.value = id
  await saveModel()
}
let controller: AbortController | null = null

async function refresh() {
  try {
    const [items, current] = await Promise.all([listConversations(), fetchUsage()])
    conversations.value = items
    usage.value = current
  } catch { ElMessage.error('无法加载 AI 会话') }
}
async function select(id: string) {
  if (sending.value) return
  selectedId.value = id
  try { messages.value = await listMessages(id) }
  catch { ElMessage.error('无法加载聊天记录') }
}
function newChat() {
  if (sending.value) return
  selectedId.value = null
  messages.value = []
}
async function send() {
  const content = input.value.trim()
  if (!content || sending.value || content.length > 4000) return
  input.value = ''
  sending.value = true
  const user: ChatMessage = { id: -Date.now(), role: 'user', content, createdAt: new Date().toISOString() }
  const assistant: ChatMessage = { id: -Date.now()-1, role: 'assistant', content: '', createdAt: new Date().toISOString() }
  messages.value.push(user, assistant)
  controller = new AbortController()
  let completed = false
  let streamError = false
  try {
    await streamChat(selectedId.value, content, ({ event, data }) => {
      if (event === 'meta') selectedId.value = String(data.conversationId)
      if (event === 'delta') assistant.content += String(data.text ?? '')
      if (event === 'done') completed = true
      if (event === 'error') { streamError = true; ElMessage.error(String(data.message ?? 'AI 请求失败')) }
    }, controller.signal)
    if (!completed) throw new Error('Stream interrupted')
  } catch {
    if (!streamError) ElMessage.error('连接中断或额度已用完，请稍后重试')
  } finally {
    sending.value = false
    controller = null
    await refresh()
    if (selectedId.value) {
      try { messages.value = await listMessages(selectedId.value) }
      catch { /* keep already received streaming text */ }
    }
  }
}
onMounted(() => { void refresh(); void loadModels() })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div><p class="eyebrow">Matrix AI</p><h1>AI 聊天</h1>
        <p>个人多模型 AI 对话与学习辅助。OpenClaw / Codex 执行能力尚未启用。</p></div>
    </header>
    <div class="model-toolbar" v-if="aiSettings">
      <label>服务商
        <el-select :model-value="currentProvider" :disabled="sending || savingModel" @change="changeProvider" style="width:170px">
          <el-option v-for="item in aiSettings.providers" :key="item.id" :value="item.id" :label="item.name" />
        </el-select>
      </label>
      <label>模型
        <el-select :model-value="currentModel" :disabled="sending || savingModel" filterable allow-create
          default-first-option @change="changeModel" style="width:210px">
          <el-option v-for="id in models" :key="id" :label="id" :value="id" />
          <el-option v-if="currentModel && !models.includes(currentModel)" :key="currentModel" :label="currentModel" :value="currentModel" />
        </el-select>
      </label>
      <RouterLink to="/me/ai-settings">管理 API Key</RouterLink>
    </div>
    <div class="chat-grid">
      <el-card shadow="never">
        <template #header>
          <div class="chat-row"><strong>历史会话</strong><el-button size="small" type="primary" @click="newChat">新对话</el-button></div>
        </template>
        <div v-for="item in conversations" :key="item.id" class="conversation"
          :class="{ active: item.id === selectedId }" @click="select(item.id)">{{ item.title }}</div>
        <el-empty v-if="conversations.length === 0" description="暂无对话" />
        <p v-if="usage" class="usage">本月请求 {{ usage.requests }}/{{ usage.maxRequests }} · 配额预留 {{ usage.reservedTokens }}/{{ usage.maxReservedTokens }} Token</p>
      </el-card>
      <el-card shadow="never" class="chat-panel">
        <div class="message-list" role="log" aria-live="polite">
          <div v-if="messages.length === 0" class="intro">向 Matrix AI 提问，开始新的对话。</div>
          <div v-for="(message, index) in messages" :key="message.id || index" class="bubble"
            :class="message.role === 'user' ? 'from-user' : 'from-ai'">
            <span class="role">{{ message.role === 'user' ? '我' : 'AI' }}</span>
            <p>{{ message.content || '正在思考...' }}</p>
          </div>
        </div>
        <div class="chat-compose">
          <el-input v-model="input" type="textarea" :rows="3" :maxlength="4000"
            placeholder="输入问题，按 Ctrl+Enter 发送" :disabled="sending" @keydown.ctrl.enter.prevent="send" />
          <div class="chat-row"><small>回答由 AI 生成，请核实重要信息。</small>
            <el-button type="primary" :disabled="!input.trim() || sending" :loading="sending" @click="send">发送</el-button>
          </div>
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>
<style scoped>
.model-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:0 0 16px}.model-toolbar label{display:flex;align-items:center;gap:8px;font-size:13px}.model-toolbar a{color:#2563eb;text-decoration:none;font-size:13px}
.chat-grid { display:grid; grid-template-columns:265px minmax(0,1fr); gap:16px }
.chat-panel { min-height:68vh }
.conversation { padding:10px; border-radius:7px; cursor:pointer; overflow-wrap:anywhere }
.conversation:hover,.conversation.active { background:#eff6ff }
.message-list { height:52vh; overflow:auto; display:flex; flex-direction:column; gap:14px; padding:6px }
.bubble { max-width:90%; background:#f1f5f9; padding:12px 14px; border-radius:12px; overflow-wrap:anywhere }
.from-user { align-self:flex-end; background:#e0efff }
.from-ai { align-self:flex-start }
.role { font-weight:600; font-size:12px; color:#64748b }
.bubble p { white-space:pre-wrap; margin:7px 0 0 }
.chat-row { display:flex; align-items:center; justify-content:space-between; gap:12px }
.chat-compose { margin-top:20px; display:grid; gap:12px }
.usage,.intro,.chat-row small { color:#64748b; font-size:12px }
@media (max-width:760px) { .chat-grid { grid-template-columns:1fr } .message-list { height:48vh } }
</style>
