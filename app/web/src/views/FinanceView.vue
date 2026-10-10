<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createFinanceAccount,
  createFinanceCategory,
  createFinanceTransaction,
  deleteFinanceAccount,
  deleteFinanceCategory,
  deleteFinanceTransaction,
  fetchFinanceAccountSummary,
  fetchFinanceAccounts,
  fetchFinanceCategories,
  fetchFinanceCategorySummary,
  fetchFinanceMonthlySummary,
  fetchFinanceTransactions,
  updateFinanceAccount,
  updateFinanceCategory,
  updateFinanceTransaction,
  type FinanceAccountItem,
  type FinanceAccountSummary,
  type FinanceCategoryItem,
  type FinanceCategorySummary,
  type FinanceMonthlySummary,
  type FinanceTransactionItem,
} from '@/api/finance'
import AppLayout from '@/layouts/AppLayout.vue'
import { accountTypeLabel, financeTypeLabel } from '@/utils/labels'

const transactions = ref<FinanceTransactionItem[]>([])
const accounts = ref<FinanceAccountItem[]>([])
const categories = ref<FinanceCategoryItem[]>([])
const categorySummary = ref<FinanceCategorySummary[]>([])
const accountSummary = ref<FinanceAccountSummary[]>([])
const summary = ref<FinanceMonthlySummary>({ income: '0', expense: '0', balance: '0' })
const loading = ref(false)
const apiOnline = ref(false)

const editingTransactionId = ref<number | null>(null)
const editingAccountId = ref<number | null>(null)
const editingCategoryId = ref<number | null>(null)

const currentMonth = new Date().toISOString().slice(0, 7)
const today = new Date().toISOString().slice(0, 10)

const filters = reactive({
  month: currentMonth,
  type: '',
  category: '',
})

const transactionForm = reactive({
  type: 'expense',
  amount: 0,
  category: '',
  account: '',
  merchant: '',
  note: '',
  transactionDate: today,
})

const accountForm = reactive({
  name: '',
  type: 'cash',
  currency: 'CNY',
  openingBalance: 0,
  note: '',
})

const categoryForm = reactive({
  name: '',
  type: 'expense',
  color: '#2563eb',
  note: '',
})

const formatCurrency = (value: string | number, currency = 'CNY') =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency,
  }).format(Number(value))

const formatPercent = (value: string | number) => `${(Number(value) * 100).toFixed(1)}%`

const transactionTypeOptions = [{ label: '支出', value: 'expense' }, { label: '收入', value: 'income' }]
const metrics = computed(() => [
  { label: '收入', value: formatCurrency(summary.value.income) },
  { label: '支出', value: formatCurrency(summary.value.expense) },
  { label: '结余', value: formatCurrency(summary.value.balance) },
])

const accountOptions = computed(() => {
  const configured = accounts.value.map((item) => item.name)
  const used = transactions.value.map((item) => item.account)
  return Array.from(new Set([...configured, ...used].filter(Boolean)))
})

const categoryOptions = computed(() => {
  const configured = categories.value
    .filter((item) => item.type === transactionForm.type)
    .map((item) => item.name)
  const used = transactions.value.map((item) => item.category)
  return Array.from(new Set([...configured, ...used].filter(Boolean)))
})

