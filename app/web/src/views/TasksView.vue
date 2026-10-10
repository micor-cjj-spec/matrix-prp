<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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
import { moduleLabel, priorityLabel } from '@/utils/labels'

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
const editDialogVisible = ref(false)
const editingTaskId = ref<number | null>(null)

const priorityOptions = [{ label: '低', value: 'low' }, { label: '中', value: 'medium' }, { label: '高', value: 'high' }]
const quickFilter = ref('all')
const quickFilterOptions = [
  { label: '全部', value: 'all' },
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

const visibleTasks = computed(() => {
  const today = localDateString()
  return tasks.value.filter((task) => {
    if (quickFilter.value === 'all') return true
    if (task.status === 'done' || task.status === 'canceled') return false
    if (quickFilter.value === 'today') return task.dueDate === today
    if (quickFilter.value === 'overdue') return !!task.dueDate && task.dueDate < today
    if (quickFilter.value === 'unscheduled') return !task.dueDate
    if (quickFilter.value === 'future') return !!task.dueDate && task.dueDate > today
    return true
  })
})
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
    const [taskItems, taskSummary, domainModules] = await Promise.all([
      fetchTasks({
        status: filters.status || undefined,
        moduleCode: filters.moduleCode || undefined,
        dueDate: filters.dueDate || undefined,
        priority: filters.priority || undefined,
      }),
      fetchTaskSummary(),
      fetchDomainModules(),
    ])
    tasks.value = taskItems
    summary.value = taskSummary
    modules.value = domainModules.filter((module) => module.enabled)
    apiOnline.value = true
  } catch {
    apiOnline.value = false
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
  await updateTaskStatus(task.id, status)
  await loadTasks()
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
  void loadTasks()
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

onMounted(loadTasks)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">任务管理</p>
        <h1>任务计划</h1>
        <p>管理今日和近期事项，把记录沉淀成下一步行动。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? 'Tasks API 已连接' : '后端未连接，列表暂不可同步' }}
        </span>
      </div>
    </header>

    <section class="metric-grid">
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
          <el-select v-model="filters.status" clearable placeholder="按状态筛选" @change="loadTasks" @clear="loadTasks">
            <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
          </el-select>
          <el-select v-model="filters.moduleCode" clearable placeholder="按模块筛选" @change="loadTasks" @clear="loadTasks">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
          <el-select v-model="filters.priority" clearable placeholder="按优先级筛选" @change="loadTasks" @clear="loadTasks">
            <el-option v-for="priority in priorityOptions" :key="priority.value" :label="priority.label" :value="priority.value" />
          </el-select>
          <el-date-picker v-model="filters.dueDate" type="date" value-format="YYYY-MM-DD" placeholder="按截止日期筛选" @change="loadTasks" />
          <el-button @click="clearFilters">清空</el-button>
        </div>

        <div class="filter-row">
          <el-segmented v-model="quickFilter" :options="quickFilterOptions" />
        </div>
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
                size="small"
                class="status-select"
                @change="(status: string) => changeTaskStatus(task, status)"
              >
                <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
              </el-select>
              <el-button v-if="task.status !== 'done'" size="small" @click="completeTask(task)">完成</el-button>
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
