<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/layouts/AppLayout.vue'
import { fetchRecords, type RecordItem } from '@/api/records'
import {
  changePersonalGoalStatus, confirmPersonalMemory, createPersonalGoal,
  erasePersonalMemory, fetchConfirmedMemories, fetchMemoryCandidates,
  fetchPersonalGoalContext, fetchPersonalGoals, fetchPrivateMemories, invalidatePersonalMemory,
  proposePersonalMemory, replacePersonalMemory,
  type GoalStatus, type MemoryPredicate, type MemorySensitivity,
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
const privateFacts = ref<PersonalMemory[]>([])
const privateOpen = ref(false)
const privateLoading = ref(false)
let privateRequestGeneration = 0
const records = ref<RecordItem[]>([])
const timelineDomain = ref('life')
const selectedGoalId = ref<number | null>(null)
const context = ref<PersonalGoalLink[]>([])
const contextLoading = ref(false)
const correctionTarget = ref<PersonalMemory | null>(null)
const correctionText = ref('')
const correctionRequestKey = ref('')
const correctionOpen = ref(false)

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

// These fields are never fetched during page initialization or general refresh.
async function togglePrivateMemories() {
  if (privateOpen.value) {
    ++privateRequestGeneration
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
  loading.value = true
  serviceError.value = ''
  try {
    const [goalData, candidateData, memoryData, recordData] = await Promise.all([
      fetchPersonalGoals(), fetchMemoryCandidates(), fetchConfirmedMemories(),
      fetchRecords({ moduleCode: timelineDomain.value || undefined }),
    ])
    goals.value = goalData
    candidates.value = candidateData
    memories.value = memoryData
    records.value = recordData
    await refreshPrivateIfOpen()
    if (selectedGoalId.value !== null && !goalData.some(item => item.id === selectedGoalId.value)) {
      selectedGoalId.value = null
      context.value = []
    }
  } catch {
    // Do not leave owner-specific data rendered after a 401, token change,
    // failed refresh, or transient response error.
    goals.value = []
    candidates.value = []
    memories.value = []
    records.value = []
    context.value = []
    selectedGoalId.value = null
    ++privateRequestGeneration
    privateFacts.value = []
    privateOpen.value = false
    serviceError.value = '数据暂时无法加载。请确认 Personal OS 后端版本已部署且账号已登录。'
  } finally {
    loading.value = false
  }
}

async function selectGoal(id: number) {
  selectedGoalId.value = id
  contextLoading.value = true
  try {
    context.value = await fetchPersonalGoalContext(id)
  } catch {
    context.value = []
    ElMessage.error('目标关联证据加载失败')
  } finally {
    contextLoading.value = false
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
      '确认后会成为已确认的个人事实。请核对内容、来源和敏感级别。',
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
  if (item.objectType !== 'LITERAL'
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

// Private facts must not persist across tabs, even while the view remains mounted.
watch(activeTab, (next) => {
  if (next !== 'memory') {
    ++privateRequestGeneration
    privateOpen.value = false
    privateFacts.value = []
  }
})

onUnmounted(() => {
  ++privateRequestGeneration
  privateOpen.value = false
  privateFacts.value = []
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
        <div><span>待确认记忆</span><strong>{{ candidates.length }}</strong></div>
        <div><span>可查询的普通记忆</span><strong>{{ memories.length }}</strong></div>
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
              <span>{{ link.objectValue || (link.objectType + ' #' + (link.objectRef || '—')) }}</span>
              <small>事实 #{{ link.assertionId }} · 已确认</small>
            </div>
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
              <el-tag size="small" type="warning">{{ item.sensitivity === 'NORMAL' ? '普通' : '受限/敏感' }}</el-tag></div>
            <p>{{ describeMemory(item) }}</p>
            <small>来源 {{ item.sourceType }}{{ item.sourceRef ? ' #' + item.sourceRef : '' }} · {{ item.createdAt.slice(0, 10) }}</small>
            <div class="os-card-actions">
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
            <small>来源 {{ item.sourceType }}{{ item.sourceRef ? ' #' + item.sourceRef : '' }} · {{ item.createdAt.slice(0, 10) }}</small>
            <div class="os-card-actions">
              <el-button v-if="item.objectType === 'LITERAL'" size="small" :disabled="actionBusy"
                @click="openCorrection(item)">更正</el-button>
              <el-button size="small" :disabled="actionBusy" @click="invalidateCandidate(item)">作废</el-button>
              <el-button size="small" text type="danger" :disabled="actionBusy" @click="eraseMemory(item)">永久删除</el-button>
            </div>
          </article>

          <section class="os-private" aria-label="受限记忆管理">
            <div class="os-section-heading os-secondary-heading">
              <h2>受限 / 敏感记忆</h2>
              <el-button :loading="privateLoading" @click="togglePrivateMemories">
                {{ privateOpen ? '收起并清除本页内容' : '主动查看并管理' }}
              </el-button>
            </div>
            <p class="os-help">默认不读取这些事实。只有点击查看才会向后端请求；不会发送给 AI 或 MCP。</p>
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
                <small>来源 {{ item.sourceType }} · 事实 #{{ item.id }}</small>
                <div class="os-card-actions">
                  <el-button v-if="item.objectType === 'LITERAL'" size="small"
                    :disabled="actionBusy" @click="openCorrection(item)">更正</el-button>
                  <el-button size="small" :disabled="actionBusy" @click="invalidateCandidate(item)">作废</el-button>
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
