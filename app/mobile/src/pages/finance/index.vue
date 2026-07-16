<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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
  { label: 'Expense', value: 'expense' },
  { label: 'Income', value: 'income' },
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
const accountLabels = computed(() => accounts.value.map((item) => `${item.name} (${item.type})`))
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
    uni.showToast({ title: 'Amount required', icon: 'none' })
    return
  }
  if (!form.category.trim() || !form.account.trim()) {
    uni.showToast({ title: 'Category and account required', icon: 'none' })
    return
  }

  loading.value = true
  try {
    await createFinanceTransaction({ ...form })
    form.amount = ''
    form.merchant = ''
    form.note = ''
    await loadFinanceSummary()
    uni.showToast({ title: 'Saved', icon: 'success' })
  } catch {
    uni.showToast({ title: 'Save failed', icon: 'none' })
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
        <view class="title">Quick Finance</view>
        <text class="muted">Capture income or expense quickly, with configured accounts and categories.</text>
      </view>
    </view>

    <view class="metric-grid">
      <view class="metric-card">
        <text class="muted">Income</text>
        <text class="value">{{ formatCurrency(monthlySummary.income) }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">Expense</text>
        <text class="value">{{ formatCurrency(monthlySummary.expense) }}</text>
      </view>
      <view class="metric-card">
        <text class="muted">Balance</text>
        <text class="value">{{ formatCurrency(monthlySummary.balance) }}</text>
      </view>
    </view>

    <view class="panel stack">
      <picker class="select" :value="typeIndex" :range="typeLabels" @change="changeType">
        <view>{{ selectedTypeLabel }}</view>
      </picker>
      <input v-model="form.amount" class="input" type="digit" placeholder="Amount" />

      <picker v-if="hasCategories" class="select" :value="categoryIndex" :range="categoryLabels" @change="changeCategory">
        <view>{{ form.category }}</view>
      </picker>
      <input v-model="form.category" class="input" placeholder="Category" />

      <picker v-if="hasAccounts" class="select" :value="accountIndex" :range="accountLabels" @change="changeAccount">
        <view>{{ form.account }}</view>
      </picker>
      <input v-model="form.account" class="input" placeholder="Account" />

      <input v-model="form.merchant" class="input" placeholder="Merchant" />
      <input v-model="form.transactionDate" class="input" placeholder="YYYY-MM-DD" />
      <textarea v-model="form.note" class="textarea" placeholder="Note" />
      <button class="button-primary" :loading="loading" @click="submit">Save Transaction</button>
      <button class="button-secondary" @click="goHome">Back Today</button>
    </view>

    <view class="section">
      <view class="section-title">This Month By Account</view>
      <view v-if="accountSummary.length === 0" class="empty">No account activity</view>
      <template v-else>
        <view v-for="item in accountSummary" :key="item.account" class="list-card">
          <view>
            <text class="list-title">{{ item.account }}</text>
            <text class="muted">Income {{ formatCurrency(item.income) }} / Expense {{ formatCurrency(item.expense) }}</text>
          </view>
          <text class="list-title">{{ formatCurrency(item.balance) }}</text>
        </view>
      </template>
    </view>
  </view>
</template>
