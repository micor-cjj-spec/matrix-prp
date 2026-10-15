<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FinanceAccountItem } from '@/api/finance'
import {
  previewWeChatBill, getFinanceImport, listFinanceImports, commitFinanceImport,
  type FinanceImportBatch, type FinanceImportHistory,
} from '@/api/financeImport'

const props = defineProps<{ accounts: FinanceAccountItem[] }>()
const emit = defineEmits<{ (e: 'imported'): void }>()
const file = ref<File | null>(null)
const sourceAccount = ref('')
const batch = ref<FinanceImportBatch | null>(null)
const history = ref<FinanceImportHistory[]>([])
const uploading = ref(false)
const committing = ref(false)
const loadingHistory = ref(false)
const mappings = reactive<Record<string, number | undefined>>({})
const paymentMethods = computed(() =>
  [...new Set(batch.value?.rows.filter(r => r.rowStatus === 'READY').map(r => r.paymentMethod) ?? [])],
)
const missingMappings = computed(() => paymentMethods.value.filter(method => !mappings[method]))
const money = (v: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(v)
const rowStatusText: Record<string,string> = {
  READY: '可入账', REVIEW: '待人工复核', DUPLICATE: '已去重', POSTED: '已入账',
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.item(0) ?? null
}
async function reloadHistory() {
  loadingHistory.value = true
  try { history.value = await listFinanceImports() }
  catch { ElMessage.warning('导入历史暂时无法读取') }
  finally { loadingHistory.value = false }
}
async function uploadPreview() {
  if (!file.value) return ElMessage.warning('请先选择微信支付 XLSX 账单')
  if (file.value.size > 5 * 1024 * 1024) return ElMessage.error('文件不能超过 5MB')
  uploading.value = true
  try {
    batch.value = await previewWeChatBill(file.value, sourceAccount.value)
    for (const key of Object.keys(mappings)) delete mappings[key]
    const candidates = props.accounts.filter(a => a.currency === 'CNY')
    for (const method of paymentMethods.value) {
      const exact = candidates.find(a => a.name === method || a.name === '微信' + method || a.name === '微信零钱')
      if (exact && (method === '零钱' || exact.name !== '微信零钱')) mappings[method] = exact.id
    }
    await reloadHistory()
    ElMessage.success('已完成安全解析，尚未计入账户余额')
  } catch {
    ElMessage.error('账单解析失败：请核对文件是否为官方微信支付 XLSX 明细')
  } finally { uploading.value = false }
}
async function openBatch(id: number) {
  try { batch.value = await getFinanceImport(id) }
  catch { ElMessage.error('导入批次读取失败') }
}
async function confirmPost() {
  const b = batch.value
  if (!b || b.ready === 0) return
  if (missingMappings.value.length) {
    return ElMessage.warning('请先为所有可入账交易的支付方式选择真实资金账户')
  }
  try {
    await ElMessageBox.confirm(
      `仅将 ${b.ready} 笔正常消费入账；${b.review} 笔退款、转账或其他不确定交易不入账，${b.duplicate} 笔重复交易跳过。确认吗？`,
      '确认导入微信账单',
      { type: 'warning', confirmButtonText: '确认入账', cancelButtonText: '返回检查' },
    )
  } catch { return }
  committing.value = true
  try {
    const mapped = Object.fromEntries(
      Object.entries(mappings).filter((entry): entry is [string, number] => Number.isInteger(entry[1])),
    )
    batch.value = await commitFinanceImport(b.id, mapped)
    ElMessage.success('导入完成：已入账 ' + batch.value.posted + ' 笔，待复核记录仍保留')
    emit('imported')
    await reloadHistory()
  } catch {
    ElMessage.error('入账失败，未确认数据不会被部分写入，请检查账户或联系管理员')
  } finally { committing.value = false }
}
onMounted(() => { void reloadHistory() })
</script>

<template>
  <el-card shadow="never" class="finance-import">
    <template #header>
      <div class="import-header">
        <strong>账单导入 · 微信支付</strong>
        <el-tag type="info">P0：先预览、后入账</el-tag>
      </div>
    </template>
    <p class="import-hint">上传微信官方导出的 XLSX 明细。账单不会发送给 AI；退款、红包和个人转账需要人工核对，本版不会自动入账。</p>
    <div class="import-picker">
      <label>选择微信账单 <input aria-label="选择微信账单文件" type="file" accept=".xlsx" @change="pickFile" /></label>
      <el-input v-model="sourceAccount" placeholder="微信来源账号标识（可选，默认读取文件昵称）" clearable style="max-width:320px" />
      <el-button type="primary" :loading="uploading" :disabled="!file" @click="uploadPreview">解析并预览</el-button>
    </div>
    <template v-if="batch">
      <el-divider />
      <div class="import-header">
        <strong>{{ batch.filename }}</strong>
        <span class="import-hint">来源账号：{{ batch.sourceAccountKey }} · 当前批次 #{{ batch.id }}</span>
      </div>
      <div class="import-counts">
        <el-tag type="success">可入账 {{ batch.ready }}</el-tag>
        <el-tag type="warning">待复核 {{ batch.review }}</el-tag>
        <el-tag type="info">重复 {{ batch.duplicate }}</el-tag>
        <el-tag>已入账 {{ batch.posted }}</el-tag>
      </div>
      <div v-if="paymentMethods.length" class="account-mapping">
        <strong>支付方式映射：请选择实际扣款的 PRP 账户</strong>
        <div v-for="method in paymentMethods" :key="method" class="account-mapping-row">
          <span>{{ method || '未注明支付方式' }}</span>
          <el-select v-model="mappings[method]" placeholder="选择实际资金账户" style="width:260px">
            <el-option v-for="account in props.accounts.filter(a => a.currency === 'CNY')"
              :key="account.id" :value="account.id" :label="account.name + ' / ' + account.currency" />
          </el-select>
        </div>
        <p class="import-hint">例如微信零钱消费应映射到零钱账户，微信通过银行卡消费应映射到对应银行卡，以防将渠道当作资金账户。</p>
      </div>
      <div class="preview-scroll">
        <el-table :data="batch.rows" size="small" max-height="390" stripe style="min-width:760px">
          <el-table-column prop="transactionAt" label="交易时间" min-width="155" />
          <el-table-column prop="counterparty" label="交易对方" min-width="160" show-overflow-tooltip />
          <el-table-column prop="transactionType" label="类型" width="125" />
          <el-table-column prop="amount" label="金额" width="105">
            <template #default="{ row }">{{ money(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="paymentMethod" label="支付方式" width="140" />
          <el-table-column label="处理结果" width="120">
            <template #default="{ row }">
              <el-tag :type="row.rowStatus === 'POSTED' ? 'success' : row.rowStatus === 'REVIEW' ? 'warning' : 'info'">
                {{ rowStatusText[row.rowStatus] || row.rowStatus }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="import-footer">
        <span class="import-hint">不会覆盖已有流水；同一来源交易单号只允许入账一次。</span>
        <el-button type="primary" :loading="committing" :disabled="batch.ready === 0" @click="confirmPost">
          确认入账正常消费（{{ batch.ready }} 笔）
        </el-button>
      </div>
    </template>
    <el-divider />
    <strong>最近导入历史</strong>
    <el-skeleton :loading="loadingHistory" animated :rows="2">
      <el-empty v-if="history.length === 0" description="暂无导入批次" :image-size="72" />
      <div v-else class="history-list">
        <button v-for="item in history" :key="item.id" type="button" @click="openBatch(item.id)">
          <span>{{ item.filename }} <small>{{ item.sourceAccountKey }}</small></span>
          <el-tag size="small">{{ item.status }}</el-tag>
        </button>
      </div>
    </el-skeleton>
  </el-card>
</template>

<style scoped>
.finance-import { margin-bottom: 16px; }
.import-header,.import-footer { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; }
.import-hint { color:#64748b; font-size:13px; line-height:1.5; }
.import-picker { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:16px 0; }
.import-picker label { display:grid; gap:6px; font-size:13px; }
.import-picker input { max-width:280px; }
.import-counts { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
.account-mapping { display:grid; gap:10px; margin:16px 0; }
.account-mapping-row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
.account-mapping-row span { min-width:130px; }
.preview-scroll { overflow-x:auto; margin:12px 0 18px; }
.history-list { display:grid; gap:6px; margin-top:12px; }
.history-list button { display:flex; align-items:center; justify-content:space-between; gap:12px;
  background:transparent; border:1px solid #e5e7eb; padding:10px; border-radius:8px; text-align:left; cursor:pointer; }
.history-list small { color:#64748b; display:block; }
@media(max-width:640px) { .account-mapping-row { align-items:stretch; flex-direction:column; } }
</style>
