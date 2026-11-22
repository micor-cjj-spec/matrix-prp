<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/layouts/AppLayout.vue'
import { fetchRecords, type RecordItem } from '@/api/records'
import { createTask, fetchTasks, type TaskItem } from '@/api/tasks'
import { fetchReviews, type ReviewItem } from '@/api/reviews'
import {
  changePersonalGoalStatus, confirmPersonalMemory, createPersonalGoal,
  erasePersonalMemory, fetchConfirmedMemories, fetchMemoryCandidates,
  fetchPersonalGoalContext, fetchPersonalGoals, fetchPrivateMemories, invalidatePersonalMemory,
  proposePersonalMemory, replacePersonalMemory, fetchMemoryChatSource, fetchNormalMemoryHistory,
  proposeGoalTaskLink, proposeGoalReviewLink,
  type ChatEvidenceSource, type GoalStatus, type MemoryPredicate, type MemorySensitivity,
  previewGoalModelSharing, confirmGoalModelSharing, suggestGoalModelAdvice,
  type PlanningModelReview, type PlanningModelAdvice, type PlanningModelProposal,
  type PersonalGoal, type PersonalGoalLink, type PersonalMemory,
} from '@/api/personalOs'

const auth = useAuthStore()
const activeTab = ref<'goals' | 'memory' | 'timeline'>('goals')
const loading = ref(false)
const actionBusy = ref(false)
const serviceError = ref('')
const goals = ref<PersonalGoal[]>([])
const candidates = ref<PersonalMemory[]>([])
const memories = ref<PersonalMemory[]>([])
const memoryLoaded = ref(false)
let loadGeneration = 0
let goalContextGeneration = 0
const privateFacts = ref<PersonalMemory[]>([])
const privateOpen = ref(false)
const privateLoading = ref(false)
let privateRequestGeneration = 0
const normalHistory = ref<PersonalMemory[]>([])
const normalHistoryOpen = ref(false)
const normalHistoryBusy = ref(false)
let normalHistoryGeneration = 0

async function toggleNormalHistory(forceRefresh = false) {
  if (normalHistoryOpen.value && !forceRefresh) {
    ++normalHistoryGeneration
    clearChatSource()
    normalHistoryOpen.value = false
    normalHistory.value = []
    normalHistoryBusy.value = false
    return
  }
  const generation = ++normalHistoryGeneration
  const identity = auth.token
  normalHistoryBusy.value = true
  try {
    const items = await fetchNormalMemoryHistory()
    if (generation !== normalHistoryGeneration || identity !== auth.token
        || activeTab.value !== 'memory') return
    normalHistory.value = items
    normalHistoryOpen.value = true
  } catch {
    if (generation === normalHistoryGeneration) {
      normalHistoryOpen.value = false
      normalHistory.value = []
      ElMessage.error('历史记忆加载失败，请检查当前账号权限')
    }
  } finally {
    if (generation === normalHistoryGeneration) normalHistoryBusy.value = false
  }
}

const records = ref<RecordItem[]>([])
const timelineDomain = ref('life')
const selectedGoalId = ref<number | null>(null)
const context = ref<PersonalGoalLink[]>([])
const contextLoading = ref(false)
const sharePersonalFacts = ref(false)
const adviceReview = ref<PlanningModelReview | null>(null)
const adviceOutput = ref<PlanningModelAdvice | null>(null)
const adviceBusy = ref(false)
let adviceGeneration = 0
const taskDraftOpen = ref(false)
const taskDraftSaving = ref(false)
const taskDraftGoalId = ref<number | null>(null)
const taskDraftOwnerToken = ref<string | null>(null)
const taskDraftForm = reactive({ title: '', description: '', priority: 'medium' })
// A task exists independently before the owner explicitly confirms its goal relation.
const taskLinkPending = ref<{
  goalId: number; taskId: number; ownerToken: string; requestKey: string
  source: 'new' | 'existing'
} | null>(null)
const taskLinkBusy = ref(false)
// Existing tasks must be fetched only after the owner opens the picker.
// Clear both loaded titles and selection on account, goal, tab or route changes.
const taskPickerOpen = ref(false)
const taskPickerBusy = ref(false)
const taskPickerTasks = ref<TaskItem[]>([])
const taskPickerTaskId = ref<number | null>(null)
const taskPickerGoalId = ref<number | null>(null)
const taskPickerOwnerToken = ref<string | null>(null)
let taskPickerGeneration = 0
// Review sources are also fetched only after deliberate owner selection.
const reviewPickerOpen = ref(false)
const reviewPickerBusy = ref(false)
const reviewPickerReviews = ref<ReviewItem[]>([])
const reviewPickerReviewId = ref<number | null>(null)
const reviewPickerGoalId = ref<number | null>(null)
const reviewPickerOwnerToken = ref<string | null>(null)
let reviewPickerGeneration = 0
const reviewLinkPending = ref<{
  goalId: number; reviewId: number; ownerToken: string; requestKey: string
} | null>(null)
const reviewLinkBusy = ref(false)

function clearReviewPicker() {
  ++reviewPickerGeneration
  reviewPickerOpen.value = false
  reviewPickerBusy.value = false
  reviewPickerReviews.value = []
  reviewPickerReviewId.value = null
  reviewPickerGoalId.value = null
  reviewPickerOwnerToken.value = null
}
function clearPendingReviewLink() {
  reviewLinkPending.value = null
}

function clearTaskPicker() {
  ++taskPickerGeneration
  taskPickerOpen.value = false
  taskPickerBusy.value = false
  taskPickerTasks.value = []
  taskPickerTaskId.value = null
  taskPickerGoalId.value = null
  taskPickerOwnerToken.value = null
}

function clearPendingTaskLink() {
  taskLinkPending.value = null
}

function clearTaskDraft() {
  taskDraftOpen.value = false
  taskDraftGoalId.value = null
  taskDraftOwnerToken.value = null
  taskDraftForm.title = ''
  taskDraftForm.description = ''
  taskDraftForm.priority = 'medium'
}

function clearPlanningAdvice() {
  ++adviceGeneration
  adviceReview.value = null
  adviceOutput.value = null
  adviceBusy.value = false
  clearTaskDraft()
  clearPendingTaskLink()
  clearTaskPicker()
  clearReviewPicker()
  clearPendingReviewLink()
}
watch(sharePersonalFacts, clearPlanningAdvice)
const correctionTarget = ref<PersonalMemory | null>(null)
const correctionText = ref('')
const correctionRequestKey = ref('')
const correctionOpen = ref(false)
const chatSourceOpen = ref(false)
const chatSourceBusy = ref(false)
const chatSourceError = ref('')
const chatSource = ref<ChatEvidenceSource | null>(null)
let chatSourceGeneration = 0

function clearChatSource() {
  ++chatSourceGeneration
  chatSourceOpen.value = false
  chatSourceBusy.value = false
  chatSourceError.value = ''
  chatSource.value = null
}
async function openChatSource(item: PersonalMemory) {
  if (item.sourceType !== 'CHAT_MESSAGE' || !item.sourceRef) return
  clearChatSource()
  const generation = chatSourceGeneration
  chatSourceOpen.value = true
  chatSourceBusy.value = true
  try {
    const data = await fetchMemoryChatSource(item.id)
    if (generation === chatSourceGeneration) chatSource.value = data
  } catch {
    if (generation === chatSourceGeneration)
      chatSourceError.value = '聊天来源不可用，可能已被删除或失去访问权限。'
  } finally {
    if (generation === chatSourceGeneration) chatSourceBusy.value = false
  }
}

