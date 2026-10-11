<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowRight, Calendar, Check, Clock, Document, Food, House,
  Money, Reading, Tickets, VideoCamera
} from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { fetchDashboardSummary, type DashboardSummary } from '@/api/dashboard'
import { wellnessApi, type DailySummary } from '@/api/wellness'
import { updateTaskStatus } from '@/api/tasks'
import { moduleLabel, priorityLabel } from '@/utils/labels'

const summary = ref<DashboardSummary | null>(null)
const wellness = ref<DailySummary | null>(null)
const loading = ref(true)
const taskError = ref('')
const wellnessError = ref('')
const pendingTask = ref<number | null>(null)
const now = new Date()
const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2,'0'), String(now.getDate()).padStart(2,'0')].join('-')
const dateLabel = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(now)
const formatMoney = (n: string | number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 0 }).format(Number(n))

const todoItems = computed(() => [
  ...(summary.value?.todayTasks ?? []),
  ...(summary.value?.overdueTasks ?? []),
  ...(summary.value?.unscheduledTasks ?? []),
].filter((task, index, list) => list.findIndex(item => item.id === task.id) === index).slice(0, 6))
const todayCalorie = computed(() => wellness.value?.calories == null ? null : Math.round(Number(wellness.value.calories)))
const kcalGoal = computed(() => wellness.value?.goal ? Number(wellness.value.goal.dailyCalories) : null)
const caloriesRate = computed(() => kcalGoal.value && todayCalorie.value != null
  ? Math.min(100, Math.round(todayCalorie.value / kcalGoal.value * 100)) : null)
const taskCount = computed(() => summary.value
  ? summary.value.todayTaskCount + summary.value.overdueTaskCount + summary.value.unscheduledTaskCount : null)

async function refresh() {
  loading.value = true
  const [tasksResult, wellnessResult] = await Promise.allSettled([
    fetchDashboardSummary(), wellnessApi.daily(today),
  ])
  if (tasksResult.status === 'fulfilled') {
    summary.value = tasksResult.value
    taskError.value = ''
  } else {
    taskError.value = '任务与财务数据暂时无法读取'
  }
  if (wellnessResult.status === 'fulfilled') {
    wellness.value = wellnessResult.value
    wellnessError.value = ''
  } else {
    wellnessError.value = '健康数据暂时无法读取'
  }
  loading.value = false
}
async function completeTask(id: number) {
  if (pendingTask.value !== null) return
  pendingTask.value = id
  try {
    await updateTaskStatus(id, 'done')
    summary.value = await fetchDashboardSummary()
    ElMessage.success('任务已完成')
  } catch {
    ElMessage.error('更新任务失败，请重试')
  } finally {
    pendingTask.value = null
  }
}
onMounted(refresh)
</script>

