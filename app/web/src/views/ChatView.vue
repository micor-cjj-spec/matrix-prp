<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, ChatDotRound, Close, CopyDocument, Edit, Menu, Plus, Promotion, RefreshRight, Setting } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import AiActionLink from '@/components/ai/AiActionLink.vue'
import AiActionDialog from '@/components/ai/AiActionDialog.vue'
import { useRoute } from 'vue-router'
import AiNavigationCard from '@/components/ai/AiNavigationCard.vue'
import ChatConversationPanel from '@/components/ai/ChatConversationPanel.vue'
import { getAiSettings, setAiSelection, type AiSettings } from '@/api/aiSettings'
import { fetchUsage, pageConversations, renameConversation, deleteConversation, listMessages, listMessageBlocks, streamChat, previewAiContext, confirmAiContext, prepareInlineHealthDraft, confirmPendingHealthDraft, AiStreamHttpError,
  type AiUsage, type ChatMessage, type AiMessageBlock, type Conversation, type AiContextPreview } from '@/api/ai'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { latestChatToRestore, shouldApplyLoadedConversation } from '@/utils/chatRestore'
import { isMealCardRequest } from '@/utils/mealCardIntent'
import { isWellnessReadQuery } from '@/utils/wellnessReadIntent'

type ContextOption = { value: string; label: string; hint: string }
const options: ContextOption[] = [
  { value: 'tasks', label: '任务', hint: '今日待办与任务概览' },
  { value: 'practice', label: '刷题', hint: '答题正确率与练习统计' },
  { value: 'wellness', label: '健康', hint: '饮食与运动近7至30天趋势（不含体重）' },
  { value: 'wellness_body', label: '身体指标', hint: '体重敏感信息：单独授权近7至30天趋势' },
  { value: 'finance', label: '财务', hint: '当月收支与分类统计（敏感）' },
]
const optionByValue = (value: string) => options.find(option => option.value === value)
const conversations = ref<Conversation[]>([])
const messages = ref<ChatMessage[]>([])
const blocksByMessage = ref<Record<number, AiMessageBlock[]>>({})
const route = useRoute()
const actionDialogVisible = ref(false)
const activeActionId = ref<string | null>(null)
const actionRevision = ref(0)
function openAction(id: string) {
  if (!/^[0-9a-fA-F-]{36}$/.test(id)) return
  activeActionId.value = id
  actionDialogVisible.value = true
}
watch(() => route.query.action, value => {
  if (typeof value === 'string') openAction(value)
}, { immediate: true })

function groupBlocks(blocks: AiMessageBlock[]): Record<number, AiMessageBlock[]> {
  const grouped: Record<number, AiMessageBlock[]> = {}
  for (const block of blocks) (grouped[block.messageId] ??= []).push(block)
  return grouped
}
const hasOlder = ref(false)
const loadingOlder = ref(false)
const HISTORY_PAGE_SIZE = 200
let prependingHistory = false
const selectedId = ref<string | null>(null)
const input = ref('')
const sending = ref(false)
const historyOpen = ref(false)
const historyLoading = ref(false)
const historyLoadError = ref(false)
const conversationsCursor = ref<string | null>(null)
const conversationsHasMore = ref(false)
const conversationsLoadingMore = ref(false)
const managingConversation = ref(false)
const showJumpToBottom = ref(false)
let explicitlyStartedNew = false
let activeSelectionRequest = 0
const usage = ref<AiUsage | null>(null)
const settings = ref<AiSettings | null>(null)
const provider = ref('deepseek')
const model = ref('deepseek-chat')
const savingModel = ref(false)
const selectedScopes = ref<string[]>([])
const mentionOpen = ref(false)
const mentionQuery = ref('')
const preview = ref<AiContextPreview | null>(null)
const previewVisible = ref(false)
const previewing = ref(false)
const confirming = ref(false)
const streamError = ref('')
const chatPhoto = ref<File | null>(null)
const photoInput = ref<HTMLInputElement | null>(null)
function photoSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 3_000_000) {
    ElMessage.warning('仅支持小于3MB的 JPG、PNG 或 WebP 食物照片')
  } else chatPhoto.value = file
  if (photoInput.value) photoInput.value.value = ''
}
async function prepareInlineDiet(content: string) {
  if (sending.value) return
  const photo = chatPhoto.value
  const originalText = input.value
  const previousMessages = [...messages.value]
  const id = -Date.now()
  ++activeSelectionRequest
  input.value = ''
  chatPhoto.value = null
  selectedScopes.value = []
  invalidatePreview()
  mentionOpen.value = false
  sending.value = true
  streamError.value = ''
  messages.value.push(
    { id, role: 'user', content: photo ? content + '（附餐食照片）' : content, createdAt: new Date().toISOString() },
    { id: id - 1, role: 'assistant', content: '正在整理饮食和营养数据，请稍候…', createdAt: new Date().toISOString() },
  )
  bottom()
  try {
    const result = await prepareInlineHealthDraft(content, selectedId.value, photo)
    selectedId.value = result.conversationId
    // The POST already persisted both messages and the draft: never resubmit on a refresh failure.
    const assistant = messages.value[messages.value.length - 1]!
    assistant.id = result.messageId
    assistant.content = '已整理健康记录，请点击下方链接核对并确认保存。'
    const localBlock: AiMessageBlock = {
      messageId: result.messageId, type: 'wellness_draft', module: 'wellness',
      label: '待确认健康记录', route: result.draft.draftId,
    }
    blocksByMessage.value = { ...blocksByMessage.value, [result.messageId]: [localBlock] }
    const [latest, blocks] = await Promise.allSettled([
      listMessages(result.conversationId, undefined, HISTORY_PAGE_SIZE + 1),
      listMessageBlocks(result.conversationId),
    ])
    if (latest.status === 'fulfilled') {
      messages.value = latest.value.slice(-HISTORY_PAGE_SIZE)
      hasOlder.value = latest.value.length > HISTORY_PAGE_SIZE
    }
    if (blocks.status === 'fulfilled') {
      const restored = groupBlocks(blocks.value)
      blocksByMessage.value = {
        ...restored,
        [result.messageId]: restored[result.messageId] ?? [localBlock],
      }
    }
    if (latest.status === 'rejected' || blocks.status === 'rejected') {
      ElMessage.warning('饮食草稿已保存，历史同步暂时失败，重新打开本会话即可恢复')
    }
    try { await refresh() } catch { /* POST was successful; optional history refresh must not retry it */ }
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } }
    streamError.value = err.response?.data?.message || 'AI 饮食记录解析失败，请检查模型配置并重试'
    input.value = originalText
    chatPhoto.value = photo
    messages.value = previousMessages
  } finally {
    sending.value = false
    bottom()
  }
}
const scroller = ref<HTMLElement | null>(null)
const models = computed(() => settings.value?.providers.find(item => item.id === provider.value)?.models ?? [])
const currentProviderName = computed(() => settings.value?.providers.find(item => item.id === provider.value)?.name ?? provider.value)
const filteredOptions = computed(() =>
  options.filter(item => item.label.includes(mentionQuery.value) || item.value.includes(mentionQuery.value.toLowerCase())))
