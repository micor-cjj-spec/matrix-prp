<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { updateTaskStatus } from '@/api/tasks'
import { Document, EditPen, Money, Notebook, Operation, Tickets } from '@element-plus/icons-vue'
import { fetchDashboardSummary, type DashboardSummary } from '@/api/dashboard'
import { fetchRuntimeHealth, type RuntimeHealth } from '@/api/health'
import AppLayout from '@/layouts/AppLayout.vue'
import { moduleLabel, priorityLabel, taskStatusLabel } from '@/utils/labels'

const iconMap = {
  records: Document,
  tasks: Tickets,
  finance: Money,
  reviews: EditPen,
  knowledge: Notebook,
}

const fallbackSummary: DashboardSummary = {
  date: new Date().toISOString().slice(0, 10),
  todayTaskCount: 0,
  overdueTaskCount: 0,
  unscheduledTaskCount: 0,
  recentRecordCount: 0,
  monthlyIncome: '0',
  monthlyExpense: '0',
  monthlyBalance: '0',
  todayTasks: [],
  overdueTasks: [],
  unscheduledTasks: [],
  highPriorityTasks: [],
  recentRecords: [],
  modules: [
    { code: 'records', name: '记录管理', description: '沉淀学习、生活、工作和兴趣记录', enabled: true },
    { code: 'tasks', name: '任务计划', description: '管理今日任务和近期计划', enabled: true },
    { code: 'finance', name: '财务管理', description: '记录收入支出并查看月度概览', enabled: true },
    { code: 'reviews', name: '复盘中心', description: '沉淀周、月和模块复盘', enabled: true },
    { code: 'knowledge', name: '知识库', description: '浏览现有 Markdown 知识库', enabled: true },
  ],
}

const summary = ref<DashboardSummary>(fallbackSummary)
const runtime = ref<RuntimeHealth | null>(null)
const loading = ref(true)
const apiOnline = ref(false)
const completingTaskId = ref<number | null>(null)

const formatCurrency = (value: string) =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
  }).format(Number(value))

const metrics = computed(() => [
  { label: '今日任务', value: String(summary.value.todayTaskCount), hint: '需要关注的行动' },
  { label: '逾期任务', value: String(summary.value.overdueTaskCount), hint: '需要尽快处理' },
  { label: '待安排', value: String(summary.value.unscheduledTaskCount), hint: '尚无截止日期' },
  { label: '本月支出', value: formatCurrency(summary.value.monthlyExpense), hint: '月度现金流' },
  { label: '最近记录', value: String(summary.value.recentRecordCount), hint: '过程沉淀' },
])

const runtimeStatus = computed(() => {
  if (!runtime.value) return '运行环境未确认'
  return `${runtime.value.persistence} · ${runtime.value.database} · 知识库${runtime.value.knowledgeAvailable ? '可用' : '不可用'}`
})

const modules = computed(() =>
  summary.value.modules.map((module) => ({
    ...module,
    icon: iconMap[module.code as keyof typeof iconMap] ?? Document,
  })),
)

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'in_progress') return 'warning'
  if (status === 'canceled') return 'info'
  return 'primary'
}

async function completeTask(id: number) {
  if (!apiOnline.value || completingTaskId.value !== null) return
  completingTaskId.value = id
  try {
    await updateTaskStatus(id, 'done')
    summary.value = await fetchDashboardSummary()
    ElMessage.success('任务已完成')
  } catch {
    ElMessage.error('完成任务失败，请重试')
  } finally {
    completingTaskId.value = null
  }
}