<template>
  <AppLayout>
    <div class="home-page">
      <header class="home-heading">
        <div>
          <p class="home-date">{{ dateLabel }}</p>
          <h1>你好，今天也加油！ <span aria-hidden="true">☀️</span></h1>
          <p>从一个小行动开始，安排好今天的学习与生活。</p>
        </div>
        <RouterLink to="/tasks" class="home-plan-link">查看我的计划 <el-icon><ArrowRight /></el-icon></RouterLink>
      </header>

      <section class="home-metrics" aria-label="今日概览">
        <RouterLink to="/tasks" class="home-metric metric-tasks">
          <div class="home-metric-top"><span>待处理任务</span><el-icon><Tickets /></el-icon></div>
          <strong>{{ loading || taskCount === null ? '—' : taskCount }}</strong>
          <small>{{ taskError || (summary ? '今日 '+summary.todayTaskCount+' 项 · 逾期 '+summary.overdueTaskCount+' 项' : '暂无任务数据') }}</small>
        </RouterLink>
        <RouterLink to="/learning" class="home-metric metric-learning">
          <div class="home-metric-top"><span>学习空间</span><el-icon><Reading /></el-icon></div>
          <strong>继续学习</strong>
          <small>视频课程、学习记录与知识整理</small>
        </RouterLink>
        <RouterLink to="/wellness" class="home-metric metric-health">
          <div class="home-metric-top"><span>今日摄入热量</span><el-icon><Food /></el-icon></div>
          <strong>{{ todayCalorie === null ? '未记录' : todayCalorie + ' kcal' }}</strong>
          <small>{{ wellnessError || (kcalGoal ? '每日目标 '+kcalGoal+' kcal' : '记录饮食，掌握每日变化') }}</small>
          <div v-if="caloriesRate !== null" class="home-meter"><span :style="{width: caloriesRate + '%'}" /></div>
        </RouterLink>
        <RouterLink to="/finance" class="home-metric metric-finance">
          <div class="home-metric-top"><span>本月支出</span><el-icon><Money /></el-icon></div>
          <strong>{{ summary ? formatMoney(summary.monthlyExpense) : '—' }}</strong>
          <small>{{ taskError || (summary ? '本月结余 '+formatMoney(summary.monthlyBalance) : '暂无财务数据') }}</small>
        </RouterLink>
      </section>

      <div class="home-main-grid">
        <section class="home-panel">
          <div class="home-panel-heading"><div><h2>今日任务</h2><p>聚焦当下最重要的行动</p></div><RouterLink to="/tasks">查看全部 <el-icon><ArrowRight /></el-icon></RouterLink></div>
          <div v-if="taskError" class="home-empty">{{ taskError }}。<button type="button" @click="refresh">重新加载</button></div>
          <div v-else-if="loading" class="home-empty">正在读取任务…</div>
          <div v-else-if="todoItems.length === 0" class="home-empty">暂无需要处理的任务。<RouterLink to="/tasks">创建一项任务</RouterLink></div>
          <div v-else class="home-task-list">
            <div v-for="task in todoItems" :key="task.id" class="home-task">
              <el-button circle plain :disabled="pendingTask !== null"
                :loading="pendingTask === task.id" aria-label="完成任务" @click="completeTask(task.id)">
                <el-icon><Check /></el-icon>
              </el-button>
              <div class="home-task-copy"><strong>{{ task.title }}</strong><small>{{ moduleLabel(task.moduleCode) }} · {{ priorityLabel(task.priority) }} · {{ task.dueDate || '待安排' }}</small></div>
              <span v-if="task.dueDate && task.dueDate < today" class="home-task-tag is-late">已逾期</span>
              <span v-else-if="task.dueDate === today" class="home-task-tag">今天</span>
            </div>
          </div>
          <div class="home-panel-footer"><RouterLink to="/tasks">安排更多任务 <el-icon><Calendar /></el-icon></RouterLink></div>
        </section>

        <section class="home-panel">
          <div class="home-panel-heading"><div><h2>各领域概览</h2><p>你最重要的四个生活空间</p></div></div>
          <div class="home-domain-grid">
            <RouterLink to="/learning" class="home-domain-card color-learning"><span class="home-domain-icon"><el-icon><Reading /></el-icon></span><div><h3>学习</h3><p>视频课程 · 学习记录<br>知识整理 · 学习计划</p></div><el-icon class="home-domain-arrow"><ArrowRight /></el-icon></RouterLink>
            <RouterLink to="/wellness" class="home-domain-card color-health"><span class="home-domain-icon"><el-icon><Food /></el-icon></span><div><h3>健康</h3><p>饮食热量 · 运动管理<br>体重趋势 · 健康目标</p></div><el-icon class="home-domain-arrow"><ArrowRight /></el-icon></RouterLink>
            <RouterLink to="/life" class="home-domain-card color-life"><span class="home-domain-icon"><el-icon><House /></el-icon></span><div><h3>生活</h3><p>任务计划 · 生活记录<br>消息提醒 · 周期复盘</p></div><el-icon class="home-domain-arrow"><ArrowRight /></el-icon></RouterLink>
            <RouterLink to="/finance" class="home-domain-card color-finance"><span class="home-domain-icon"><el-icon><Money /></el-icon></span><div><h3>财务</h3><p>账户管理 · 收支记录<br>分类统计 · 财务分析</p></div><el-icon class="home-domain-arrow"><ArrowRight /></el-icon></RouterLink>
          </div>
        </section>
      </div>

      <div class="home-quick-grid">
        <RouterLink to="/videos" class="home-quick-card"><el-icon><VideoCamera /></el-icon><div><strong>继续看课程</strong><span>打开视频学习库</span></div><el-icon><ArrowRight /></el-icon></RouterLink>
        <RouterLink to="/records" class="home-quick-card"><el-icon><Document /></el-icon><div><strong>记录这一刻</strong><span>留下今天的学习与生活</span></div><el-icon><ArrowRight /></el-icon></RouterLink>
        <RouterLink to="/wellness" class="home-quick-card"><el-icon><Clock /></el-icon><div><strong>健康打卡</strong><span>添加饮食、运动或体重</span></div><el-icon><ArrowRight /></el-icon></RouterLink>
      </div>
    </div>
  </AppLayout>
</template>