const isEmpty = computed(() => messages.value.length === 0)
let controller: AbortController | null = null

async function loadSettings() {
  try {
    settings.value = await getAiSettings()
    provider.value = settings.value.selectedProvider
    model.value = settings.value.selectedModel
  } catch { ElMessage.warning('模型配置暂时不可用') }
}
async function changeProvider(id: string) {
  if (sending.value || savingModel.value || !settings.value) return
  const previous = { provider: provider.value, model: model.value }
  provider.value = id
  model.value = settings.value.providers.find(item => item.id === id)?.defaultModel ?? ''
  await persistModel(previous)
}
async function changeModel(id: string) {
  if (sending.value || savingModel.value) return
  const previous = { provider: provider.value, model: model.value }
  model.value = id
  await persistModel(previous)
}
async function persistModel(previous: { provider: string; model: string }) {
  savingModel.value = true
  preview.value = null // preview binds to the selected provider + model
  try { settings.value = await setAiSelection(provider.value, model.value) }
  catch {
    provider.value = previous.provider
    model.value = previous.model
    ElMessage.error('切换模型失败，请检查配置')
  } finally { savingModel.value = false }
}

async function refresh(restoreLatest = false) {
  historyLoading.value = true
  // A refresh reopens the first cursor page; lazy pages are loaded on demand.
  const [chats, current] = await Promise.allSettled([pageConversations(), fetchUsage()])
  if (chats.status === 'fulfilled') {
    conversations.value = chats.value.items
    conversationsCursor.value = chats.value.nextCursor
    conversationsHasMore.value = chats.value.hasMore
    historyLoadError.value = false
    if (restoreLatest) {
      const id = latestChatToRestore(chats.value.items, {
        selectedId: selectedId.value,
        hasMessages: messages.value.length > 0,
        isSending: sending.value,
        explicitlyStartedNew,
        hasDraft: Boolean(input.value.trim()),
      })
      if (id) await select(id, true)
    }
  } else {
    historyLoadError.value = true
    ElMessage.error('历史会话加载失败，请重试；已有记录不会因此删除')
  }
  if (current.status === 'fulfilled') usage.value = current.value
  historyLoading.value = false
}
async function loadMoreConversations() {
  if (!conversationsHasMore.value || !conversationsCursor.value ||
      conversationsLoadingMore.value || historyLoading.value) return
  const cursor = conversationsCursor.value
  conversationsLoadingMore.value = true
  try {
    const page = await pageConversations(cursor)
    const existing = new Set(conversations.value.map(item => item.id))
    conversations.value = [...conversations.value, ...page.items.filter(item => !existing.has(item.id))]
    conversationsCursor.value = page.nextCursor
    conversationsHasMore.value = page.hasMore
  } catch { ElMessage.error('加载更多会话失败，请重试') }
  finally { conversationsLoadingMore.value = false }
}
async function renameSelectedConversation(item: Conversation) {
  if (sending.value || managingConversation.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话标题', '重命名会话', {
      inputValue: item.title,
      inputPattern: /\S/u,
      inputErrorMessage: '会话标题不能为空',
      inputValidator: (title: string) => title.trim().length <= 120 || '标题不能超过 120 个字符',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    managingConversation.value = true
    const title = String(value).trim()
    await renameConversation(item.id, title)
    conversations.value = conversations.value.map(c => c.id === item.id ? { ...c, title } : c)
    ElMessage.success('已重命名')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('重命名失败，请重试')
  } finally { managingConversation.value = false }
}
async function deleteSelectedConversation(item: Conversation) {
  if (sending.value || managingConversation.value || loadingOlder.value) return
  try {
    await ElMessageBox.confirm(
      '确认删除“' + item.title + '”？删除后不再显示此聊天，也不能继续在此会话发送消息。已经保存到健康中心等应用的数据不会删除。',
      '删除会话', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
        confirmButtonClass: 'chat-delete-confirm' },
    )
    managingConversation.value = true
    await deleteConversation(item.id)
    conversations.value = conversations.value.filter(c => c.id !== item.id)
    if (selectedId.value === item.id) newChat()
    ElMessage.success('会话已删除')
    void refresh()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败，会话仍然保留')
  } finally { managingConversation.value = false }
}
function onMessagesScroll() {
  const el = scroller.value
  if (!el) return
  showJumpToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight > 90
}
function bottom() {
  void nextTick(() => {
    if (scroller.value) {
      scroller.value.scrollTop = scroller.value.scrollHeight
      showJumpToBottom.value = false
    }
  })
}
// While streaming, let users scroll up to read previous messages.
watch(messages, () => { if (!prependingHistory && !showJumpToBottom.value) bottom() }, { deep: true })
async function select(id: string, automaticRestore = false) {
  if (sending.value || loadingOlder.value) return
  const requestId = ++activeSelectionRequest
  try {
    const [data, blocks] = await Promise.all([
      listMessages(id, undefined, HISTORY_PAGE_SIZE + 1),
      listMessageBlocks(id).catch(() => [] as AiMessageBlock[]),
    ])
    const canApply = shouldApplyLoadedConversation(
      conversations.value, id, automaticRestore, requestId, activeSelectionRequest, {
        selectedId: selectedId.value,
        hasMessages: messages.value.length > 0,
        isSending: sending.value,
        explicitlyStartedNew,
        hasDraft: Boolean(input.value.trim()),
      },
    )
    if (!canApply) return
    if (!automaticRestore) explicitlyStartedNew = false
    selectedId.value = id
    // Prevent a draft or one-time authorization leaking across conversations.
    input.value = ''
    selectedScopes.value = []
    preview.value = null
    chatPhoto.value = null
    mentionOpen.value = false
    hasOlder.value = data.length > HISTORY_PAGE_SIZE
    messages.value = data.slice(-HISTORY_PAGE_SIZE)
    blocksByMessage.value = groupBlocks(blocks)
    historyOpen.value = false
    streamError.value = ''
    bottom()
  } catch {
    if (requestId === activeSelectionRequest) ElMessage.error('无法加载聊天记录')
  }
}
async function loadOlder() {
  const id = selectedId.value
  const oldestId = messages.value.find(message => message.id > 0)?.id
  if (!id || oldestId === undefined || !hasOlder.value || loadingOlder.value || sending.value) return
  loadingOlder.value = true
  try {
    const olderPage = await listMessages(id, oldestId, HISTORY_PAGE_SIZE + 1)
    if (selectedId.value !== id) return
    hasOlder.value = olderPage.length > HISTORY_PAGE_SIZE
    const previousHeight = scroller.value?.scrollHeight ?? 0
    const previousTop = scroller.value?.scrollTop ?? 0
    prependingHistory = true
    messages.value = [...olderPage.slice(-HISTORY_PAGE_SIZE), ...messages.value]
    await nextTick()
    if (scroller.value) scroller.value.scrollTop =
      previousTop + scroller.value.scrollHeight - previousHeight
  } catch { ElMessage.error('加载更早消息失败，请重试') }
  finally {
    prependingHistory = false
    loadingOlder.value = false
  }
}
function newChat() {
  if (sending.value || loadingOlder.value) return
  explicitlyStartedNew = true
  ++activeSelectionRequest
  selectedId.value = null
  hasOlder.value = false
  messages.value = []
  blocksByMessage.value = {}
  input.value = ''
  selectedScopes.value = []
  preview.value = null
  chatPhoto.value = null
  mentionOpen.value = false
  showJumpToBottom.value = false
  streamError.value = ''
  historyOpen.value = false
}
function invalidatePreview() { preview.value = null }
function removeScope(scope: string) {
  selectedScopes.value = selectedScopes.value.filter(value => value !== scope)
  invalidatePreview()
}
function handleInput(value: string) {
  const mention = value.match(/@([^\s@]*)$/u)
  mentionOpen.value = Boolean(mention)
  mentionQuery.value = mention?.[1] ?? ''
}
function pickMention(item: ContextOption) {
  if (!selectedScopes.value.includes(item.value)) selectedScopes.value.push(item.value)
  input.value = input.value.replace(/@([^\s@]*)$/u, '@' + item.label + ' ')
  invalidatePreview()
  mentionOpen.value = false
}
async function showPreview() {
  if (!selectedScopes.value.length || sending.value || previewing.value) return
  previewing.value = true
  try {
    preview.value = await previewAiContext([...selectedScopes.value])
    previewVisible.value = true
    mentionOpen.value = false
  } catch { ElMessage.error('数据预览失败，请检查相关应用是否可用') }
  finally { previewing.value = false }
}
async function confirmShare() {
  if (!preview.value || confirming.value) return
  confirming.value = true
  try {
    const approved = await confirmAiContext(preview.value.previewId)
    previewVisible.value = false
    preview.value = null
    await send(approved.contextToken)
  } catch { ElMessage.error('授权已过期或确认失败，请重新预览') }
  finally { confirming.value = false }
}
function copy(content: string) {
  void navigator.clipboard?.writeText(content).then(() => ElMessage.success('已复制')).catch(() => ElMessage.error('复制失败'))
}
function retry() {
  const last = [...messages.value].reverse().find(m => m.role === 'user')
  if (last && !sending.value) { input.value = last.content; ElMessage.info('已填入上一条问题，请确认后重新发送') }
}
function describeStreamError(error: unknown): string {
  if (error instanceof AiStreamHttpError) {
    switch (error.status) {
      case 400: return '消息请求无效（HTTP 400），请重新发送。'
      case 401: return '聊天身份认证失败（HTTP 401），请检查登录状态。'
      case 403: return '没有权限使用聊天接口（HTTP 403）。'
      case 404: return '聊天接口未找到（HTTP 404），请检查反向代理的 API 路径。'
      case 429: return '聊天请求超过调用限额（HTTP 429），请稍后重试或检查额度。'
      case 502: case 503: case 504: return `模型服务或后端暂时不可用（HTTP ${error.status}），请稍后重试。`
      default: return `聊天请求失败（HTTP ${error.status}），请检查服务器日志。`
    }
  }
  if (error instanceof Error && error.name === 'AbortError') return '请求已取消。'
  return '聊天流式连接中断，请检查网络后重试。'
}
const explicitConfirm = /^(?:是的|对|嗯|确认|确认保存|确认录入|保存|保存吧|保存一下|好的|可以|没错|是|帮我保存到健康中心)$/u
async function confirmPreviousHealthDraft(content: string) {
  if (!selectedId.value || sending.value) {
    ElMessage.warning('当前没有可确认的饮食记录，请先描述日期、餐次与热量')
    return
  }
  const previousMessages = [...messages.value]
  const pendingId = -Date.now()
  const conversation = selectedId.value
  sending.value = true
  streamError.value = ''
  input.value = ''
  messages.value.push(
    { id: pendingId, role: 'user', content, createdAt: new Date().toISOString() },
    { id: pendingId - 1, role: 'assistant', content: '正在核实健康中心记录，请稍候…', createdAt: new Date().toISOString() },
  )
  bottom()
  try {
    const result = await confirmPendingHealthDraft(conversation, content)
    // The backend returns a receipt only after the authorized draft was committed.
    const assistant = messages.value[messages.value.length - 1]!
    assistant.id = result.messageId
    assistant.content = result.content
    const [latest, blocks] = await Promise.allSettled([
      listMessages(conversation, undefined, HISTORY_PAGE_SIZE + 1),
      listMessageBlocks(conversation),
    ])
    if (latest.status === 'fulfilled') {
      messages.value = latest.value.slice(-HISTORY_PAGE_SIZE)
      hasOlder.value = latest.value.length > HISTORY_PAGE_SIZE
    }
    if (blocks.status === 'fulfilled') blocksByMessage.value = groupBlocks(blocks.value)
    if (result.status !== 'SAVED' && result.status !== 'ALREADY_SAVED')
      ElMessage.info(result.content)
    try { await refresh() } catch { /* the server has already committed; never retry */ }
  } catch {
    // In case of uncertain HTTP outcome, never claim a write, and do not re-POST.
    streamError.value = '保存结果未核实，请先到健康中心查看，避免重复提交；也可重新打开会话查看服务器回执。'
    messages.value = previousMessages
    input.value = content
  } finally {
    sending.value = false
    bottom()
  }
}
async function send(contextToken?: string) {
  const content = input.value.trim() || (chatPhoto.value ? '请识别照片中的食物，分析热量并记录这顿饮食' : '')
  if (!content || sending.value || content.length > 4000) return
  const hasHealthCard = Object.values(blocksByMessage.value).some(blocks =>
    blocks.some(block => block.type === 'wellness_draft'))
  if (explicitConfirm.test(content) && !chatPhoto.value && !selectedScopes.value.length &&
      (hasHealthCard || /保存|确认录入/u.test(content))) {
    await confirmPreviousHealthDraft(content)
    return
  }
  if (chatPhoto.value && (content.length > 1500 ||
      selectedScopes.value.some(scope => scope !== 'wellness'))) {
    ElMessage.warning('食物照片只能用于健康记录，请缩短描述并移除其他应用引用后重试')
    return
  }
  // A natural-language read request needs explicit consent, even without an @健康 mention.
  // Check BEFORE the meal-writing intent regex: "没有录入" is a query, not a write.
  if (!contextToken && !chatPhoto.value && selectedScopes.value.length === 0 &&
      isWellnessReadQuery(content)) {
    selectedScopes.value = ['wellness']
    invalidatePreview()
    await showPreview()
    return
  }
  const writeVerb = /(?:记录|录入|录人|导入|写入|归档|添加|新增|保存|记下|记一下|帮我记|记一笔|存入)/u.test(content)
  const foodContext = /(?:早饭|午饭|晚饭|早餐|午餐|晚餐|加餐|饮食|食物|热量|卡路里|吃了|喝了|这顿|我吃|今天吃)/u.test(content)
  const directFoodQuantity = /(?:记|记录|录入|录人|添加|新增|保存|记下)(?:一下|一笔|入)?\s*(?:一个|一份|一碗|一杯|两个|[0-9]+(?:g|克|ml|毫升))/u.test(content)
  const notTechnicalOrOther = !/(?:如何实现|怎么开发|如何设计|为什么不能|记录日志|错误日志|会议记录|记录会议|记录任务|添加任务|添加待办|保存笔记|添加笔记)/u.test(content)
  const healthWrite = !isWellnessReadQuery(content) && writeVerb && notTechnicalOrOther &&
    (foodContext || directFoodQuantity || selectedScopes.value.includes('wellness'))
  // Short follow-ups like "帮我录入一下" or "生成一下卡片" depend on
  // the selected conversation's real user meal description, not model promises.
  const hasRecentMeal = messages.value.slice(-40).some(m => m.role === 'user' &&
    /(?:早餐|早饭|早上|午餐|午饭|中午|晚餐|晚饭|晚上|今晚|加餐|夜宵)/u.test(m.content) &&
    /(?:米饭|炒菜|炒肉|馄饨|混沌|米线|鸡腿|面条|鸡蛋|牛奶|酸奶|土豆|面包|豆腐|青菜|排骨|饺子|饭|肉|菜|吃)/u.test(m.content))
  const contextualMealCard = !isWellnessReadQuery(content) && isMealCardRequest(content, hasRecentMeal)
  if (content.length <= 1500 && (healthWrite || contextualMealCard || chatPhoto.value) &&
      (selectedScopes.value.length === 0 ||
       selectedScopes.value.every(s => s === 'wellness'))) {
    await prepareInlineDiet(content.replace(/^@(健康)\s*/u, ''))
    return
  }
  if (selectedScopes.value.length > 0 && !contextToken) { await showPreview(); return }
  if (selectedScopes.value.length === 0 && contextToken) return
  const scopes = [...selectedScopes.value]
  input.value = ''
  selectedScopes.value = []
  invalidatePreview()
  mentionOpen.value = false
  ++activeSelectionRequest // A pending automatic history load must not rebind this send.
  sending.value = true
  streamError.value = ''
  const id = -Date.now()
  messages.value.push(
    { id, role: 'user', content, createdAt: new Date().toISOString() },
    { id: id - 1, role: 'assistant', content: '', createdAt: new Date().toISOString() },
  )
  bottom()
  const reply = messages.value[messages.value.length - 1]!
  controller = new AbortController()
  let completed = false
  let eventError = false
  try {
    await streamChat(selectedId.value, content, ({ event, data }) => {
      if (event === 'meta') selectedId.value = String(data.conversationId)
      if (event === 'delta') reply.content += String(data.text ?? '')
      if (event === 'done') completed = true
      if (event === 'error') {
        eventError = true
        const status = Number(data.status)
        streamError.value = status === 429
          ? data.quotaSource === 'provider'
            ? '模型服务商返回 HTTP 429：可能限流或 API 余额不足，请检查服务商账户后重试。'
            : 'PRP 本月 AI 调用配额已用完（HTTP 429），请查看本月用量。'
          : status === 503
            ? 'AI 服务暂时不可用（HTTP 503），请稍后重试。'
            : '生成失败，请稍后重试。'
      }
    }, controller.signal, scopes, contextToken)
    if (!completed) throw new Error('Stream interrupted')
  } catch (error) {
    if (!eventError) streamError.value = describeStreamError(error)
  } finally {
    sending.value = false
    controller = null
    await refresh()
    if (selectedId.value) {
      try {
        const [latest, blocks] = await Promise.all([
          listMessages(selectedId.value, undefined, HISTORY_PAGE_SIZE + 1),
          listMessageBlocks(selectedId.value).catch(() => [] as AiMessageBlock[]),
        ])
        hasOlder.value = latest.length > HISTORY_PAGE_SIZE
        messages.value = latest.slice(-HISTORY_PAGE_SIZE)
        blocksByMessage.value = groupBlocks(blocks)
      } catch { /* preserve partial streamed content if refresh fails */ }
    }
    bottom()
  }
}
onMounted(() => { void refresh(true); void loadSettings() })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <AppLayout>
    <div class="prp-chat-workspace">
      <aside class="chat-desktop-sidebar" aria-label="桌面聊天会话侧边栏">
        <ChatConversationPanel :conversations="conversations" :selected-id="selectedId"
          :loading="historyLoading" :loading-more="conversationsLoadingMore"
          :has-more="conversationsHasMore" :error="historyLoadError"
          :busy="sending || managingConversation || loadingOlder" :usage="usage"
          @select="select" @new-chat="newChat" @rename="renameSelectedConversation"
          @remove="deleteSelectedConversation" @load-more="loadMoreConversations"
          @retry="refresh()" />
      </aside>
    <div class="prp-chat-screen">
      <header class="prp-chat-header">
        <div class="chat-header-left">
          <button class="chat-icon-button chat-mobile-menu" aria-label="打开历史会话" title="历史会话" @click="historyOpen = true"><el-icon><Menu /></el-icon></button>
          <div class="chat-brand">
            <div class="chat-title">PRP 助手 <el-icon class="chat-brand-icon"><ArrowDown /></el-icon></div>
            <div class="chat-subtitle">{{ currentProviderName }} · {{ model }}</div>
          </div>
        </div>
        <div class="chat-header-actions">
          <el-popover v-if="settings" placement="bottom-end" :width="290" trigger="click">
            <template #reference>
              <button class="chat-icon-button" title="切换模型" aria-label="切换模型"><el-icon><Setting /></el-icon></button>
            </template>
            <div class="model-panel">
              <strong>聊天模型</strong>
              <label>服务商</label>
              <el-select :model-value="provider" :disabled="sending || savingModel" @change="changeProvider">
                <el-option v-for="item in settings.providers" :key="item.id" :value="item.id" :label="item.name" />
              </el-select>
              <label>模型</label>
              <el-select :model-value="model" :disabled="sending || savingModel" filterable allow-create default-first-option @change="changeModel">
                <el-option v-for="name in models" :key="name" :value="name" :label="name" />
              </el-select>
              <RouterLink to="/me/ai-settings">配置 API Key</RouterLink>
            </div>
          </el-popover>
          <button class="chat-icon-button" aria-label="新对话" title="新对话" :disabled="sending" @click="newChat"><el-icon><Edit /></el-icon></button>
        </div>
      </header>

      <div ref="scroller" class="prp-chat-messages" role="log" aria-label="聊天消息" @scroll.passive="onMessagesScroll">
        <div v-if="hasOlder && selectedId" class="chat-history-pagination">
          <button type="button" :disabled="loadingOlder || sending" @click="loadOlder">
            {{ loadingOlder ? '正在加载…' : '加载更早的消息' }}
          </button>
        </div>
        <section v-if="isEmpty" class="chat-welcome">
          <div class="chat-welcome-icon"><el-icon><ChatDotRound /></el-icon></div>
          <h1>今天有什么可以帮你？</h1>
          <p>我是 PRP 助手，可以陪你学习、规划任务和管理生活。</p>
          <div class="chat-suggestions">
            <button @click="input = '帮我制定今天的学习计划'">帮我制定学习计划</button>
            <button @click="input = '@健康 分析一下今天的饮食'; selectedScopes = ['wellness']">分析今天的饮食</button>
            <button @click="input = '@任务 今天有什么待办？'; selectedScopes = ['tasks']">看看今天的待办</button>
            <button @click="input = '@刷题 我最近练习得怎么样？'; selectedScopes = ['practice']">查看刷题统计</button>
            <button @click="input = '@财务 本月支出情况如何？'; selectedScopes = ['finance']">分析本月收支</button>
          </div>
        </section>
        <div v-for="(message, index) in messages" :key="message.id || index" class="chat-message"
          :class="message.role === 'user' ? 'chat-message-user' : 'chat-message-assistant'">
          <div v-if="message.role === 'assistant'" class="chat-ai-mark"><el-icon><ChatDotRound /></el-icon></div>
          <div class="chat-message-content">
            <div v-if="message.role === 'assistant' && !message.content" class="chat-typing">正在思考 <span>···</span></div>
            <div v-else-if="message.role === 'assistant'" class="markdown-body" v-html="renderSafeMarkdown(message.content)" />
            <div v-else class="chat-user-text">{{ message.content }}</div>
            <template v-for="(block, i) in blocksByMessage[message.id] ?? []" :key="message.id + '-' + i">
              <AiNavigationCard v-if="block.type === 'navigation'" :block="block" />
              <AiActionLink v-else-if="block.type === 'wellness_draft'"
                :draft-id="block.route" :refresh-key="actionRevision" @open="openAction" />
            </template>
            <div v-if="message.role === 'assistant' && message.content" class="chat-message-actions">
              <button title="复制回复" aria-label="复制回复" @click="copy(message.content)"><el-icon><CopyDocument /></el-icon></button>
              <button v-if="index === messages.length - 1 && !sending" title="重新提问" aria-label="重新提问" @click="retry"><el-icon><RefreshRight /></el-icon></button>
            </div>
          </div>
        </div>
        <p v-if="streamError" class="chat-error" role="alert">{{ streamError }}</p>
      </div>

      <AiActionDialog v-model="actionDialogVisible" :draft-id="activeActionId"
        @changed="actionRevision++" />
      <div class="prp-chat-footer">
        <div class="chat-footer-inner">
          <button v-if="showJumpToBottom" type="button" class="chat-jump-bottom" @click="bottom">
            <el-icon><ArrowDown /></el-icon> 跳到最新消息
          </button>
          <div v-if="selectedScopes.length" class="chat-context-chips">
            <span v-for="scope in selectedScopes" :key="scope" class="chat-context-chip">
              @{{ optionByValue(scope)?.label }}
              <button :aria-label="'移除' + optionByValue(scope)?.label + '引用'" @click="removeScope(scope)"><el-icon><Close /></el-icon></button>
            </span>
            <span class="chat-private-note">发送前预览 · 仅本次授权</span>
          </div>
          <div v-if="mentionOpen" class="chat-mention-menu" role="listbox" aria-label="选择 PRP 应用引用">
            <div class="mention-heading">引用 PRP 应用数据</div>
            <button v-for="item in filteredOptions" :key="item.value" role="option" aria-selected="false" @click="pickMention(item)">
              <strong>@{{ item.label }}</strong><span>{{ item.hint }}</span>
            </button>
            <div v-if="filteredOptions.length === 0" class="mention-empty">暂无匹配的可授权应用</div>
            <div class="mention-hint">引用其他应用需要一次性只读授权；饮食记录在聊天卡片中确认后才写入。</div>
          </div>
          <div v-if="chatPhoto" class="chat-photo-preview">
            <span>📷 {{ chatPhoto.name }}</span>
            <button type="button" aria-label="移除照片" @click="chatPhoto = null">移除</button>
          </div>
          <div class="chat-composer">
            <el-input v-model="input" type="textarea" class="chat-input" resize="none" :autosize="{ minRows: 1, maxRows: 5 }"
              maxlength="4000" :disabled="sending" placeholder="询问 PRP 助手，输入 @ 引用应用…"
              @input="handleInput" @keydown.enter.exact.prevent="send()" @keydown.esc="mentionOpen = false" />
            <div class="chat-compose-tools">
              <div class="chat-compose-left">
                <button type="button" aria-label="引用 PRP 应用" title="引用应用" @click="mentionOpen = !mentionOpen; mentionQuery = ''"><el-icon><Plus /></el-icon></button>
                <button type="button" class="chat-at" @click="mentionOpen = !mentionOpen; mentionQuery = ''">@ 应用</button>
                <input ref="photoInput" type="file" accept="image/jpeg,image/png,image/webp"
                  class="chat-photo-input" aria-label="添加食物照片" @change="photoSelected" />
                <button type="button" class="chat-at" aria-label="添加食物照片" @click="photoInput?.click()">📷 食物照片</button>
              </div>
              <button type="button" class="chat-send" aria-label="发送消息" :disabled="(!input.trim() && !chatPhoto) || sending || previewing" @click="send()">
                <el-icon><Promotion /></el-icon>
              </button>
            </div>
          </div>
          <div class="chat-disclaimer">PRP 助手可能出错，重要信息请核实。</div>
        </div>
      </div>
    </div>
    </div>

    <el-drawer v-model="historyOpen" direction="ltr" :size="'min(86vw, 320px)'"
      :with-header="false" append-to-body class="prp-chat-history-drawer">
      <ChatConversationPanel mobile :conversations="conversations" :selected-id="selectedId"
        :loading="historyLoading" :loading-more="conversationsLoadingMore"
        :has-more="conversationsHasMore" :error="historyLoadError"
        :busy="sending || managingConversation || loadingOlder" :usage="usage"
        @select="select" @new-chat="newChat" @rename="renameSelectedConversation"
        @remove="deleteSelectedConversation" @load-more="loadMoreConversations"
        @close="historyOpen = false" @retry="refresh()" />
    </el-drawer>

    <el-dialog v-model="previewVisible" title="确认本次共享的数据" width="min(580px, 95vw)" append-to-body>
      <p class="chat-consent-explain">以下是已选数据域的最小化摘要预览。确认后，PRP 助手可在当前这一条消息中按需查询所选模块的其他记录（包括任务标题、账目日期与金额；仅在选择「身体指标」时包含体重记录等），并将查询结果发送给 {{ currentProviderName }}。不会修改数据；如不愿共享该模块其他记录，请取消授权。</p>
      <pre class="chat-preview-data">{{ JSON.stringify(preview?.data ?? {}, null, 2) }}</pre>
      <p class="chat-consent-explain">授权令牌三分钟内有效、只能使用一次。工具调用只限已选模块和当前账户；完整查询内容不另存到聊天历史，但模型回复可能引用它。</p>
      <template #footer>
        <el-button @click="previewVisible = false">取消</el-button>
        <el-button type="primary" :loading="confirming" @click="confirmShare">允许仅本次发送</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>