onMounted(async () => {
  try {
    const [nextSummary, nextRuntime] = await Promise.all([
      fetchDashboardSummary(),
      fetchRuntimeHealth(),
    ])
    summary.value = nextSummary
    runtime.value = nextRuntime
    apiOnline.value = true
  } catch {
    summary.value = fallbackSummary
    runtime.value = null
    apiOnline.value = false
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">今日概览</p>
        <h1>个人资源管理工作台</h1>
        <p>集中查看今日任务、财务、记录和知识库，随时掌握个人计划。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ loading ? '正在连接服务' : apiOnline ? '服务已连接' : '后端未连接，显示本地占位数据' }}
        </span>
        <span class="api-status" :class="{ online: runtime?.status === 'UP' }">
          {{ runtimeStatus }}
        </span>
      </div>
      <RouterLink class="el-button el-button--primary" to="/records">
        <el-icon><Operation /></el-icon>
        <span>快速记录</span>
      </RouterLink>
    </header>

    <section class="metric-grid">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <p>{{ metric.hint }}</p>
      </article>
    </section>

    <section class="dashboard-grid">
      <el-card shadow="never">
        <template #header><div class="list-item-row"><span>今日待办</span><RouterLink to="/tasks">管理任务</RouterLink></div></template>
        <el-empty v-if="summary.todayTasks.length === 0" description="暂无今日任务" />
        <div v-else class="item-list">
          <article v-for="task in summary.todayTasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <div class="item-actions">
                <el-tag :type="statusTagType(task.status)">{{ taskStatusLabel(task.status) }}</el-tag>
                <el-button size="small" type="success" plain
                  :loading="completingTaskId === task.id"
                  :disabled="!apiOnline || completingTaskId !== null"
                  @click="completeTask(task.id)">完成</el-button>
              </div>
            </div>
            <span>{{ moduleLabel(task.moduleCode) }} · {{ priorityLabel(task.priority) }} · {{ task.dueDate || '无截止日期' }}</span>
            <p>{{ task.description || '无描述' }}</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>逾期任务</template>
        <el-empty v-if="summary.overdueTasks.length === 0" description="没有逾期任务" />
        <div v-else class="item-list">
          <article v-for="task in summary.overdueTasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <el-button size="small" type="success" plain
                :loading="completingTaskId === task.id"
                :disabled="!apiOnline || completingTaskId !== null"
                @click="completeTask(task.id)">完成</el-button>
            </div>
            <span>{{ moduleLabel(task.moduleCode) }} · 截止 {{ task.dueDate }}</span>
            <p>{{ task.description || '无描述' }}</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>待安排（无截止日期）</template>
        <el-empty v-if="summary.unscheduledTasks.length === 0" description="暂无待安排任务" />
        <div v-else class="item-list">
          <article v-for="task in summary.unscheduledTasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <div class="item-actions">
                <RouterLink to="/tasks">设置日期</RouterLink>
                <el-button size="small" type="success" plain
                  :loading="completingTaskId === task.id"
                  :disabled="!apiOnline || completingTaskId !== null"
                  @click="completeTask(task.id)">完成</el-button>
              </div>
            </div>
            <span>{{ moduleLabel(task.moduleCode) }} · {{ priorityLabel(task.priority) }}</span>
            <p>{{ task.description || '无描述' }}</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>高优先级</template>
        <el-empty v-if="summary.highPriorityTasks.length === 0" description="暂无高优先级任务" />
        <div v-else class="item-list">
          <article v-for="task in summary.highPriorityTasks" :key="task.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ task.title }}</strong>
              <el-tag type="danger">高优先级</el-tag>
            </div>
            <span>{{ moduleLabel(task.moduleCode) }} · {{ taskStatusLabel(task.status) }} · {{ task.dueDate || '无截止日期' }}</span>
            <p>{{ task.description || '无描述' }}</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>最近记录</template>
        <el-empty v-if="summary.recentRecords.length === 0" description="暂无记录" />
        <div v-else class="item-list">
          <article v-for="record in summary.recentRecords" :key="record.id" class="list-item">
            <strong>{{ record.title }}</strong>
            <span>{{ moduleLabel(record.moduleCode) }} · {{ record.recordDate }}</span>
            <p>{{ record.content || '无内容' }}</p>
          </article>
        </div>
      </el-card>
    </section>

    <section class="module-grid">
      <RouterLink v-for="module in modules" :key="module.code" class="module-card" :to="`/${module.code}`">
        <el-icon>
          <component :is="module.icon" />
        </el-icon>
        <div>
          <h2>{{ module.name }}</h2>
          <p>{{ module.description }}</p>
        </div>
      </RouterLink>
    </section>
  </AppLayout>
</template>
