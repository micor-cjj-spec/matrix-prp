<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
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

const tasks = ref<TaskItem[]>([])
const summary = ref<TaskSummary>({
  openCount: 0,
  todayCount: 0,
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

const priorityOptions = ['low', 'medium', 'high']
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
  dueDate: new Date().toISOString().slice(0, 10),
})

const editForm = reactive({
  moduleCode: 'life',
  title: '',
  description: '',
  priority: 'medium',
  dueDate: new Date().toISOString().slice(0, 10),
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
  editForm.dueDate = task.dueDate || new Date().toISOString().slice(0, 10)
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
        <p class="eyebrow">Tasks</p>
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
        <p>todo {{ summary.statusCounts.todo || 0 }} / doing {{ summary.statusCounts.in_progress || 0 }}</p>
      </article>
      <article class="metric-card">
        <span>今日关注</span>
        <strong>{{ summary.todayCount }}</strong>
        <p>无截止日期或今天到期</p>
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
            <el-option v-for="priority in priorityOptions" :key="priority" :label="priority" :value="priority" />
          </el-select>
          <el-date-picker v-model="filters.dueDate" type="date" value-format="YYYY-MM-DD" placeholder="按截止日期筛选" @change="loadTasks" />
          <el-button @click="clearFilters">清空</el-button>
        </div>

        <el-empty v-if="tasks.length === 0" description="暂无任务" />
        <div v-else class="item-list">
          <article v-for="task in tasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <div class="item-actions">
                <el-tag :type="priorityTagType(task.priority)">{{ task.priority }}</el-tag>
                <el-tag :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
                <el-button size="small" text @click="openEditDialog(task)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeTask(task)">删除</el-button>
              </div>
            </div>
            <span>{{ task.moduleCode }} · {{ task.dueDate || '无截止日期' }}</span>
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
