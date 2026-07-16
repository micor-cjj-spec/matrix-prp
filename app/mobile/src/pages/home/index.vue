<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { clearToken } from '@/api/client'
import { fetchDashboardSummary, type DashboardSummary } from '@/api/dashboard'
import { fetchFinanceMonthlySummary, type FinanceMonthlySummary } from '@/api/finance'
import { fetchTaskSummary, updateTaskStatus, type TaskItem, type TaskSummary } from '@/api/tasks'

const summary = ref<DashboardSummary>({
  date: new Date().toISOString().slice(0, 10),
  todayTaskCount: 0,
  overdueTaskCount: 0,
  recentRecordCount: 0,
  monthlyIncome: '0',
  monthlyExpense: '0',
  monthlyBalance: '0',
  todayTasks: [],
  highPriorityTasks: [],
  recentRecords: [],
})
const financeSummary = ref<FinanceMonthlySummary>({ income: '0', expense: '0', balance: '0' })
const taskSummary = ref<TaskSummary>({
  openCount: 0,
  todayCount: 0,
  overdueCount: 0,
  upcomingSevenDaysCount: 0,
  highPriorityOpenCount: 0,
  statusCounts: {},
})
const apiOnline = ref(false)
const loading = ref(false)

const todayTasks = computed(() => summary.value.todayTasks.slice(0, 5))
const highPriorityTasks = computed(() => summary.value.highPriorityTasks.slice(0, 5))
const recentRecords = computed(() => summary.value.recentRecords.slice(0, 5))

function formatCurrency(value: string | number) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
  }).format(Number(value))
}

function go(url: string) {
  uni.navigateTo({ url })
}

function logout() {
  clearToken()
  uni.reLaunch({ url: '/pages/login/index' })
}

async function completeTask(task: TaskItem) {
  try {
    await updateTaskStatus(task.id, 'done')
    await loadToday()
    uni.showToast({ title: '已完成', icon: 'success' })
  } catch {
    uni.showToast({ title: '更新失败', icon: 'none' })
  }
}

async function loadToday() {
  loading.value = true
  try {
    const [nextSummary, nextFinanceSummary, nextTaskSummary] = await Promise.all([
      fetchDashboardSummary(),
      fetchFinanceMonthlySummary(),
      fetchTaskSummary(),
    ])
    summary.value = nextSummary
    financeSummary.value = nextFinanceSummary
    taskSummary.value = nextTaskSummary
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

onMounted(loadToday)
</script>

<template>
  <view class="screen">
    <view class="brand-row">
      <view class="brand-mark">M</view>
      <view>
        <view class="title">今日</view>
        <text class="muted">{{ apiOnline ? 'API 已连接' : '后端未连接，显示占位数据' }}</text>
      </view>
    </view>

    <view class="metric-grid">
      <view class="metric-card">
        <text class="muted">未完成</text>
        <text class="value">{{ taskSummary.openCount }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">今日关注</text>
        <text class="value">{{ taskSummary.todayCount }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">未来 7 天</text>
        <text class="value">{{ taskSummary.upcomingSevenDaysCount }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">高优先级</text>
        <text class="value">{{ taskSummary.highPriorityOpenCount }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">本月支出</text>
        <text class="value">{{ formatCurrency(financeSummary.expense || summary.monthlyExpense) }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">本月结余</text>
        <text class="value">{{ formatCurrency(financeSummary.balance || summary.monthlyBalance) }}</text>
      </view>
    </view>

    <view class="quick-grid">
      <view class="quick-card" @click="go('/pages/record/index')">
        <text>快速记录</text>
        <text class="muted">生活、学习、工作随手记</text>
      </view>
      <view class="quick-card" @click="go('/pages/task/index')">
        <text>快速任务</text>
        <text class="muted">下一步行动马上安排</text>
      </view>
      <view class="quick-card" @click="go('/pages/finance/index')">
        <text>快速记账</text>
        <text class="muted">收入支出马上录入</text>
      </view>
    </view>

    <view class="section">
      <view class="section-title">今日待办</view>
      <view v-if="todayTasks.length === 0" class="empty">暂无今日任务</view>
      <template v-else>
        <view v-for="task in todayTasks" :key="task.id" class="list-card">
          <view>
            <text class="list-title">{{ task.title }}</text>
            <text class="muted">{{ task.moduleCode }} · {{ task.priority }} · {{ task.dueDate || '无截止日期' }}</text>
          </view>
          <button class="mini-button" @click="completeTask(task)">完成</button>
        </view>
      </template>
    </view>

    <view class="section">
      <view class="section-title">高优先级</view>
      <view v-if="highPriorityTasks.length === 0" class="empty">暂无高优先级任务</view>
      <template v-else>
        <view v-for="task in highPriorityTasks" :key="task.id" class="list-card">
          <view>
            <text class="list-title">{{ task.title }}</text>
            <text class="muted">{{ task.moduleCode }} · {{ task.status }} · {{ task.dueDate || '无截止日期' }}</text>
          </view>
          <button v-if="task.status !== 'done'" class="mini-button" @click="completeTask(task)">完成</button>
        </view>
      </template>
    </view>

    <view class="section">
      <view class="section-title">最近记录</view>
      <view v-if="recentRecords.length === 0" class="empty">暂无记录</view>
      <template v-else>
        <view v-for="record in recentRecords" :key="record.id" class="list-card">
          <view>
            <text class="list-title">{{ record.title }}</text>
            <text class="muted">{{ record.moduleCode }} · {{ record.recordDate }}</text>
          </view>
        </view>
      </template>
    </view>

    <button class="button-secondary logout-button" :loading="loading" @click="logout">退出登录</button>
  </view>
</template>
