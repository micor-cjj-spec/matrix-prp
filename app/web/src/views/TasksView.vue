<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fallbackDomainModules, fetchDomainModules, type ModuleItem } from '@/api/modules'
import {
  createTask,
  deleteTask,
  fetchTasks,
  fetchTaskSummary,
  updateTask,
  updateTaskStatus,
  type TaskItem,
  type TaskSummary,
} from '@/api/tasks'
import AppLayout from '@/layouts/AppLayout.vue'
import { loadTaskResources } from '@/utils/taskLoading'
import { moduleLabel, priorityLabel } from '@/utils/labels'
import {
  filterAndRankTasks, getNextTask, taskProgress, moduleTaskProgress, type TaskSortOrder,
} from '@/utils/taskPlanning'

const route = useRoute()
const tasks = ref<TaskItem[]>([])
const summary = ref<TaskSummary>({
  openCount: 0,
  todayCount: 0,
  unscheduledCount: 0,
  overdueCount: 0,
  upcomingSevenDaysCount: 0,
  highPriorityOpenCount: 0,
  statusCounts: {},
})
const modules = ref<ModuleItem[]>(fallbackDomainModules)
const loading = ref(false)
const apiOnline = ref(false)
const summaryAvailable = ref(false)
const editDialogVisible = ref(false)
const editingTaskId = ref<number | null>(null)
const keyword = ref('')
const sortBy = ref<TaskSortOrder>('recommended')
const pendingStatusId = ref<number | null>(null)

const priorityOptions = [{ label: '低', value: 'low' }, { label: '中', value: 'medium' }, { label: '高', value: 'high' }]
const quickFilter = ref('all')
const quickFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '进行中', value: 'active' },
  { label: '待办', value: 'todo' },
  { label: '今日', value: 'today' },
  { label: '逾期', value: 'overdue' },
  { label: '待安排', value: 'unscheduled' },
  { label: '未来', value: 'future' },
]