function requestKey(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`
}

const goalForm = reactive({
  title: '', description: '', domain: 'career', priority: 'medium' as PersonalGoal['priority'],
  successCriteria: '', targetDate: '', requestKey: requestKey('goal'),
})
const memoryForm = reactive({
  predicate: 'PREFERS' as MemoryPredicate,
  text: '', sensitivity: 'RESTRICTED' as MemorySensitivity,
  requestKey: requestKey('memory'),
})

const goalStatuses: Record<GoalStatus, string> = {
  PLANNED: '待开始', ACTIVE: '进行中', PAUSED: '已暂停',
  COMPLETED: '已完成', CANCELLED: '已取消',
}
const relationLabels: Record<string, string> = {
  PURSUES: '追求目标', ADVANCES: '推进目标', NEEDS_SKILL: '需要技能',
  DECLARES_SKILL: '自报技能', PREFERS: '个人偏好',
  HAS_BACKGROUND: '背景信息', HAS_EVENT_RECORD: '经历记录',
  USES_RESOURCE_RECORD: '资源记录', EVALUATES: '复盘评价',
}
const selectedGoal = computed(() => goals.value.find(g => g.id === selectedGoalId.value) ?? null)
const timeline = computed(() => [...records.value]
  .sort((a, b) => b.recordDate.localeCompare(a.recordDate) || b.id - a.id)
  .slice(0, 40))

function describeMemory(item: PersonalMemory) {
  if (item.objectType === 'LITERAL') return item.objectValue ?? ''
  return `${item.objectType} · #${item.objectRef ?? '—'}`
}

function describeGoalLink(link: PersonalGoalLink) {
  // In TASK --ADVANCES--> GOAL, the selected goal is the object;
  // show the actual task subject rather than repeating this goal ID.
  if (link.predicate === 'ADVANCES' && link.subjectType === 'TASK')
    return `任务 #${link.subjectRef}`
  if (link.predicate === 'EVALUATES' && link.subjectType === 'REVIEW')
    return `复盘 #${link.subjectRef}`
  return link.objectValue || `${link.objectType} #${link.objectRef || '—'}`
}

// These fields are never fetched during page initialization or general refresh.
async function togglePrivateMemories() {
  if (privateOpen.value) {
    ++privateRequestGeneration
    clearChatSource()
    privateOpen.value = false
    privateFacts.value = []
    return
  }
  const generation = ++privateRequestGeneration
  privateLoading.value = true
  try {
    const result = await fetchPrivateMemories()
    if (generation !== privateRequestGeneration || activeTab.value !== 'memory') return
    privateFacts.value = result
    privateOpen.value = true
  } catch {
    if (generation !== privateRequestGeneration || activeTab.value !== 'memory') return
    privateFacts.value = []
    ElMessage.error('受限记忆加载失败，请确认账号权限')
  } finally {
    privateLoading.value = false
  }
}

async function refreshPrivateIfOpen() {
  if (!privateOpen.value || activeTab.value !== 'memory') return
  const generation = privateRequestGeneration
  try {
    const result = await fetchPrivateMemories()
    if (generation !== privateRequestGeneration || activeTab.value !== 'memory') return
    privateFacts.value = result
  } catch {
    if (generation !== privateRequestGeneration || activeTab.value !== 'memory') return
    ++privateRequestGeneration
    privateFacts.value = []
    privateOpen.value = false
    ElMessage.error('受限记忆无法刷新，已收起内容')
  }
}