async function loadFinance() {
  loading.value = true
  try {
    const [
      nextTransactions,
      nextSummary,
      nextCategorySummary,
      nextAccountSummary,
      nextAccounts,
      nextCategories,
    ] = await Promise.all([
      fetchFinanceTransactions({
        month: filters.month || undefined,
        type: filters.type || undefined,
        category: filters.category || undefined,
      }),
      fetchFinanceMonthlySummary(filters.month || undefined),
      fetchFinanceCategorySummary(filters.month || undefined),
      fetchFinanceAccountSummary(filters.month || undefined),
      fetchFinanceAccounts(),
      fetchFinanceCategories(),
    ])
    transactions.value = nextTransactions
    summary.value = nextSummary
    categorySummary.value = nextCategorySummary
    accountSummary.value = nextAccountSummary
    accounts.value = nextAccounts
    categories.value = nextCategories
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

function resetTransactionForm() {
  editingTransactionId.value = null
  transactionForm.type = 'expense'
  transactionForm.amount = 0
  transactionForm.category = ''
  transactionForm.account = accountOptions.value[0] || ''
  transactionForm.merchant = ''
  transactionForm.note = ''
  transactionForm.transactionDate = today
}

async function submitTransaction() {
  if (!transactionForm.amount || !transactionForm.category.trim() || !transactionForm.account.trim()) return
  if (editingTransactionId.value === null) {
    await createFinanceTransaction({ ...transactionForm })
    ElMessage.success('收支记录已创建')
  } else {
    await updateFinanceTransaction(editingTransactionId.value, { ...transactionForm })
    ElMessage.success('收支记录已更新')
  }
  resetTransactionForm()
  await loadFinance()
}

function editTransaction(transaction: FinanceTransactionItem) {
  editingTransactionId.value = transaction.id
  transactionForm.type = transaction.type
  transactionForm.amount = Number(transaction.amount)
  transactionForm.category = transaction.category
  transactionForm.account = transaction.account
  transactionForm.merchant = transaction.merchant
  transactionForm.note = transaction.note
  transactionForm.transactionDate = transaction.transactionDate
}

async function removeTransaction(transaction: FinanceTransactionItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${transaction.category}」这笔 ${formatCurrency(transaction.amount)} 的记录吗？`, '删除收支记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteFinanceTransaction(transaction.id)
  ElMessage.success('收支记录已删除')
  await loadFinance()
}

function resetAccountForm() {
  editingAccountId.value = null
  accountForm.name = ''
  accountForm.type = 'cash'
  accountForm.currency = 'CNY'
  accountForm.openingBalance = 0
  accountForm.note = ''
}

async function submitAccount() {
  if (!accountForm.name.trim()) return
  if (editingAccountId.value === null) {
    await createFinanceAccount({ ...accountForm })
    ElMessage.success('账户已创建')
  } else {
    await updateFinanceAccount(editingAccountId.value, { ...accountForm })
    ElMessage.success('账户已更新')
  }
  resetAccountForm()
  await loadFinance()
}

function editAccount(account: FinanceAccountItem) {
  editingAccountId.value = account.id
  accountForm.name = account.name
  accountForm.type = account.type
  accountForm.currency = account.currency
  accountForm.openingBalance = Number(account.openingBalance)
  accountForm.note = account.note
}

async function removeAccount(account: FinanceAccountItem) {
  try {
    await ElMessageBox.confirm(`确定删除账户「${account.name}」吗？`, '删除账户', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteFinanceAccount(account.id)
  ElMessage.success('账户已删除')
  await loadFinance()
}

function resetCategoryForm() {
  editingCategoryId.value = null
  categoryForm.name = ''
  categoryForm.type = 'expense'
  categoryForm.color = '#2563eb'
  categoryForm.note = ''
}

async function submitCategory() {
  if (!categoryForm.name.trim()) return
  if (editingCategoryId.value === null) {
    await createFinanceCategory({ ...categoryForm })
    ElMessage.success('分类已创建')
  } else {
    await updateFinanceCategory(editingCategoryId.value, { ...categoryForm })
    ElMessage.success('分类已更新')
  }
  resetCategoryForm()
  await loadFinance()
}

function editCategory(category: FinanceCategoryItem) {
  editingCategoryId.value = category.id
  categoryForm.name = category.name
  categoryForm.type = category.type
  categoryForm.color = category.color
  categoryForm.note = category.note
}

async function removeCategory(category: FinanceCategoryItem) {
  try {
    await ElMessageBox.confirm(`确定删除分类「${category.name}」吗？`, '删除分类', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteFinanceCategory(category.id)
  ElMessage.success('分类已删除')
  await loadFinance()
}

onMounted(async () => {
  await loadFinance()
  resetTransactionForm()
})
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">财务管理</p>
        <h1>个人财务工作台</h1>
        <p>管理收支记录、账户与分类，清晰掌握每月资金变化。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? '财务服务已连接' : '财务服务未连接' }}
        </span>
      </div>
    </header>

    <section class="metric-grid">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
      </article>
    </section>

    <section class="finance-grid">
      <el-card shadow="never">
        <template #header>{{ editingTransactionId === null ? '新增收支' : '编辑收支' }}</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="类型">
            <el-segmented v-model="transactionForm.type" :options="transactionTypeOptions" />
          </el-form-item>
          <el-form-item label="金额">
            <el-input-number v-model="transactionForm.amount" :precision="2" :min="0" />
          </el-form-item>
          <el-form-item label="分类">
            <el-select v-model="transactionForm.category" filterable allow-create placeholder="选择或输入新名称">
              <el-option v-for="category in categoryOptions" :key="category" :label="category" :value="category" />
            </el-select>
          </el-form-item>
          <el-form-item label="账户">
            <el-select v-model="transactionForm.account" filterable allow-create placeholder="选择或输入新名称">
              <el-option v-for="account in accountOptions" :key="account" :label="account" :value="account" />
            </el-select>
          </el-form-item>
          <el-form-item label="商家 / 对方">
            <el-input v-model="transactionForm.merchant" />
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="transactionForm.transactionDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="transactionForm.note" type="textarea" :rows="2" />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="loading" @click="submitTransaction">
              {{ editingTransactionId === null ? '创建' : '保存' }}
            </el-button>
            <el-button v-if="editingTransactionId !== null" @click="resetTransactionForm">Cancel</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>{{ editingAccountId === null ? '账户管理' : '编辑账户' }}</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="名称">
            <el-input v-model="accountForm.name" placeholder="例如：现金、银行卡、支付宝" />
          </el-form-item>
          <el-form-item label="类型">
            <el-input v-model="accountForm.type" placeholder="例如：cash、bank、card" />
          </el-form-item>
          <el-form-item label="币种">
            <el-input v-model="accountForm.currency" />
          </el-form-item>
          <el-form-item label="期初余额">
            <el-input-number v-model="accountForm.openingBalance" :precision="2" :min="0" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="accountForm.note" />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" @click="submitAccount">
              {{ editingAccountId === null ? '新增账户' : '保存账户' }}
            </el-button>
            <el-button v-if="editingAccountId !== null" @click="resetAccountForm">Cancel</el-button>
          </div>
        </el-form>

        <div class="compact-list">
          <article v-for="account in accounts" :key="account.id" class="compact-row">
            <div>
              <strong>{{ account.name }}</strong>
              <span>{{ accountTypeLabel(account.type) }} / {{ account.currency }}</span>
            </div>
            <div class="item-actions">
              <el-tag>{{ formatCurrency(account.openingBalance, account.currency) }}</el-tag>
              <el-button size="small" text @click="editAccount(account)">编辑</el-button>
              <el-button size="small" text type="danger" @click="removeAccount(account)">删除</el-button>
            </div>
          </article>
          <el-empty v-if="accounts.length === 0" description="暂无账户" />
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>{{ editingCategoryId === null ? '分类管理' : '编辑分类' }}</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="名称">
            <el-input v-model="categoryForm.name" placeholder="例如：餐饮、工资、交通" />
          </el-form-item>
          <el-form-item label="类型">
            <el-segmented v-model="categoryForm.type" :options="transactionTypeOptions" />
          </el-form-item>
          <el-form-item label="颜色">
            <el-color-picker v-model="categoryForm.color" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="categoryForm.note" />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" @click="submitCategory">
              {{ editingCategoryId === null ? '新增分类' : '保存分类' }}
            </el-button>
            <el-button v-if="editingCategoryId !== null" @click="resetCategoryForm">Cancel</el-button>
          </div>
        </el-form>

        <div class="compact-list">
          <article v-for="category in categories" :key="category.id" class="compact-row">
            <div>
              <strong>{{ category.name }}</strong>
              <span>{{ financeTypeLabel(category.type) }}</span>
            </div>
            <div class="item-actions">
              <span class="swatch" :style="{ backgroundColor: category.color }" />
              <el-button size="small" text @click="editCategory(category)">编辑</el-button>
              <el-button size="small" text type="danger" @click="removeCategory(category)">删除</el-button>
            </div>
          </article>
          <el-empty v-if="categories.length === 0" description="暂无分类" />
        </div>
      </el-card>
    </section>

    <section class="work-grid">
      <el-card shadow="never">
        <template #header>本月支出分类</template>
        <el-empty v-if="categorySummary.length === 0" description="本月暂无支出分类数据" />
        <div v-else class="summary-list">
          <div v-for="item in categorySummary" :key="item.category" class="summary-item">
            <div>
              <strong>{{ item.category }}</strong>
              <span>{{ formatPercent(item.ratio) }}</span>
            </div>
            <el-progress :percentage="Number(item.ratio) * 100" :show-text="false" />
            <p>{{ formatCurrency(item.amount) }}</p>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>账户收支汇总</template>
        <el-empty v-if="accountSummary.length === 0" description="本月暂无账户变动" />
        <div v-else class="item-list">
          <article v-for="item in accountSummary" :key="item.account" class="list-item">
            <div class="list-item-row">
              <strong>{{ item.account }}</strong>
              <el-tag :type="Number(item.balance) >= 0 ? 'success' : 'danger'">
                {{ formatCurrency(item.balance) }}
              </el-tag>
            </div>
            <span>收入 {{ formatCurrency(item.income) }} / 支出 {{ formatCurrency(item.expense) }}</span>
          </article>
        </div>
      </el-card>

      <el-card shadow="never" class="transaction-list-card">
        <template #header>收支明细</template>
        <div class="filter-row">
          <el-date-picker v-model="filters.month" type="month" value-format="YYYY-MM" placeholder="选择月份" @change="loadFinance" />
          <el-select v-model="filters.type" clearable placeholder="收支类型" @change="loadFinance" @clear="loadFinance">
            <el-option label="支出" value="expense" />
            <el-option label="收入" value="income" />
          </el-select>
          <el-select v-model="filters.category" clearable filterable allow-create placeholder="分类" @change="loadFinance" @clear="loadFinance">
            <el-option v-for="category in categoryOptions" :key="category" :label="category" :value="category" />
          </el-select>
        </div>
        <el-empty v-if="transactions.length === 0" description="暂无收支记录" />
        <div v-else class="item-list">
          <article v-for="transaction in transactions" :key="transaction.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ transaction.category }}</strong>
              <div class="item-actions">
                <el-tag :type="transaction.type === 'income' ? 'success' : 'warning'">
                  {{ financeTypeLabel(transaction.type) }}
                </el-tag>
                <el-button size="small" text @click="editTransaction(transaction)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeTransaction(transaction)">删除</el-button>
              </div>
            </div>
            <span>{{ transaction.transactionDate }} / {{ transaction.account }}</span>
            <p>{{ formatCurrency(transaction.amount) }} / {{ transaction.merchant || '未填写商家' }}</p>
          </article>
        </div>
      </el-card>
    </section>
  </AppLayout>
</template>

<style scoped>
.finance-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.work-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.transaction-list-card {
  grid-column: 1 / -1;
}

.form-actions,
.filter-row,
.item-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.compact-list,
.item-list,
.summary-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.compact-row,
.list-item,
.summary-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.compact-row,
.list-item-row,
.summary-item > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.compact-row span,
.list-item span,
.summary-item span,
.summary-item p {
  color: #64748b;
  font-size: 13px;
}

.swatch {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
}

@media (max-width: 980px) {
  .finance-grid,
  .work-grid {
    grid-template-columns: 1fr;
  }
}
</style>
