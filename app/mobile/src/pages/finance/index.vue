<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { accountTypeLabel } from '@/utils/labels'
import {
  createFinanceTransaction,
  fetchFinanceAccounts,
  fetchFinanceAccountSummary,
  fetchFinanceCategories,
  fetchFinanceMonthlySummary,
  type FinanceAccountItem,
  type FinanceAccountSummary,
  type FinanceCategoryItem,
  type FinanceMonthlySummary,
} from '@/api/finance'

const loading = ref(false)
const monthlySummary = ref<FinanceMonthlySummary>({ income: '0', expense: '0', balance: '0' })
const accountSummary = ref<FinanceAccountSummary[]>([])
const accounts = ref<FinanceAccountItem[]>([])
const categories = ref<FinanceCategoryItem[]>([])

const currentMonth = new Date().toISOString().slice(0, 7)
const today = new Date().toISOString().slice(0, 10)

const typeOptions = [
  { label: '支出', value: 'expense' },
  { label: '收入', value: 'income' },
]

const typeIndex = ref(0)
const accountIndex = ref(0)
const categoryIndex = ref(0)

const form = reactive({
  type: 'expense',
  amount: '',
  category: 'daily',
  account: 'default',
  merchant: '',
  note: '',
  transactionDate: today,
})

const typeLabels = computed(() => typeOptions.map((item) => item.label))
const selectedTypeLabel = computed(() => typeOptions[typeIndex.value]?.label ?? form.type)
const accountLabels = computed(() => accounts.value.map((item) => `${item.name} (${accountTypeLabel(item.type)})`))
const categoryLabels = computed(() => categories.value.map((item) => item.name))
const hasAccounts = computed(() => accounts.value.length > 0)
const hasCategories = computed(() => categories.value.length > 0)

function formatCurrency(value: string | number) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
  }).format(Number(value))
}

function changeType(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  typeIndex.value = nextIndex
  form.type = typeOptions[nextIndex]?.value ?? form.type
  void loadFinanceConfig()
}

function changeAccount(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  accountIndex.value = nextIndex
  form.account = accounts.value[nextIndex]?.name ?? form.account
}

function changeCategory(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  categoryIndex.value = nextIndex
  form.category = categories.value[nextIndex]?.name ?? form.category
}

function goHome() {
  uni.reLaunch({ url: '/pages/home/index' })
}

async function loadFinanceSummary() {
  try {
    const [nextMonthlySummary, nextAccountSummary] = await Promise.all([
      fetchFinanceMonthlySummary(currentMonth),
      fetchFinanceAccountSummary(currentMonth),
    ])
    monthlySummary.value = nextMonthlySummary
    accountSummary.value = nextAccountSummary
  } catch {
    monthlySummary.value = { income: '0', expense: '0', balance: '0' }
    accountSummary.value = []
  }
}

async function loadFinanceConfig() {
  try {
    const [nextAccounts, nextCategories] = await Promise.all([
      fetchFinanceAccounts(),
      fetchFinanceCategories(form.type),
    ])
    accounts.value = nextAccounts
    categories.value = nextCategories

    if (nextAccounts.length > 0 && !nextAccounts.some((item) => item.name === form.account)) {
      accountIndex.value = 0
      form.account = nextAccounts[0].name
    }
    if (nextCategories.length > 0 && !nextCategories.some((item) => item.name === form.category)) {
      categoryIndex.value = 0
      form.category = nextCategories[0].name
    }
  } catch {
    accounts.value = []
    categories.value = []
  }
}

async function submit() {
  if (!form.amount.trim()) {
    uni.showToast({ title: '请输入金额', icon: 'none' })
    return
  }
  if (!form.category.trim() || !form.account.trim()) {
    uni.showToast({ title: '请填写分类和账户', icon: 'none' })
    return
  }

  loading.value = true
  try {
    await createFinanceTransaction({ ...form })
    form.amount = ''
    form.merchant = ''
    form.note = ''
    await loadFinanceSummary()
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch {
    uni.showToast({ title: '保存失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadFinanceSummary(), loadFinanceConfig()])
})
</script>

<template>
  <view class="screen">
    <view class="brand-row">
      <view>
        <view class="title">快速记账</view>
        <text class="muted">快速记录收入和支出，使用已配置的账户与分类。</text>
      </view>
    </view>

    <view class="metric-grid">
      <view class="metric-card">
        <text class="muted">本月收入</text>
        <text class="value">{{ formatCurrency(monthlySummary.income) }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">本月支出</text>
        <text class="value">{{ formatCurrency(monthlySummary.expense) }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">本月结余</text>
        <text class="value">{{ formatCurrency(monthlySummary.balance) }}</text>
      </view>
    </view>

    <view class="panel stack">
      <picker class="select" :value="typeIndex" :range="typeLabels" @change="changeType">
        <view>{{ selectedTypeLabel }}</view>
      </picker>
      <input v-model="form.amount" class="input" type="digit" placeholder="金额" />

      <picker v-if="hasCategories" class="select" :value="categoryIndex" :range="categoryLabels" @change="changeCategory">
        <view>{{ form.category }}</view>
      </picker>
      <input v-model="form.category" class="input" placeholder="分类" />

      <picker v-if="hasAccounts" class="select" :value="accountIndex" :range="accountLabels" @change="changeAccount">
        <view>{{ form.account }}</view>
      </picker>
      <input v-model="form.account" class="input" placeholder="账户" />

      <input v-model="form.merchant" class="input" placeholder="商家 / 对方" />
      <input v-model="form.transactionDate" class="input" placeholder="YYYY-MM-DD" />
      <textarea v-model="form.note" class="textarea" placeholder="备注" />
      <button class="button-primary" :loading="loading" @click="submit">保存收支记录</button>
      <button class="button-secondary" @click="goHome">返回今日</button>
    </view>

    <view class="section">
      <view class="section-title">本月账户收支</view>
      <view v-if="accountSummary.length === 0" class="empty">暂无账户变动</view>
      <template v-else>
        <view v-for="item in accountSummary" :key="item.account" class="list-card">
          <view>
            <text class="list-title">{{ item.account }}</text>
            <text class="muted">收入 {{ formatCurrency(item.income) }} / 支出 {{ formatCurrency(item.expense) }}</text>
          </view>
          <text class="list-title">{{ formatCurrency(item.balance) }}</text>
        </view>
      </template>
    </view>
  </view>
</template>