<style scoped>
.prp-chat-workspace{display:flex;flex:1;min-height:0;min-width:0;height:100%}
.chat-desktop-sidebar{display:block;flex:0 0 270px;min-height:0;border-right:1px solid #e8eef5;background:#fbfcff}
.chat-mobile-menu{display:none!important}
.prp-chat-screen{display:flex;flex:1;flex-direction:column;min-width:0;min-height:0;height:100%;position:relative;background:#fff;color:#1e293b}
.prp-chat-header{height:66px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 27px;border-bottom:1px solid #edf1f6;background:#fff}
.chat-header-left,.chat-header-actions{display:flex;align-items:center;gap:13px;min-width:0}
.chat-icon-button{display:inline-grid;place-items:center;width:38px;height:38px;flex:none;border:0;background:transparent;border-radius:11px;color:#62738b;font-size:20px;cursor:pointer}
.chat-icon-button:hover{background:#f1f5fb}
.chat-icon-button:disabled{opacity:.4;cursor:not-allowed}
.chat-brand{min-width:0}.chat-title{display:flex;align-items:center;gap:4px;font-size:16px;font-weight:700;color:#20344d}.chat-brand-icon{font-size:11px;color:#9ba8b7}
.chat-subtitle{font-size:11px;color:#91a0b2;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.prp-chat-messages{flex:1;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch;touch-action:pan-y;overscroll-behavior:contain;padding:28px max(24px,calc((100% - 800px)/2)) 24px;scrollbar-gutter:stable}
.chat-welcome{padding:clamp(45px,13vh,135px) 6px 20px;text-align:center}
.chat-welcome-icon{display:grid;place-items:center;margin:0 auto 20px;width:58px;height:58px;border-radius:19px;background:#eef4ff;color:#4a83e8;font-size:27px}
.chat-welcome h1{margin:0;font-size:clamp(22px,3vw,28px);font-weight:700;letter-spacing:-.5px}.chat-welcome p{color:#8592a4;font-size:14px;line-height:1.8}
.chat-suggestions{display:grid;grid-template-columns:1fr 1fr;gap:11px;max-width:530px;margin:31px auto 0}
.chat-suggestions button{text-align:left;border:1px solid #e9edf5;border-radius:14px;padding:15px 17px;color:#566b86;background:#fff;cursor:pointer}
.chat-suggestions button:hover{background:#f6f9ff;border-color:#bfd3f8}
.chat-message{display:flex;gap:12px;margin-bottom:25px;align-items:flex-start;min-width:0}
.chat-message-user{justify-content:flex-end}
.chat-message-content{flex:1 1 0;min-width:0;max-width:100%;line-height:1.85;font-size:15px;overflow-wrap:anywhere}
.chat-message-user .chat-message-content{flex:0 1 auto}
.chat-message-user .chat-message-content{max-width:84%;border-radius:18px 18px 4px 18px;background:#edf3fc;padding:10px 16px}
.chat-user-text{white-space:pre-wrap}
.chat-ai-mark{display:grid;place-items:center;flex:none;width:28px;height:28px;border-radius:10px;background:#eaf1ff;color:#3477e6;font-size:15px;margin-top:3px}
.chat-message-actions{display:flex;align-items:center;gap:8px;margin-top:8px}
.chat-message-actions button{border:0;background:transparent;color:#9aa8b8;cursor:pointer;font-size:14px;padding:5px;border-radius:7px}
.chat-message-actions button:hover{color:#3477e6;background:#f0f5ff}
.chat-typing{color:#8493a5}.chat-typing span{letter-spacing:4px;animation:chatPulse 1.2s infinite}
@keyframes chatPulse{50%{opacity:.3}}
.chat-error{color:#b45309;background:#fff7ed;padding:12px 14px;border-radius:12px;font-size:13px}
.prp-chat-footer{flex:none;background:linear-gradient(to bottom,rgba(255,255,255,.92),#fff 16%);padding:10px 22px 12px}
.chat-footer-inner{position:relative;max-width:800px;margin:0 auto}
.chat-jump-bottom{position:absolute;top:-49px;right:0;display:flex;align-items:center;gap:5px;padding:8px 12px;border:1px solid #d5e1f1;border-radius:20px;background:#fff;color:#3975c9;font-size:12px;box-shadow:0 3px 12px #223f681a;cursor:pointer;z-index:4}
.chat-composer{border:1px solid #dfe6ef;box-shadow:0 5px 24px #233f6510;border-radius:22px;padding:12px 15px 9px;background:white}
.chat-composer:focus-within{border-color:#9abcf2}
.chat-compose-tools{display:flex;align-items:center;justify-content:space-between;margin-top:3px}
.chat-compose-left{display:flex;align-items:center;gap:3px}
.chat-compose-left button{border:0;background:transparent;color:#7c8b9e;cursor:pointer;height:32px;border-radius:10px;padding:0 8px}
.chat-compose-left button:hover{background:#f2f6fe;color:#3777dc}.chat-at{font-size:12px}
.chat-send{display:grid;place-items:center;width:35px;height:35px;background:#4386f3;color:white;border:0;border-radius:12px;cursor:pointer;font-size:18px}
.chat-send:disabled{background:#c6d5ed;cursor:not-allowed}
.chat-context-chips{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-bottom:8px}
.chat-context-chip{display:inline-flex;align-items:center;gap:7px;padding:5px 8px 5px 11px;border:1px solid #bcd4fc;border-radius:12px;background:#ecf4ff;color:#356fc8;font-size:12px}
.chat-context-chip button{border:0;background:transparent;color:inherit;cursor:pointer;padding:0;display:grid;place-items:center}
.chat-private-note{font-size:11px;color:#91a0b3}
.chat-disclaimer{text-align:center;color:#a1acba;font-size:11px;margin:9px 0 0}
.chat-mention-menu{position:absolute;bottom:calc(100% + 9px);left:0;width:min(380px,100%);max-height:300px;overflow-y:auto;background:white;border:1px solid #e1e9f4;border-radius:15px;padding:7px;box-shadow:0 12px 35px #1c365426;z-index:8}
.mention-heading{padding:8px 10px;font-size:12px;color:#8492a6}
.chat-mention-menu button{display:flex;flex-direction:column;align-items:flex-start;gap:2px;width:100%;border:0;border-radius:9px;background:white;padding:10px 12px;cursor:pointer;text-align:left}
.chat-mention-menu button:hover{background:#f2f7ff}
.chat-mention-menu button strong{font-size:13px;color:#375b94}.chat-mention-menu button span,.mention-hint,.mention-empty{font-size:11px;color:#95a1b0}
.mention-hint,.mention-empty{padding:8px 10px}
.model-panel{display:grid;gap:9px;padding:5px}.model-panel label{font-size:12px;color:#6f8095}.model-panel a{font-size:12px;color:#3477e6;margin-top:5px}
.chat-history{height:100%;display:flex;flex-direction:column;gap:15px}.chat-history-top{display:flex;justify-content:space-between;align-items:center}.chat-history-top h2{font-size:18px;margin:0}
.chat-new-button{display:flex;align-items:center;gap:9px;width:100%;padding:11px 14px;background:#eef5ff;border:1px solid #d8e7ff;color:#2964bd;border-radius:12px;cursor:pointer}
.chat-history-list{flex:1;overflow:auto}.chat-history-item{display:flex;align-items:center;gap:10px;width:100%;margin-bottom:5px;padding:12px 10px;border:0;border-radius:10px;background:#fff;color:#5b6b80;text-align:left;cursor:pointer}
.chat-history-item span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.chat-history-item.selected,.chat-history-item:hover{background:#ecf4ff;color:#276bce}
.chat-history-usage,.chat-history-empty{font-size:12px;color:#8795a8}
.chat-history-load-error{display:grid;gap:8px;font-size:12px;color:#a0552f}
.chat-history-load-error button{justify-self:start;border:1px solid #d5e1f1;border-radius:8px;background:#fff;padding:6px 11px;color:#3477e6;cursor:pointer}.chat-preview-data{max-height:35vh;overflow:auto;background:#f4f7fb;padding:15px;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
.chat-history-pagination{display:flex;justify-content:center;padding:10px 0 20px}
.chat-history-pagination button{border:1px solid #d7e4f3;border-radius:12px;padding:8px 15px;background:#fff;color:#4578b7;font-size:12px;cursor:pointer}
.chat-history-pagination button:disabled{opacity:.5;cursor:wait}
.chat-consent-explain{color:#64748b;font-size:12px;line-height:1.8}
:deep(.chat-input .el-textarea__inner){border:0;box-shadow:none!important;resize:none;background:transparent;padding:2px 0 5px;line-height:1.8;font-size:14px}
:deep(.markdown-body p){margin:0 0 10px}:deep(.markdown-body p:last-child){margin-bottom:0}
:deep(.markdown-body h2),:deep(.markdown-body h3),:deep(.markdown-body h4){margin:12px 0 8px;line-height:1.4}
:deep(.markdown-body ul),:deep(.markdown-body ol){padding-left:23px;margin:8px 0}
:deep(.markdown-body li){margin-bottom:4px}:deep(.markdown-body code){padding:2px 5px;background:#f1f5f9;color:#315b8f;border-radius:5px;font-size:13px}
:deep(.markdown-body .markdown-code){background:#172334;color:#e2e8f0;border-radius:12px;padding:15px;overflow:auto;font-size:13px;line-height:1.65}
:deep(.markdown-body .markdown-code code){background:transparent;color:inherit;padding:0}
:deep(.markdown-body .markdown-table-wrap){max-width:100%;width:100%;overflow-x:auto;margin:12px 0;-webkit-overflow-scrolling:touch}
:deep(.markdown-body){max-width:100%;min-width:0;overflow-wrap:anywhere}
:deep(.markdown-body img),:deep(.markdown-body pre){max-width:100%}
:deep(.markdown-body img){height:auto}
:deep(.markdown-body table){border-collapse:collapse;min-width:330px;font-size:13px}
:deep(.markdown-body th),:deep(.markdown-body td){padding:8px 10px;border:1px solid #dbe4f0;text-align:left}
:deep(.markdown-body th){background:#f4f7fc}
:deep(.markdown-body blockquote){margin:10px 0;padding:6px 14px;border-left:3px solid #b4c7e7;color:#6b7b90}
.chat-photo-input{display:none}
.chat-photo-preview{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:7px 10px;margin-bottom:6px;background:#eff6ff;border-radius:9px;color:#1d4ed8;font-size:12px}
.chat-photo-preview span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chat-photo-preview button{border:none;background:transparent;color:#375bb2;cursor:pointer}
@media(max-width:860px){
  .chat-desktop-sidebar{display:none}
  .chat-mobile-menu{display:inline-grid!important}
  .prp-chat-header{height:54px;padding:0 10px}
  .prp-chat-messages{padding:19px 14px}
  .chat-message{gap:8px;margin-bottom:19px}
  .chat-message-content{font-size:14px}
  .chat-message-user .chat-message-content{max-width:87%}
  .chat-ai-mark{width:25px;height:25px}
  .prp-chat-footer{padding:8px 10px 10px}
  .chat-composer{border-radius:18px;padding:8px 12px 7px}
  .chat-welcome{padding-top:clamp(36px,10vh,90px)}
  .chat-suggestions{gap:8px}
  .chat-suggestions button{padding:12px 11px;font-size:12px}
  .chat-disclaimer{margin-top:6px;font-size:10px}
  :deep(.chat-input .el-textarea__inner){font-size:16px}
}
@media(prefers-reduced-motion:reduce){.chat-typing span{animation:none}}
</style>