function localDateString() {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const statusOptions = [
  { label: '待办', value: 'todo' },
  { label: '进行中', value: 'in_progress' },
  { label: '已完成', value: 'done' },
  { label: '已取消', value: 'canceled' },
]

const filters = reactive({
  status: '',
  moduleCode: '',
  dueDate: '',
  priority: '',
})

const visibleTasks = computed(() => filterAndRankTasks(tasks.value, {
  today: localDateString(),
  quickFilter: quickFilter.value,
  keyword: keyword.value,
  sortBy: sortBy.value,
  status: filters.status,
  moduleCode: filters.moduleCode,
  dueDate: filters.dueDate,
  priority: filters.priority,
}))
const progress = computed(() => taskProgress(tasks.value))
const moduleProgress = computed(() => moduleTaskProgress(tasks.value))
const nextTask = computed(() => getNextTask(tasks.value, localDateString()))

function selectModule(moduleCode: string) {
  filters.moduleCode = filters.moduleCode === moduleCode ? '' : moduleCode
  quickFilter.value = 'all'
}

const form = reactive({
  moduleCode: 'life',
  title: '',
  description: '',
  priority: 'medium',
  dueDate: localDateString() as string | null,
})

const editForm = reactive({
  moduleCode: 'life',
  title: '',
  description: '',
  priority: 'medium',
  dueDate: localDateString() as string | null,
})

async function loadTasks() {
  loading.value = true
  try {
    const { taskItems, summaryResult, moduleResult } = await loadTaskResources(
      fetchTasks, fetchTaskSummary, fetchDomainModules,
    )
    tasks.value = taskItems
    apiOnline.value = true

    if (summaryResult.status === 'fulfilled') {
      summary.value = summaryResult.value
      summaryAvailable.value = true
    } else {
      summaryAvailable.value = false
      ElMessage.warning('任务统计暂不可用，任务列表仍可操作')
    }
    if (moduleResult.status === 'fulfilled') {
      modules.value = moduleResult.value.filter((module) => module.enabled)
    } else {
      ElMessage.warning('模块目录暂不可用，已保留当前模块选项')
    }
  } catch {
    apiOnline.value = false
    summaryAvailable.value = false
    tasks.value = []
    ElMessage.error('任务读取失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function submitTask() {
  if (!form.title.trim()) return
  await createTask({ ...form })
  form.title = ''
  form.description = ''
  ElMessage.success('任务已创建')
  await loadTasks()
}

function openEditDialog(task: TaskItem) {
  editingTaskId.value = task.id
  editForm.moduleCode = task.moduleCode
  editForm.title = task.title
  editForm.description = task.description
  editForm.priority = task.priority
  editForm.dueDate = task.dueDate || null
  editDialogVisible.value = true
}

async function submitEditTask() {
  if (editingTaskId.value === null || !editForm.title.trim()) return
  await updateTask(editingTaskId.value, { ...editForm })
  editDialogVisible.value = false
  editingTaskId.value = null
  ElMessage.success('任务已更新')
  await loadTasks()
}

async function changeTaskStatus(task: TaskItem, status: string) {
  if (pendingStatusId.value !== null || task.status === status) return
  pendingStatusId.value = task.id
  try {
    await updateTaskStatus(task.id, status)
    await loadTasks()
  } catch {
    ElMessage.error('状态更新失败，请重试')
  } finally {
    pendingStatusId.value = null
  }
}

async function completeTask(task: TaskItem) {
  await changeTaskStatus(task, 'done')
}

async function removeTask(task: TaskItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${task.title}」吗？`, '删除任务', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteTask(task.id)
  ElMessage.success('任务已删除')
  await loadTasks()
}

function clearFilters() {
  filters.status = ''
  filters.moduleCode = ''
  filters.dueDate = ''
  filters.priority = ''
  quickFilter.value = 'all'
  keyword.value = ''
  sortBy.value = 'recommended'
}

function statusLabel(status: string) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'in_progress') return 'warning'
  if (status === 'canceled') return 'info'
  return 'primary'
}

function priorityTagType(priority: string) {
  if (priority === 'high') return 'danger'
  if (priority === 'low') return 'info'
  return 'warning'
}

function focusFromRoute() {
  const raw = route.query.focus
  if (typeof raw !== 'string' || !/^[1-9]\d*$/.test(raw)) return
  const found = tasks.value.find(task => task.id === Number(raw))
  if (found) openEditDialog(found)
  else ElMessage.warning('任务不存在或无权查看')
}
onMounted(async () => { await loadTasks(); focusFromRoute() })
watch(() => route.query.focus, async () => { await loadTasks(); focusFromRoute() })
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">任务管理</p>
        <h1>任务计划</h1>
        <p>管理今日和近期事项，把记录沉淀成下一步行动。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? '任务服务已连接' : '后端未连接，列表暂不可同步' }}
        </span>
      </div>
    </header>

    <p v-if="!summaryAvailable && apiOnline" class="tasks-result-count">任务统计暂不可用，列表数据和操作不受影响。</p>
    <section v-if="summaryAvailable" class="metric-grid">
      <article class="metric-card">
        <span>未完成</span>
        <strong>{{ summary.openCount }}</strong>
        <p>待办 {{ summary.statusCounts.todo || 0 }} / 进行中 {{ summary.statusCounts.in_progress || 0 }}</p>
      </article>
      <article class="metric-card">
        <span>今日到期</span>
        <strong>{{ summary.todayCount }}</strong>
        <p>仅今天到期且未完成</p>
      </article>
      <article class="metric-card">
        <span>待安排</span>
        <strong>{{ summary.unscheduledCount }}</strong>
        <p>尚未设置截止日期</p>
      </article>
      <article class="metric-card">
        <span>逾期</span>
        <strong>{{ summary.overdueCount }}</strong>
        <p>需要尽快处理</p>
      </article>
      <article class="metric-card">
        <span>未来 7 天</span>
        <strong>{{ summary.upcomingSevenDaysCount }}</strong>
        <p>高优先级 {{ summary.highPriorityOpenCount }}</p>
      </article>
    </section>

    <section class="tasks-insight" aria-label="任务进度和优先事项">
      <div class="tasks-progress-panel">
        <div class="tasks-insight-heading">
          <div>
            <span class="tasks-eyebrow">总体进度</span>
            <strong>已完成 {{ progress.done }} / {{ progress.total }} 项</strong>
          </div>
          <strong class="tasks-percent">{{ progress.percent }}%</strong>
        </div>
        <el-progress :percentage="progress.percent" :show-text="false" :stroke-width="10" />
        <p>进行中 {{ progress.inProgress }} 项 · 待办 {{ progress.todo }} 项 · 已取消不计入进度</p>
      </div>
      <div class="tasks-focus-panel">
        <span class="tasks-eyebrow">下一步优先处理</span>
        <template v-if="nextTask">
          <strong>{{ nextTask.title }}</strong>
          <p>{{ moduleLabel(nextTask.moduleCode) }} · {{ statusLabel(nextTask.status) }} · {{ priorityLabel(nextTask.priority) }}优先级 · {{ nextTask.dueDate || '未安排截止日期' }}</p>
          <div class="tasks-focus-actions">
            <el-button size="small" @click="openEditDialog(nextTask)">查看 / 编辑</el-button>
            <el-button v-if="nextTask.status === 'todo'" size="small" type="primary"
              :disabled="pendingStatusId !== null" :loading="pendingStatusId === nextTask.id"
              @click="changeTaskStatus(nextTask, 'in_progress')">开始任务</el-button>
            <el-button v-if="nextTask.status === 'in_progress'" size="small" type="primary"
              :disabled="pendingStatusId !== null" :loading="pendingStatusId === nextTask.id"
              @click="completeTask(nextTask)">标记完成</el-button>
          </div>
        </template>
        <p v-else>当前没有待处理任务，可以新建一项计划。</p>
        <small>按进行中、逾期、今日到期与优先级推荐；不是 AI 自动决策。</small>
      </div>
    </section>

    <section v-if="moduleProgress.length" class="tasks-module-section" aria-label="按模块查看任务进度">
      <div class="tasks-module-heading">
        <h2>模块进度</h2>
        <span>点击模块即可筛选任务，再次点击取消筛选</span>
      </div>
      <div class="tasks-module-grid">
        <button v-for="item in moduleProgress" :key="item.moduleCode" type="button"
          class="tasks-module-item" :class="{ selected: filters.moduleCode === item.moduleCode }"
          :aria-pressed="filters.moduleCode === item.moduleCode" @click="selectModule(item.moduleCode)">
          <span class="tasks-module-name">{{ moduleLabel(item.moduleCode) }} <b>{{ item.percent }}%</b></span>
          <el-progress :percentage="item.percent" :show-text="false" :stroke-width="5" />
          <small>{{ item.inProgress }} 进行中 · {{ item.todo }} 待办 · {{ item.done }} 已完成</small>
        </button>
      </div>
    </section>

    <section class="work-grid">
      <el-card shadow="never">
        <template #header>新增任务</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="模块">
            <el-select v-model="form.moduleCode">
              <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="form.title" placeholder="任务标题" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="3" placeholder="任务说明" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-segmented v-model="form.priority" :options="priorityOptions" />
          </el-form-item>
          <el-form-item label="截止日期">
            <el-date-picker v-model="form.dueDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="submitTask">保存任务</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>任务列表</template>
        <div class="filter-row">
          <el-select v-model="filters.status" clearable placeholder="按状态筛选">
            <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
          </el-select>
          <el-select v-model="filters.moduleCode" clearable placeholder="按模块筛选">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
          <el-select v-model="filters.priority" clearable placeholder="按优先级筛选">
            <el-option v-for="priority in priorityOptions" :key="priority.value" :label="priority.label" :value="priority.value" />
          </el-select>
          <el-date-picker v-model="filters.dueDate" type="date" value-format="YYYY-MM-DD" placeholder="按截止日期筛选" />
          <el-button @click="clearFilters">清空</el-button>
        </div>

        <div class="tasks-search-row">
          <el-input v-model="keyword" clearable aria-label="搜索任务" placeholder="搜索任务标题或描述" />
          <el-select v-model="sortBy" aria-label="任务排序方式" class="tasks-sort">
            <el-option label="智能优先排序" value="recommended" />
            <el-option label="截止日期优先" value="due" />
            <el-option label="最近创建优先" value="recent" />
          </el-select>
        </div>
        <div class="tasks-quick-filters">
          <el-segmented v-model="quickFilter" :options="quickFilterOptions" />
        </div>
        <p class="tasks-result-count">显示 {{ visibleTasks.length }} / {{ tasks.length }} 项任务</p>
        <el-empty v-if="visibleTasks.length === 0" description="没有符合筛选条件的任务" />
        <div v-else class="item-list">
          <article v-for="task in visibleTasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <div class="item-actions">
                <el-tag :type="priorityTagType(task.priority)">{{ priorityLabel(task.priority) }}</el-tag>
                <el-tag :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
                <el-button size="small" text @click="openEditDialog(task)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeTask(task)">删除</el-button>
              </div>
            </div>
            <span>{{ moduleLabel(task.moduleCode) }} · {{ task.dueDate || '无截止日期' }}</span>
            <p>{{ task.description || '无描述' }}</p>
            <div class="item-actions">
              <el-select
                :model-value="task.status"
                :disabled="pendingStatusId !== null"
                size="small"
                class="status-select"
                @change="(status: string) => changeTaskStatus(task, status)"
              >
                <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
              </el-select>
              <el-button v-if="task.status === 'todo'" size="small" :disabled="pendingStatusId !== null"
                  @click="changeTaskStatus(task, 'in_progress')">开始</el-button>
                <el-button v-if="task.status === 'in_progress'" size="small" type="primary"
                  :disabled="pendingStatusId !== null" :loading="pendingStatusId === task.id"
                  @click="completeTask(task)">完成</el-button>
            </div>
          </article>
        </div>
      </el-card>
    </section>

    <el-dialog v-model="editDialogVisible" title="编辑任务" width="520px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="模块">
          <el-select v-model="editForm.moduleCode">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="editForm.title" placeholder="任务标题" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="任务说明" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-segmented v-model="editForm.priority" :options="priorityOptions" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="editForm.dueDate" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitEditTask">保存</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>

<style scoped>
.tasks-insight {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.tasks-progress-panel, .tasks-focus-panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid #dde6f2;
  border-radius: 14px;
  background: #fff;
}
.tasks-focus-panel {
  background: linear-gradient(135deg, #f4f8ff, #fff);
}
.tasks-insight-heading, .tasks-module-name {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.tasks-insight-heading { margin-bottom: 16px; }
.tasks-insight-heading > div { display: grid; gap: 6px; }
.tasks-eyebrow { font-size: 12px; color: #64748b; }
.tasks-insight strong { font-size: 16px; color: #172b4a; }
.tasks-percent { color: #2865ec !important; font-size: 24px !important; }
.tasks-insight p { margin: 12px 0 0; font-size: 12px; color: #64748b; }
.tasks-focus-panel > strong { display: block; margin-top: 8px; overflow-wrap: anywhere; }
.tasks-focus-panel small { display: block; margin-top: 12px; font-size: 11px; color: #71809a; }
.tasks-focus-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.tasks-module-section { margin-bottom: 20px; }
.tasks-module-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.tasks-module-heading h2 { font-size: 16px; margin: 0; }
.tasks-module-heading > span { color: #71809a; font-size: 12px; }
.tasks-module-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.tasks-module-item { cursor: pointer; padding: 14px; border: 1px solid #dde6f2; border-radius: 12px; background: #fff; text-align: left; color: inherit; min-width: 0; }
.tasks-module-item:hover, .tasks-module-item.selected { border-color: #6796ef; background: #f4f8ff; }
.tasks-module-item:focus-visible { outline: 2px solid #2865ec; outline-offset: 2px; }
.tasks-module-name { font-size: 13px; font-weight: 600; margin-bottom: 10px; }
.tasks-module-name b { color: #2865ec; }
.tasks-module-item small { display: block; font-size: 11px; color: #64748b; margin-top: 8px; }
.tasks-search-row { display: grid; grid-template-columns: minmax(0, 1fr) 170px; gap: 10px; margin-bottom: 14px; }
.tasks-sort { width: 100%; }
.tasks-quick-filters { max-width: 100%; overflow-x: auto; padding-bottom: 4px; }
.tasks-result-count { margin: 10px 0 14px; color: #64748b; font-size: 12px; }
@media (max-width: 760px) {
  .tasks-insight { grid-template-columns: 1fr; }
  .tasks-search-row { grid-template-columns: 1fr; }
  .tasks-module-grid { grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); }
}
</style>