async function loadData() {
  const generation = ++loadGeneration
  const tab = activeTab.value
  loading.value = true
  serviceError.value = ''
  try {
    // Only the active panel may fetch its personal source data.
    const [goalData, candidateData, memoryData, recordData] = await Promise.all([
      fetchPersonalGoals(),
      tab === 'memory' ? fetchMemoryCandidates() : Promise.resolve([] as PersonalMemory[]),
      tab === 'memory' ? fetchConfirmedMemories() : Promise.resolve([] as PersonalMemory[]),
      tab === 'timeline'
        ? fetchRecords({ moduleCode: timelineDomain.value || undefined })
        : Promise.resolve([] as RecordItem[]),
    ])
    if (generation !== loadGeneration || activeTab.value !== tab) return
    goals.value = goalData
    candidates.value = candidateData
    memories.value = memoryData
    memoryLoaded.value = tab === 'memory'
    records.value = recordData
    await refreshPrivateIfOpen()
    if (generation !== loadGeneration || activeTab.value !== tab) return
    // The owner explicitly opened normal history. Keep it accurate after
    // corrections/invalidations/erasure; never fetch it on a closed panel.
    if (tab === 'memory' && normalHistoryOpen.value) await toggleNormalHistory(true)
    if (generation !== loadGeneration || activeTab.value !== tab) return
    if (selectedGoalId.value !== null && !goalData.some(item => item.id === selectedGoalId.value)) {
      ++goalContextGeneration
      selectedGoalId.value = null
      context.value = []
      contextLoading.value = false
    }
  } catch {
    if (generation !== loadGeneration || activeTab.value !== tab) return
    // Do not leave owner-specific data rendered after a 401, token change,
    // failed refresh, or transient response error.
    goals.value = []
    candidates.value = []
    memories.value = []
    memoryLoaded.value = false
    records.value = []
    context.value = []
    ++goalContextGeneration
    selectedGoalId.value = null
    contextLoading.value = false
    ++privateRequestGeneration
    ++normalHistoryGeneration
    normalHistoryOpen.value = false
    normalHistory.value = []
    clearChatSource()
    privateFacts.value = []
    privateOpen.value = false
    serviceError.value = '数据暂时无法加载。请确认 Personal OS 后端版本已部署且账号已登录。'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function selectGoal(id: number) {
  clearPlanningAdvice()
  selectedGoalId.value = id
  context.value = []
  contextLoading.value = true
  const request = ++goalContextGeneration
  const generation = loadGeneration
  const identity = auth.token
  try {
    const response = await fetchPersonalGoalContext(id)
    if (request !== goalContextGeneration || generation !== loadGeneration
        || identity !== auth.token || selectedGoalId.value !== id
        || activeTab.value !== 'goals') return
    context.value = response
  } catch {
    if (request !== goalContextGeneration || generation !== loadGeneration
        || identity !== auth.token || selectedGoalId.value !== id
        || activeTab.value !== 'goals') return
    context.value = []
    ElMessage.error('目标关联证据加载失败')
  } finally {
    if (request === goalContextGeneration && generation === loadGeneration
        && identity === auth.token) contextLoading.value = false
  }
}

async function reviewGoalModelSharing() {
  const goal = selectedGoal.value
  if (!goal || goal.domain !== 'career' || adviceBusy.value) return
  clearPlanningAdvice()
  const generation = adviceGeneration
  const identity = auth.token
  adviceBusy.value = true
  try {
    const review = await previewGoalModelSharing(goal.id, sharePersonalFacts.value)
    if (generation !== adviceGeneration || identity !== auth.token
        || selectedGoalId.value !== goal.id || activeTab.value !== 'goals') return
    adviceReview.value = review
  } catch {
    if (generation === adviceGeneration) ElMessage.error('共享预览失败，请检查目标状态或重新登录')
  } finally {
    if (generation === adviceGeneration) adviceBusy.value = false
  }
}

async function generateGoalModelAdvice() {
  const review = adviceReview.value
  if (!review || adviceBusy.value || selectedGoalId.value !== review.goalId) return
  try {
    await ElMessageBox.confirm(
      '你已查看下方完整共享快照。确认后仅本次发送给 '
        + review.provider + ' / ' + review.model
        + '，可能产生模型费用。建议不会自动创建任务。',
      '确认向外部模型共享资料',
      { confirmButtonText: '确认仅本次发送', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  const generation = adviceGeneration
  const identity = auth.token
  adviceBusy.value = true
  try {
    const modelToken = await confirmGoalModelSharing(review.goalId, review.previewId)
    if (generation !== adviceGeneration || identity !== auth.token
        || selectedGoalId.value !== review.goalId || activeTab.value !== 'goals') return
    const result = await suggestGoalModelAdvice(review.goalId, modelToken)
    if (generation !== adviceGeneration || identity !== auth.token
        || selectedGoalId.value !== review.goalId || activeTab.value !== 'goals') return
    adviceReview.value = null
    adviceOutput.value = result
    ElMessage.success('建议已生成；尚未创建任务')
  } catch {
    if (generation !== adviceGeneration) return
    clearPlanningAdvice()
    ElMessage.error('建议生成失败或授权已失效，请重新预览后确认')
  } finally {
    if (generation === adviceGeneration) adviceBusy.value = false
  }
}

function openAdviceTaskDraft(proposal: PlanningModelProposal) {
  const advice = adviceOutput.value
  if (!advice || !auth.token || activeTab.value !== 'goals'
      || selectedGoalId.value !== advice.goalId
      || !advice.proposals.includes(proposal) || taskDraftSaving.value
      || taskLinkPending.value !== null) return
  clearTaskDraft()
  taskDraftGoalId.value = advice.goalId
  taskDraftOwnerToken.value = auth.token
  taskDraftForm.title = proposal.title.slice(0, 120)
  taskDraftForm.description = proposal.rationale.slice(0, 400)
  taskDraftOpen.value = true
}

async function saveAdviceTaskDraft() {
  if (!taskDraftOpen.value || taskDraftSaving.value
      || !auth.token || auth.token !== taskDraftOwnerToken.value
      || taskDraftGoalId.value === null
      || selectedGoalId.value !== taskDraftGoalId.value || activeTab.value !== 'goals'
      || !adviceOutput.value || adviceOutput.value.goalId !== taskDraftGoalId.value
      || !taskDraftForm.title.trim()) return
  const identity = auth.token
  const goalId = taskDraftGoalId.value
  taskDraftSaving.value = true
  try {
    // AI-generated advice does NOT write tasks. This requires a separate owner click.
    const created = await createTask({
      moduleCode: 'learning',
      title: taskDraftForm.title.trim().slice(0, 120),
      description: taskDraftForm.description.trim().slice(0, 400),
      priority: taskDraftForm.priority,
      dueDate: null,
    })
    if (identity !== auth.token || goalId !== selectedGoalId.value
        || activeTab.value !== 'goals') return
    clearTaskDraft()
    taskLinkPending.value = {
      goalId, taskId: created.id, ownerToken: identity,
      requestKey: requestKey('task_link'), source: 'new',
    }
    ElMessage.success(`任务 #${created.id} 已创建；如要关联目标，请单独确认`)
  } catch {
    if (identity === auth.token && goalId === selectedGoalId.value)
      ElMessage.error('任务创建结果未确认，请先到任务模块检查，避免重复提交')
  } finally {
    taskDraftSaving.value = false
  }
}

/** Deliberate owner-only read: never fetch task titles on page initialization. */
async function openExistingTaskPicker() {
  const goalId = selectedGoalId.value
  const identity = auth.token
  if (!goalId || !identity || activeTab.value !== 'goals'
      || taskLinkBusy.value || taskLinkPending.value !== null) return
  clearTaskPicker()
  taskPickerOpen.value = true
  taskPickerBusy.value = true
  taskPickerGoalId.value = goalId
  taskPickerOwnerToken.value = identity
  const generation = taskPickerGeneration
  try {
    const [tasks, links] = await Promise.all([
      fetchTasks(), fetchPersonalGoalContext(goalId),
    ])
    if (generation !== taskPickerGeneration || identity !== auth.token
        || selectedGoalId.value !== goalId || activeTab.value !== 'goals') return
    context.value = links
    const alreadyLinked = new Set(links
      .filter(link => link.predicate === 'ADVANCES'
        && link.subjectType === 'TASK' && link.objectType === 'GOAL')
      .map(link => link.subjectRef))
    taskPickerTasks.value = tasks.filter(task =>
      task.status !== 'canceled' && !alreadyLinked.has(String(task.id)))
  } catch {
    if (generation === taskPickerGeneration) {
      clearTaskPicker()
      ElMessage.error('已有任务加载失败，请确认当前账号权限后重试')
    }
  } finally {
    if (generation === taskPickerGeneration) taskPickerBusy.value = false
  }
}

/** Stage an existing task; opening/selecting it never creates a link. */
function stageExistingTaskLink() {
  const goalId = taskPickerGoalId.value
  const taskId = taskPickerTaskId.value
  const identity = taskPickerOwnerToken.value
  if (!taskPickerOpen.value || taskPickerBusy.value || taskLinkBusy.value
      || taskLinkPending.value !== null || !goalId || !taskId
      || !identity || identity !== auth.token
      || selectedGoalId.value !== goalId || activeTab.value !== 'goals'
      || !taskPickerTasks.value.some(task => task.id === taskId)) return
  taskLinkPending.value = {
    goalId, taskId, ownerToken: identity,
    requestKey: requestKey('task_link'), source: 'existing',
  }
  clearTaskPicker()
}

/** The owner explicitly requests existing review titles; never on page startup. */
async function openExistingReviewPicker() {
  const goalId = selectedGoalId.value
  const identity = auth.token
  if (!goalId || !identity || activeTab.value !== 'goals' || reviewLinkBusy.value
      || reviewLinkPending.value !== null) return
  clearReviewPicker()
  reviewPickerOpen.value = true
  reviewPickerBusy.value = true
  reviewPickerGoalId.value = goalId
  reviewPickerOwnerToken.value = identity
  const generation = reviewPickerGeneration
  try {
    const [reviews, links] = await Promise.all([
      fetchReviews(), fetchPersonalGoalContext(goalId),
    ])
    if (generation !== reviewPickerGeneration || identity !== auth.token
        || selectedGoalId.value !== goalId || activeTab.value !== 'goals') return
    context.value = links
    const alreadyLinked = new Set(links
      .filter(link => link.predicate === 'EVALUATES'
        && link.subjectType === 'REVIEW' && link.objectType === 'GOAL')
      .map(link => link.subjectRef))
    reviewPickerReviews.value = reviews.filter(review =>
      !alreadyLinked.has(String(review.id)))
  } catch {
    if (generation === reviewPickerGeneration) {
      clearReviewPicker()
      ElMessage.error('本人复盘列表加载失败，请稍后重试')
    }
  } finally {
    if (generation === reviewPickerGeneration) reviewPickerBusy.value = false
  }
}

/** Selection alone is read-only; the owner must still confirm in the goal. */
function stageExistingReviewLink() {
  const goalId = reviewPickerGoalId.value
  const reviewId = reviewPickerReviewId.value
  const identity = reviewPickerOwnerToken.value
  if (!reviewPickerOpen.value || reviewPickerBusy.value || reviewLinkBusy.value
      || reviewLinkPending.value !== null || !goalId || !reviewId
      || !identity || identity !== auth.token
      || selectedGoalId.value !== goalId || activeTab.value !== 'goals'
      || !reviewPickerReviews.value.some(review => review.id === reviewId)) return
  reviewLinkPending.value = {
    goalId, reviewId, ownerToken: identity, requestKey: requestKey('review_link'),
  }
  clearReviewPicker()
}

/** Separate owner confirmation and server-side review/goal/source authorization. */
async function confirmGoalReviewLink() {
  const pending = reviewLinkPending.value
  if (!pending || reviewLinkBusy.value || pending.ownerToken !== auth.token
      || activeTab.value !== 'goals' || selectedGoalId.value !== pending.goalId) return
  reviewLinkBusy.value = true
  try {
    const links = await fetchPersonalGoalContext(pending.goalId)
    if (reviewLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    if (links.some(link => link.predicate === 'EVALUATES'
        && link.subjectType === 'REVIEW'
        && link.subjectRef === String(pending.reviewId))) {
      context.value = links
      reviewLinkPending.value = null
      ElMessage.info('该复盘已经关联当前目标')
      return
    }
    const candidate = await proposeGoalReviewLink(
      pending.goalId, pending.reviewId, pending.requestKey,
    )
    if (reviewLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    await confirmPersonalMemory(candidate.id)
    if (reviewLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    reviewLinkPending.value = null
    ElMessage.success(`复盘 #${pending.reviewId} 已关联到目标`)
    const generation = ++goalContextGeneration
    try {
      const refreshed = await fetchPersonalGoalContext(pending.goalId)
      if (generation === goalContextGeneration && pending.ownerToken === auth.token
          && selectedGoalId.value === pending.goalId && activeTab.value === 'goals')
        context.value = refreshed
    } catch {
      if (generation === goalContextGeneration && pending.ownerToken === auth.token)
        ElMessage.warning('复盘关联已确认，但列表刷新失败，请手动刷新')
    }
  } catch {
    if (reviewLinkPending.value === pending && pending.ownerToken === auth.token)
      ElMessage.error('复盘关联尚未确认，可重试；原始复盘未发生改变')
  } finally {
    reviewLinkBusy.value = false
  }
}

/** Separate owner click; proposal + confirmation reuse the reviewed owner-scoped ontology API. */
async function confirmGoalTaskLink() {
  const pending = taskLinkPending.value
  if (!pending || taskLinkBusy.value || pending.ownerToken !== auth.token
      || activeTab.value !== 'goals' || selectedGoalId.value !== pending.goalId) return
  taskLinkBusy.value = true
  try {
    // A fresh owner-scoped read avoids known duplicates after another tab
    // established this relation. Server authorization is still authoritative.
    const latestLinks = await fetchPersonalGoalContext(pending.goalId)
    if (taskLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    if (latestLinks.some(link => link.predicate === 'ADVANCES'
        && link.subjectType === 'TASK' && link.subjectRef === String(pending.taskId))) {
      context.value = latestLinks
      taskLinkPending.value = null
      ElMessage.info('该任务已经关联到当前目标，无需重复关联')
      return
    }
    // The stable request key allows a retry after a lost response without
    // creating another task or another association.
    const candidate = await proposeGoalTaskLink(
      pending.goalId, pending.taskId, pending.requestKey,
    )
    if (taskLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    await confirmPersonalMemory(candidate.id)
    if (taskLinkPending.value !== pending || pending.ownerToken !== auth.token
        || selectedGoalId.value !== pending.goalId || activeTab.value !== 'goals') return
    taskLinkPending.value = null
    ElMessage.success(`任务 #${pending.taskId} 已关联到目标`)
    const request = ++goalContextGeneration
    try {
      const links = await fetchPersonalGoalContext(pending.goalId)
      if (request === goalContextGeneration && auth.token === pending.ownerToken
          && selectedGoalId.value === pending.goalId && activeTab.value === 'goals') {
        context.value = links
      }
    } catch {
      if (request === goalContextGeneration && auth.token === pending.ownerToken)
        ElMessage.warning('目标关联已确认，但列表刷新失败，请手动刷新')
    }
  } catch {
    if (taskLinkPending.value === pending && pending.ownerToken === auth.token)
      ElMessage.error('关联尚未确认，可重试；任务已存在，请勿重复创建任务')
  } finally {
    taskLinkBusy.value = false
  }
}

async function submitGoal() {
  if (!goalForm.title.trim() || actionBusy.value) return
  actionBusy.value = true
  try {
    const created = await createPersonalGoal({
      title: goalForm.title.trim(),
      description: goalForm.description.trim() || null,
      domain: goalForm.domain,
      priority: goalForm.priority,
      successCriteria: goalForm.successCriteria.trim() || null,
      targetDate: goalForm.targetDate || null,
      requestKey: goalForm.requestKey,
    })
    goalForm.title = ''
    goalForm.description = ''
    goalForm.successCriteria = ''
    goalForm.targetDate = ''
    goalForm.requestKey = requestKey('goal')
    ElMessage.success('目标已创建')
    await loadData()
    await selectGoal(created.id)
  } catch {
    ElMessage.error('创建目标失败，表单已保留以便重试')
  } finally {
    actionBusy.value = false
  }
}

function nextGoalActions(status: GoalStatus): Array<{ value: GoalStatus; label: string }> {
  if (status === 'PLANNED') return [{ value: 'ACTIVE', label: '开始执行' }, { value: 'CANCELLED', label: '取消目标' }]
  if (status === 'ACTIVE') return [
    { value: 'PAUSED', label: '暂停' }, { value: 'COMPLETED', label: '标记完成' },
    { value: 'CANCELLED', label: '取消目标' },
  ]
  if (status === 'PAUSED') return [{ value: 'ACTIVE', label: '继续执行' }, { value: 'CANCELLED', label: '取消目标' }]
  return []
}

async function setGoalStatus(id: number, next: GoalStatus) {
  if (actionBusy.value) return
  try {
    await ElMessageBox.confirm(`确认把目标设为「${goalStatuses[next]}」？`, '目标状态变更', {
      confirmButtonText: '确认', cancelButtonText: '返回', type: 'warning',
    })
  } catch { return }
  actionBusy.value = true
  try {
    await changePersonalGoalStatus(id, next)
    ElMessage.success('状态已更新')
    await loadData()
    if (selectedGoalId.value === id) await selectGoal(id)
  } catch { ElMessage.error('状态变更失败，请刷新后重试') }
  finally { actionBusy.value = false }
}

function memoryInput(predicate: MemoryPredicate, text: string, sensitivity: MemorySensitivity, key: string) {
  const personId = auth.user?.id
  if (personId === undefined || personId === null) throw new Error('用户身份尚未加载')
  return {
    subjectType: 'PERSON' as const, subjectRef: String(personId),
    predicate, objectType: 'LITERAL' as const, objectRef: null,
    objectValue: text.trim(), sourceType: 'USER_INPUT' as const, sourceRef: null,
    validFrom: null, validTo: null, sensitivity, requestKey: key,
  }
}

async function submitMemory() {
  if (!memoryForm.text.trim() || actionBusy.value) return
  actionBusy.value = true
  try {
    await proposePersonalMemory(memoryInput(
      memoryForm.predicate, memoryForm.text, memoryForm.sensitivity, memoryForm.requestKey,
    ))
    memoryForm.text = ''
    memoryForm.requestKey = requestKey('memory')
    ElMessage.success('已保存为待确认候选，尚未视为事实')
    await loadData()
    activeTab.value = 'memory'
  } catch {
    ElMessage.error('保存候选失败，内容已保留')
  } finally { actionBusy.value = false }
}

async function confirmCandidate(item: PersonalMemory) {
  if (actionBusy.value) return
  try {
    await ElMessageBox.confirm(
      item.origin === 'AI_CANDIDATE'
        ? `此内容由 AI 提议，并非独立核实的事实。请逐字核对；${item.sensitivity === 'NORMAL' ? '确认后可进入普通记忆和后续授权的 AI 检索。' : '确认后仍属于受限/敏感记忆，不进入默认 AI 检索。'}`
        : '确认后会成为已确认的个人事实。请核对内容、来源和敏感级别。',
      '确认个人记忆',
      { confirmButtonText: '我已核对，确认', cancelButtonText: '暂不确认', type: 'warning' },
    )
  } catch { return }
  actionBusy.value = true
  try {
    await confirmPersonalMemory(item.id)
    ElMessage.success('记忆已确认')
    await loadData()
  } catch { ElMessage.error('确认失败；可能已被其他操作修改或证据失效') }
  finally { actionBusy.value = false }
}

async function invalidateCandidate(item: PersonalMemory) {
  if (actionBusy.value) return
  try {
    await ElMessageBox.confirm('将这条事实标记为无效，不再参与默认查询？', '作废个人记忆',
      { confirmButtonText: '作废', cancelButtonText: '返回', type: 'warning' })
  } catch { return }
  actionBusy.value = true
  try {
    await invalidatePersonalMemory(item.id)
    ElMessage.success('已作废')
    await loadData()
  } catch { ElMessage.error('作废失败') }
  finally { actionBusy.value = false }
}

async function eraseMemory(item: PersonalMemory) {
  if (actionBusy.value) return
  try {
    await ElMessageBox.confirm(
      '确定彻底删除这条个人记忆吗？此操作会删除本条数据，不可撤销。',
      '永久删除个人记忆',
      { confirmButtonText: '永久删除', cancelButtonText: '返回', type: 'warning' },
    )
  } catch { return }
  actionBusy.value = true
  try {
    await erasePersonalMemory(item.id)
    ElMessage.success('记忆数据已删除')
    await loadData()
  } catch { ElMessage.error('删除失败，请检查关联关系后重试') }
  finally { actionBusy.value = false }
}

function openCorrection(item: PersonalMemory) {
  if (item.status !== 'CONFIRMED' || item.objectType !== 'LITERAL'
    || !['PREFERS', 'DECLARES_SKILL', 'HAS_BACKGROUND'].includes(item.predicate)) return
  correctionTarget.value = item
  correctionText.value = item.objectValue ?? ''
  correctionRequestKey.value = requestKey('correction')
  correctionOpen.value = true
}

async function saveCorrection() {
  const item = correctionTarget.value
  if (!item || !correctionText.value.trim() || actionBusy.value) return
  actionBusy.value = true
  try {
    await replacePersonalMemory(item.id, memoryInput(
      item.predicate as MemoryPredicate, correctionText.value,
      item.sensitivity, correctionRequestKey.value,
    ))
    correctionOpen.value = false
    correctionTarget.value = null
    correctionRequestKey.value = ''
    ElMessage.success('更正已保存为候选；原事实在更正确认前仍然有效')
    await loadData()
    activeTab.value = 'memory'
  } catch { ElMessage.error('创建更正候选失败') }
  finally { actionBusy.value = false }
}

// Never reuse old-account data or accept delayed responses after an auth switch.
watch(() => auth.token, (next, prior) => {
  if (next === prior) return
  clearPlanningAdvice()
  ++loadGeneration
  ++goalContextGeneration
  ++privateRequestGeneration
  ++normalHistoryGeneration
  normalHistoryOpen.value = false
  normalHistory.value = []
  normalHistoryBusy.value = false
  clearChatSource()
  goals.value = []
  context.value = []
  selectedGoalId.value = null
  contextLoading.value = false
  candidates.value = []
  memories.value = []
  memoryLoaded.value = false
  privateFacts.value = []
  privateOpen.value = false
  records.value = []
  correctionTarget.value = null
  correctionText.value = ''
  correctionRequestKey.value = ''
  correctionOpen.value = false
  if (next) void loadData()
})

// Private facts must not persist across tabs, even while the view remains mounted.
watch(activeTab, (next) => {
  clearPlanningAdvice()
  // Cancel stale responses and immediately clear data from inactive panels.
  ++loadGeneration
  if (next !== 'memory') {
    ++privateRequestGeneration
    ++normalHistoryGeneration
    normalHistoryOpen.value = false
    normalHistory.value = []
    normalHistoryBusy.value = false
    privateOpen.value = false
    privateFacts.value = []
    candidates.value = []
    memories.value = []
    memoryLoaded.value = false
    clearChatSource()
  }
  if (next !== 'timeline') records.value = []
  if (next !== 'goals') {
    ++goalContextGeneration
    context.value = []
    contextLoading.value = false
  }
  void loadData()
})

onUnmounted(() => {
  clearPlanningAdvice()
  // Discard both normal and private in-flight responses after route exit.
  ++loadGeneration
  ++goalContextGeneration
  ++privateRequestGeneration
  ++normalHistoryGeneration
  normalHistoryOpen.value = false
  normalHistory.value = []
  clearChatSource()
  contextLoading.value = false
  privateOpen.value = false
  privateFacts.value = []
  candidates.value = []
  memories.value = []
  records.value = []
  context.value = []
})

onMounted(async () => {
  try { await auth.loadCurrentUser() } catch { /* auth/error UI is handled by route and API */ }
  await loadData()
})
</script>

<template>
  <AppLayout>
    <div class="personal-os-page">
      <header class="os-hero">
        <div>
          <p class="os-kicker">PERSONAL OS · 个人智能操作系统</p>
          <h1>把目标、经历和个人记忆连接起来</h1>
          <p class="os-intro">让记录成为可追溯的事实，让目标带动行动；所有记忆必须经过你确认。</p>
        </div>
        <div class="os-privacy">
          <strong>隐私优先</strong>
          <span>新记忆默认受限；此页面不自动调用 AI 或公开个人资料。</span>
        </div>
      </header>

      <el-alert v-if="serviceError" :title="serviceError" type="warning" show-icon :closable="false" class="os-alert" />
      <div class="os-toolbar">
        <el-segmented v-model="activeTab" :options="[
          { label: '我的目标', value: 'goals' },
          { label: '个人记忆', value: 'memory' },
          { label: '人生记录', value: 'timeline' },
        ]" />
        <el-button :loading="loading" @click="loadData">刷新</el-button>
      </div>

      <div class="os-stats">
        <div><span>目标总数</span><strong>{{ goals.length }}</strong></div>
        <div><span>进行中的目标</span><strong>{{ goals.filter(g => g.status === 'ACTIVE').length }}</strong></div>
        <div><span>待确认记忆</span><strong>{{ memoryLoaded ? candidates.length : '—' }}</strong></div>
        <div><span>可查询的普通记忆</span><strong>{{ memoryLoaded ? memories.length : '—' }}</strong></div>
      </div>

      <section v-if="activeTab === 'goals'" class="os-grid">
        <el-card shadow="never" class="os-panel">
          <template #header><strong>创建一个可执行的目标</strong></template>
          <el-form label-position="top" @submit.prevent="submitGoal">
            <el-form-item label="目标名称">
              <el-input v-model="goalForm.title" maxlength="255" show-word-limit placeholder="例如：完成一个阶段性学习计划" />
            </el-form-item>
            <el-form-item label="所属领域">
              <el-select v-model="goalForm.domain">
                <el-option label="职业发展" value="career" />
                <el-option label="学习成长" value="learning" />
                <el-option label="健康管理" value="wellness" />
                <el-option label="生活" value="life" />
                <el-option label="财务" value="finance" />
              </el-select>
            </el-form-item>
            <el-form-item label="描述"><el-input v-model="goalForm.description" type="textarea" :rows="2" maxlength="20000" /></el-form-item>
            <el-form-item label="成功标准">
              <el-input v-model="goalForm.successCriteria" placeholder="用什么事实判定目标达成" maxlength="4000" />
            </el-form-item>
            <div class="os-form-row">
              <el-form-item label="优先级">
                <el-select v-model="goalForm.priority">
                  <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
                </el-select>
              </el-form-item>
              <el-form-item label="目标日期"><el-date-picker v-model="goalForm.targetDate" type="date" value-format="YYYY-MM-DD" placeholder="可选" clearable /></el-form-item>
            </div>
            <el-button type="primary" native-type="submit" :loading="actionBusy" :disabled="!goalForm.title.trim()">创建目标</el-button>
          </el-form>
        </el-card>
        <div class="os-list-panel">
          <div class="os-section-heading"><h2>目标列表</h2><span>{{ goals.length }} 个</span></div>
          <el-empty v-if="!goals.length && !loading" description="尚未创建目标" />
          <el-skeleton v-else-if="loading && !goals.length" :rows="3" animated />
          <article v-for="goal in goals" :key="goal.id" class="os-goal-card" :class="{ selected: goal.id === selectedGoalId }">
            <button type="button" class="os-goal-select" @click="selectGoal(goal.id)">
              <span class="os-goal-top"><strong>{{ goal.title }}</strong><el-tag size="small" effect="plain">{{ goalStatuses[goal.status] }}</el-tag></span>
              <span>{{ goal.description || '暂无目标说明' }}</span>
              <small>领域 {{ goal.domain }} · {{ goal.targetDate || '未设截止日期' }}</small>
            </button>
            <div v-if="nextGoalActions(goal.status).length" class="os-card-actions">
              <el-button v-for="action in nextGoalActions(goal.status)" :key="action.value" size="small" text
                :disabled="actionBusy" @click="setGoalStatus(goal.id, action.value)">{{ action.label }}</el-button>
            </div>
          </article>
          <div v-if="selectedGoal" class="os-context">
            <h3>{{ selectedGoal.title }} · 关联事实</h3>
            <p v-if="!contextLoading && !context.length">暂无已确认、仍有效且有权限查看的关联事实。</p>
            <el-skeleton v-if="contextLoading" :rows="2" animated />
            <div v-for="link in context" :key="link.assertionId" class="os-evidence">
              <strong>{{ relationLabels[link.predicate] || link.predicate }}</strong>
              <span>{{ describeGoalLink(link) }}</span>
              <small>事实 #{{ link.assertionId }} · 已确认</small>
            </div>
            <div class="os-card-actions">
              <el-button :disabled="taskLinkBusy || taskLinkPending !== null"
                @click="openExistingTaskPicker">关联已有任务（先选择）</el-button>
              <el-button :disabled="reviewLinkBusy || reviewLinkPending !== null"
                @click="openExistingReviewPicker">关联已有复盘（先选择）</el-button>
            </div>
            <div v-if="taskLinkPending && taskLinkPending.goalId === selectedGoal.id"
              class="os-evidence" role="status">
              <strong>任务 #{{ taskLinkPending.taskId }} {{ taskLinkPending.source === 'new' ? '已创建' : '已选中' }}，尚未关联目标</strong>
              <p>任务已经独立保存。只有再次点击确认，才会把此任务记录为推进当前目标的已确认关系。</p>
              <div class="os-card-actions">
                <el-button type="primary" :loading="taskLinkBusy" @click="confirmGoalTaskLink">确认关联到此目标</el-button>
                <el-button :disabled="taskLinkBusy" @click="clearPendingTaskLink">暂不关联</el-button>
              </div>
            </div>
            <div v-if="reviewLinkPending && reviewLinkPending.goalId === selectedGoal.id"
              class="os-evidence" role="status">
              <strong>复盘 #{{ reviewLinkPending.reviewId }} 已选中，尚未关联目标</strong>
              <p>复盘已经存在；只有明确点击确认才会建立本目标的复盘关系，不会修改复盘原文。</p>
              <div class="os-card-actions">
                <el-button type="primary" :loading="reviewLinkBusy"
                  @click="confirmGoalReviewLink">确认复盘关联到此目标</el-button>
                <el-button :disabled="reviewLinkBusy"
                  @click="clearPendingReviewLink">暂不关联复盘</el-button>
              </div>
            </div>
            <section v-if="selectedGoal.domain === 'career'" class="os-model-panel" aria-label="AI 职业规划">
              <h3>AI 职业规划 · 单次授权</h3>
              <p class="os-help">先在本机生成共享预览，核对后才能发送给已选模型。只用已确认、有效且授权的事实，不会自动创建任务。</p>
              <el-checkbox v-model="sharePersonalFacts" :disabled="adviceBusy">
                本次额外包含已确认的普通个人事实（默认不选；受限和敏感事实永不包含）
              </el-checkbox>
              <div class="os-card-actions">
                <el-button :loading="adviceBusy" @click="reviewGoalModelSharing">预览将共享的内容</el-button>
                <el-button v-if="adviceReview" type="primary" :loading="adviceBusy"
                  @click="generateGoalModelAdvice">核对完成，确认仅本次发送</el-button>
              </div>
              <div v-if="adviceReview" class="os-model-review">
                <p><strong>接收模型：</strong>{{ adviceReview.provider }} / {{ adviceReview.model }}</p>
                <p><strong>授权过期：</strong>{{ new Date(adviceReview.expiresAtMillis).toLocaleTimeString() }}（过期须重新预览）</p>
                <p>以下 JSON 是将发送给外部模型的完整业务快照；查看内容后再确认。</p>
                <pre class="os-model-json">{{ JSON.stringify(adviceReview.snapshot, null, 2) }}</pre>
              </div>
              <div v-if="adviceOutput" class="os-model-results">
                <h3>待核验的 AI 建议（未创建任务）</h3>
                <article v-for="(proposal, index) in adviceOutput.proposals" :key="index" class="os-model-proposal">
                  <strong>{{ proposal.title }}</strong>
                  <p>{{ proposal.rationale }}</p>
                  <small>证据：{{ proposal.evidenceRefs.join('、') }}</small>
                  <p v-if="proposal.assumptions.length">待核实：{{ proposal.assumptions.join('；') }}</p>
                  <div class="os-card-actions">
                    <el-button size="small" :disabled="taskDraftSaving || taskLinkPending !== null" @click="openAdviceTaskDraft(proposal)">采纳为任务（先审核）</el-button>
                  </div>
                </article>
                <p class="os-help">{{ adviceOutput.limitation }}</p>
                <el-button @click="reviewGoalModelSharing">重新预览后再生成</el-button>
              </div>
            </section>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'memory'" class="os-grid">
        <el-card class="os-panel" shadow="never">
          <template #header><strong>补充个人事实</strong></template>
          <p class="os-help">手动写入的内容先保存为候选。确认前，不会成为已验证的个人记忆。</p>
          <el-form label-position="top" @submit.prevent="submitMemory">
            <el-form-item label="事实类型">
              <el-select v-model="memoryForm.predicate">
                <el-option label="个人偏好" value="PREFERS" />
                <el-option label="自报技能" value="DECLARES_SKILL" />
                <el-option label="人生背景" value="HAS_BACKGROUND" />
              </el-select>
            </el-form-item>
            <el-form-item label="事实内容">
              <el-input v-model="memoryForm.text" type="textarea" :rows="3" maxlength="512" show-word-limit placeholder="只填写你希望保存在 PRP 中的信息" />
            </el-form-item>
            <el-form-item label="敏感级别">
              <el-radio-group v-model="memoryForm.sensitivity">
                <el-radio value="RESTRICTED">受限（默认）</el-radio>
                <el-radio value="SENSITIVE">敏感</el-radio>
                <el-radio value="NORMAL">普通</el-radio>
              </el-radio-group>
            </el-form-item>
            <p class="os-help">只有明确选择「普通」并确认的有效事实，才进入默认的记忆列表。</p>
            <el-button type="primary" native-type="submit" :loading="actionBusy"
              :disabled="!memoryForm.text.trim()">保存为待确认候选</el-button>
          </el-form>
        </el-card>
        <div class="os-list-panel">
          <div class="os-section-heading"><h2>待你确认</h2><span>{{ candidates.length }} 条</span></div>
          <el-empty v-if="!candidates.length" description="暂无待确认的记忆" />
          <article v-for="item in candidates" :key="item.id" class="os-memory-card">
            <div class="os-memory-heading"><strong>{{ relationLabels[item.predicate] || item.predicate }}</strong>
              <el-tag v-if="item.origin === 'AI_CANDIDATE'" size="small" type="danger">AI 提议 · 未核实</el-tag>
              <el-tag size="small" type="warning">{{ item.sensitivity === 'NORMAL' ? '普通' : '受限/敏感' }}</el-tag></div>
            <p>{{ describeMemory(item) }}</p>
            <small>来源 {{ item.sourceType === 'CHAT_MESSAGE' ? '本人聊天消息（仅核验来源，内容待确认）' : item.origin === 'AI_CANDIDATE' ? 'AI 候选（无关联聊天来源）' : item.sourceType }}{{ item.sourceRef ? ' #' + item.sourceRef : '' }} · {{ item.createdAt.slice(0, 10) }}</small>
            <div class="os-card-actions">
              <el-button v-if="item.sourceType === 'CHAT_MESSAGE'" size="small" :disabled="chatSourceBusy" @click="openChatSource(item)">查看聊天来源</el-button>
              <el-button size="small" type="primary" :disabled="actionBusy" @click="confirmCandidate(item)">确认事实</el-button>
              <el-button size="small" :disabled="actionBusy" @click="invalidateCandidate(item)">不采纳</el-button>
              <el-button size="small" text type="danger" :disabled="actionBusy" @click="eraseMemory(item)">删除</el-button>
            </div>
          </article>
          <div class="os-section-heading os-secondary-heading"><h2>已确认 · 普通记忆</h2><span>{{ memories.length }} 条</span></div>
          <p class="os-help">受限/敏感记忆不会出现在此列表；不可据此认为它们已被删除。</p>
          <el-empty v-if="!memories.length" description="暂无可以展示的普通记忆" />
          <article v-for="item in memories" :key="item.id" class="os-memory-card">
            <div class="os-memory-heading"><strong>{{ relationLabels[item.predicate] || item.predicate }}</strong>
              <el-tag size="small" type="success">已确认</el-tag></div>
            <p>{{ describeMemory(item) }}</p>
            <small>来源 {{ item.sourceType === 'CHAT_MESSAGE' ? '本人聊天消息' : item.sourceType }}{{ item.sourceRef ? ' #' + item.sourceRef : '' }} · {{ item.createdAt.slice(0, 10) }}</small>
            <div class="os-card-actions">
              <el-button v-if="item.sourceType === 'CHAT_MESSAGE'" size="small" @click="openChatSource(item)">查看聊天来源</el-button>
              <el-button v-if="item.objectType === 'LITERAL'" size="small" :disabled="actionBusy"
                @click="openCorrection(item)">更正</el-button>
              <el-button size="small" :disabled="actionBusy" @click="invalidateCandidate(item)">作废</el-button>
              <el-button size="small" text type="danger" :disabled="actionBusy" @click="eraseMemory(item)">永久删除</el-button>
            </div>
          </article>


          <section class="os-private" aria-label="普通记忆历史管理">
            <div class="os-section-heading os-secondary-heading">
              <h2>普通记忆历史与失效来源</h2>
              <el-button :loading="normalHistoryBusy" @click="toggleNormalHistory()">
                {{ normalHistoryOpen ? '收起并清除本页历史' : '主动查看历史' }}
              </el-button>
            </div>
            <p class="os-help">旧版本、作废记录以及聊天来源失效的普通事实不会进入默认 AI 检索。只有你主动查看时才加载，仍可更正或删除。</p>
            <template v-if="normalHistoryOpen">
              <el-button size="small" :loading="normalHistoryBusy" @click="toggleNormalHistory(true)">刷新历史</el-button>
              <el-empty v-if="!normalHistory.length" description="没有可管理的普通记忆历史" />
              <article v-for="item in normalHistory" :key="item.id" class="os-memory-card">
                <div class="os-memory-heading">
                  <strong>{{ relationLabels[item.predicate] || item.predicate }}</strong>
                  <el-tag size="small" :type="item.status === 'CONFIRMED' ? 'success' : 'info'">
                    {{ item.status === 'CONFIRMED' ? '已确认（来源可能已失效）' :
                      item.status === 'SUPERSEDED' ? '旧版本' : '已作废' }}
                  </el-tag>
                </div>
                <p>{{ describeMemory(item) }}</p>
                <small>事实 #{{ item.id }} · {{ item.supersedesId ? '替代事实 #' + item.supersedesId + ' · ' : '' }}
                  来源 {{ item.sourceType }}{{ item.sourceRef ? ' #' + item.sourceRef : '' }} · {{ item.createdAt.slice(0, 10) }}</small>
                <div class="os-card-actions">
                  <el-button v-if="item.sourceType === 'CHAT_MESSAGE'" size="small" @click="openChatSource(item)">查看聊天来源</el-button>
                  <el-button v-if="item.status === 'CONFIRMED' && item.objectType === 'LITERAL'" size="small"
                    :disabled="actionBusy" @click="openCorrection(item)">更正</el-button>
                  <el-button v-if="item.status === 'CONFIRMED'" size="small" :disabled="actionBusy" @click="invalidateCandidate(item)">作废</el-button>
                  <el-button size="small" type="danger" text :disabled="actionBusy" @click="eraseMemory(item)">永久删除</el-button>
                </div>
              </article>
            </template>
          </section>

          <section class="os-private" aria-label="受限记忆管理">
            <div class="os-section-heading os-secondary-heading">
              <h2>受限 / 敏感记忆</h2>
              <el-button :loading="privateLoading" @click="togglePrivateMemories">
                {{ privateOpen ? '收起并清除本页内容' : '主动查看并管理' }}
              </el-button>
            </div>
            <p class="os-help">受限/敏感的已确认及历史事实默认不读取，只有主动展开才会请求；待确认候选仍显示在上方审核队列。此管理列表不会发送给 AI 或 MCP。</p>
            <template v-if="privateOpen">
              <el-empty v-if="!privateFacts.length" description="没有可管理的受限/敏感记忆" />
              <article v-for="item in privateFacts" :key="item.id" class="os-memory-card">
                <div class="os-memory-heading">
                  <strong>{{ relationLabels[item.predicate] || item.predicate }}</strong>
                  <el-tag size="small" type="warning">
                    {{ item.sensitivity === 'RESTRICTED' ? '受限' : '敏感' }}
                  </el-tag>
                </div>
                <p>{{ describeMemory(item) }}</p>
                <small>来源 {{ item.sourceType }} · 事实 #{{ item.id }} ·
                  {{ item.status === 'CONFIRMED' ? '已确认' : item.status === 'INVALID' ? '已作废' : '已被替代' }}</small>
                <div class="os-card-actions">
                  <el-button v-if="item.sourceType === 'CHAT_MESSAGE'" size="small" @click="openChatSource(item)">查看聊天来源</el-button>
                  <el-button v-if="item.status === 'CONFIRMED' && item.objectType === 'LITERAL'" size="small"
                    :disabled="actionBusy" @click="openCorrection(item)">更正</el-button>
                  <el-button v-if="item.status === 'CONFIRMED'" size="small"
                    :disabled="actionBusy" @click="invalidateCandidate(item)">作废</el-button>
                  <el-button size="small" type="danger" text :disabled="actionBusy"
                    @click="eraseMemory(item)">永久删除</el-button>
                </div>
              </article>
            </template>
          </section>
        </div>
      </section>

      <section v-else class="os-timeline">
        <div class="os-section-heading"><h2>人生记录时间轴</h2>
          <RouterLink to="/records">管理原始记录</RouterLink></div>
        <el-select v-model="timelineDomain" style="max-width: 220px; margin-bottom: 14px;" aria-label="时间轴记录领域" @change="loadData">
          <el-option label="生活记录" value="life" />
          <el-option label="工作经历" value="work" />
          <el-option label="学习经历" value="learning" />
          <el-option label="全部记录（主动选择）" value="" />
        </el-select>
        <p class="os-help">复用已有记录模块，默认只读取生活记录。其他领域由你主动选择；不自动推断人生经历。</p>
        <el-empty v-if="!timeline.length && !loading" description="暂无记录，先在记录管理中留下第一条。" />
        <article v-for="record in timeline" :key="record.id" class="os-timeline-item">
          <time>{{ record.recordDate }}</time>
          <div><h3>{{ record.title }}</h3><p>{{ record.content || '未填写详细内容' }}</p>
            <small>{{ record.moduleCode }} · #{{ record.id }}</small></div>
        </article>
      </section>

      <el-dialog v-model="reviewPickerOpen" title="选择已有复盘关联目标"
        width="min(92vw, 520px)" destroy-on-close @close="clearReviewPicker">
        <p class="os-help">主动读取当前账号已有复盘；仅选择不会修改原复盘，也不会写入知识关系。</p>
        <el-skeleton v-if="reviewPickerBusy" :rows="3" animated />
        <template v-else>
          <el-empty v-if="!reviewPickerReviews.length" description="暂无可关联的复盘" />
          <el-select v-else v-model="reviewPickerReviewId" filterable clearable
            placeholder="选择现有复盘" aria-label="选择已有复盘" style="width:100%">
            <el-option v-for="review in reviewPickerReviews" :key="review.id"
              :label="`${review.title} (#${review.id})`" :value="review.id" />
          </el-select>
        </template>
        <template #footer>
          <el-button @click="clearReviewPicker">取消</el-button>
          <el-button type="primary" :disabled="reviewPickerBusy || !reviewPickerReviewId ||
            reviewPickerOwnerToken !== auth.token || reviewPickerGoalId !== selectedGoalId"
            @click="stageExistingReviewLink">审核复盘关联</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="taskPickerOpen" title="选择已有任务关联目标"
        width="min(92vw, 520px)" destroy-on-close @close="clearTaskPicker">
        <p class="os-help">这里只读取本人现有任务，不会创建任务，也不会自动建立目标关联；选定任务后仍需再次确认。</p>
        <el-skeleton v-if="taskPickerBusy" :rows="3" animated />
        <template v-else>
          <el-empty v-if="!taskPickerTasks.length" description="暂无可关联的任务" />
          <el-select v-else v-model="taskPickerTaskId" filterable clearable
            placeholder="选择本人现有任务" aria-label="选择已有任务" style="width:100%">
            <el-option v-for="task in taskPickerTasks" :key="task.id"
              :label="`${task.title} (#${task.id})`" :value="task.id" />
          </el-select>
        </template>
        <template #footer>
          <el-button @click="clearTaskPicker">取消</el-button>
          <el-button type="primary" :disabled="taskPickerBusy || !taskPickerTaskId ||
            taskPickerOwnerToken !== auth.token || taskPickerGoalId !== selectedGoalId"
            @click="stageExistingTaskLink">审核关联</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="taskDraftOpen" title="采纳 AI 建议为任务" width="min(92vw, 520px)"
        destroy-on-close :close-on-click-modal="!taskDraftSaving"
        :close-on-press-escape="!taskDraftSaving" :show-close="!taskDraftSaving">
        <p class="os-help">请核对并修改建议。只有明确点击「确认创建任务」才会写入本人任务列表；模型不会自动写入，也不会自动建立目标关系。</p>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="任务标题">
            <el-input v-model="taskDraftForm.title" maxlength="120" show-word-limit aria-label="任务标题" />
          </el-form-item>
          <el-form-item label="任务说明">
            <el-input v-model="taskDraftForm.description" type="textarea" :rows="3"
              maxlength="400" show-word-limit aria-label="任务说明" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="taskDraftForm.priority" aria-label="任务优先级">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button :disabled="taskDraftSaving" @click="clearTaskDraft">取消</el-button>
          <el-button type="primary" :loading="taskDraftSaving"
            :disabled="!taskDraftForm.title.trim() || !taskDraftOwnerToken || taskDraftOwnerToken !== auth.token"
            @click="saveAdviceTaskDraft">确认创建任务</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="chatSourceOpen" title="原始聊天来源 · 仅本人查看"
        width="min(92vw, 540px)" append-to-body destroy-on-close @closed="clearChatSource">
        <p class="os-help">仅在你点击时读取这一条本人聊天消息。不会自动发送给 AI 或 MCP。若聊天已删除，引用也会失效。</p>
        <p v-if="chatSourceBusy" role="status">正在核验消息来源…</p>
        <p v-else-if="chatSourceError" role="alert">{{ chatSourceError }}</p>
        <template v-else-if="chatSource">
          <small>消息 #{{ chatSource.messageId }} · {{ chatSource.sentAt }}</small>
          <pre class="os-chat-source-text">{{ chatSource.messageText }}</pre>
        </template>
        <template #footer><el-button @click="clearChatSource">关闭并清除本页来源内容</el-button></template>
      </el-dialog>

      <el-dialog v-model="correctionOpen" title="更正个人记忆" width="min(92vw, 480px)" destroy-on-close>
        <p class="os-help">保存后先生成待确认候选。确认新版本时才会替代旧事实。</p>
        <el-input v-model="correctionText" type="textarea" :rows="4" maxlength="512" show-word-limit />
        <template #footer>
          <el-button @click="correctionOpen = false">取消</el-button>
          <el-button type="primary" :disabled="!correctionText.trim()" :loading="actionBusy" @click="saveCorrection">提交更正候选</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<style scoped>
.os-chat-source-text { white-space:pre-wrap; overflow-wrap:anywhere; max-height:50vh; overflow-y:auto; padding:14px; border-radius:12px; background:var(--el-fill-color-light); font:inherit; font-size:13px; line-height:1.6 }

.personal-os-page { max-width: 1260px; margin: 0 auto; padding: 0 0 60px; }
.os-hero { background: linear-gradient(115deg,#172b45,#2b526a); color: #fff; border-radius: 22px; padding: 34px 38px; display: flex; align-items: end; justify-content: space-between; gap: 26px; }
.os-kicker { font-size: 11px; font-weight: 700; letter-spacing: .15em; opacity: .8; }
.os-hero h1 { font-size: clamp(23px,3vw,34px); line-height: 1.25; margin: 9px 0 12px; }
.os-intro { margin: 0; color: #d7e6ee; max-width: 620px; line-height: 1.7; }
.os-privacy { border: 1px solid #ffffff45; border-radius: 15px; padding: 14px 16px; width: 215px; background: #ffffff12; flex-shrink: 0; }
.os-privacy strong { display: block; font-size: 14px; margin-bottom: 7px; }
.os-privacy span { font-size: 12px; line-height: 1.6; color: #dfecf2; }
.os-alert { margin-top: 16px; }
.os-toolbar { margin: 22px 0; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.os-stats { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 13px; margin-bottom: 22px; }
.os-stats > div { padding: 18px; border: 1px solid var(--el-border-color-light); border-radius: 15px; background: var(--el-bg-color); }
.os-stats span { display: block; color: var(--el-text-color-secondary); font-size: 12px; }
.os-stats strong { display: block; font-size: 29px; line-height: 1.2; margin-top: 10px; }
.os-grid { display: grid; grid-template-columns: minmax(260px,360px) minmax(0,1fr); gap: 20px; align-items: start; }
.os-panel, .os-list-panel { border-radius: 17px; min-width: 0; }
.os-list-panel { padding: 3px 0; }
.os-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.os-form-row :deep(.el-date-editor) { width: 100%; }
.os-section-heading { display: flex; align-items: center; justify-content: space-between; margin: 0 0 14px; }
.os-section-heading h2 { font-size: 19px; margin: 0; }
.os-section-heading span,.os-section-heading a { color: var(--el-text-color-secondary); font-size: 13px; }
.os-goal-card,.os-memory-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 15px; padding: 16px; margin-bottom: 12px; }
.os-goal-card.selected { border-color: var(--el-color-primary); box-shadow: 0 2px 14px #2584b512; }
.os-goal-select { all: unset; cursor: pointer; display: grid; gap: 9px; width: 100%; box-sizing: border-box; }
.os-goal-top,.os-memory-heading { display: flex; align-items: center; justify-content: space-between; gap: 9px; }
.os-goal-top strong { font-size: 15px; }
.os-goal-select > span:not(.os-goal-top) { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.5; }
.os-goal-select small,.os-memory-card small,.os-evidence small { color: var(--el-text-color-placeholder); font-size: 12px; }
.os-card-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.os-card-actions .el-button { margin-left: 0; }
.os-context { margin-top: 19px; border-top: 1px solid var(--el-border-color-light); padding: 18px 3px; }
.os-context h3 { font-size: 15px; margin: 0 0 12px; }
.os-context p,.os-help { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.65; }
.os-evidence { border-left: 3px solid #6e99a8; padding: 5px 13px; display: grid; gap: 5px; margin-bottom: 12px; }
.os-evidence span { overflow-wrap: anywhere; }
.os-model-panel { border-top: 1px solid var(--el-border-color-light); margin-top: 18px; padding-top: 18px; min-width: 0; }
.os-model-panel :deep(.el-checkbox) { white-space: normal; height: auto; align-items: start; }
.os-model-panel :deep(.el-checkbox__label) { white-space: normal; line-height: 1.6; overflow-wrap: anywhere; }
.os-model-review,.os-model-results { margin-top: 15px; padding: 14px; border-radius: 12px; border: 1px solid var(--el-border-color-light); min-width: 0; }
.os-model-json { max-height: 300px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; line-height: 1.5; }
.os-model-proposal { padding: 12px 0; border-top: 1px solid var(--el-border-color-light); overflow-wrap: anywhere; }
.os-model-proposal p { margin: 7px 0; }
.os-model-proposal small { color: var(--el-text-color-secondary); }
.os-memory-card p { overflow-wrap: anywhere; white-space: pre-wrap; line-height: 1.65; }
.os-memory-heading strong { font-size: 14px; }
.os-secondary-heading { margin-top: 24px; }
.os-timeline { max-width: 800px; }
.os-timeline-item { display: grid; grid-template-columns: 105px minmax(0,1fr); border-left: 2px solid var(--el-border-color); padding: 8px 0 20px 20px; gap: 18px; margin-left: 12px; }
.os-timeline-item time { font-size: 12px; color: var(--el-text-color-secondary); }
.os-timeline-item h3 { font-size: 16px; margin: 0 0 8px; }
.os-timeline-item p { color: var(--el-text-color-regular); margin: 0 0 8px; line-height: 1.6; overflow-wrap: anywhere; white-space: pre-wrap; }
.os-timeline-item small { color: var(--el-text-color-placeholder); }
@media(max-width:820px) {
  .os-hero { align-items: stretch; flex-direction: column; padding: 25px 21px; }
  .os-privacy { width: auto; }
  .os-stats { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .os-grid { grid-template-columns: 1fr; gap: 18px; }
  .os-form-row { grid-template-columns: 1fr; gap: 0; }
  .os-timeline-item { grid-template-columns: 1fr; gap: 8px; }
}
</style>
