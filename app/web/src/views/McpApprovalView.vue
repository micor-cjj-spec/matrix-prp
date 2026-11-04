<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { approveMcpDraft, readMcpDraft, rejectMcpDraft, type McpDraftReview } from '@/api/mcpApproval'

const route = useRoute()
const draftId = computed(() => String(route.params.draftId ?? ''))
const draft = ref<McpDraftReview | null>(null)
const password = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const kindText: Record<string, string> = { TASK: '新建任务', TASK_UPDATE: '修改任务', TASK_DELETE: '删除任务', FINANCE: '新增财务流水', RECORD: '新建个人记录' }
const statusText: Record<string, string> = { PENDING: '待本人确认', APPROVED: '本人已批准，等待 MCP 客户端保存', CONSUMED: '已保存', REJECTED: '已拒绝' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    draft.value = await readMcpDraft(draftId.value)
  } catch {
    draft.value = null
    error.value = '草稿不存在、无权访问，或 MCP 尚未启用。'
  } finally { loading.value = false }
}

async function approve() {
  if (!draft.value || draft.value.status !== 'PENDING' || !password.value) return
  busy.value = true
  try {
    const result = await approveMcpDraft(draftId.value, password.value)
    password.value = ''
    if (result.status === 'APPROVED') {
      ElMessage.success('已由 PRP 验证本人身份并批准。返回聊天要求 MCP 客户端完成保存。')
      await load()
    } else {
      ElMessage.error(result.status === 'LOCKED'
        ? '密码验证次数已用尽，草稿已锁定；请重新创建草稿。'
        : `密码错误，剩余 ${result.remainingAttempts} 次尝试机会。`)
      await load()
    }
  } catch { password.value = ''; ElMessage.error('审批失败：请检查账号、草稿状态或网络。'); await load() }
  finally { busy.value = false }
}

async function reject() {
  if (!draft.value || !['PENDING', 'APPROVED'].includes(draft.value.status)) return
  try {
    await ElMessageBox.confirm('拒绝后本草稿不能再入库，是否确认？', '拒绝 MCP 写入', { type: 'warning' })
  } catch { return }
  busy.value = true
  try { await rejectMcpDraft(draftId.value); ElMessage.success('已拒绝本次写入'); await load() }
  catch { ElMessage.error('拒绝失败，请重新加载页面') }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <AppLayout>
    <div class="mcp-review">
      <RouterLink to="/me" class="back-link">‹ 返回我的</RouterLink>
      <header class="page-header">
        <div>
          <p class="eyebrow">MATRIX PRP / MCP</p>
          <h1>确认 AI 数据写入</h1>
          <p>请在 PRP 核对具体数据并验证账号密码。不要把密码发送给 ChatGPT 或其他 MCP 客户端。</p>
        </div>
      </header>
      <el-alert type="warning" :closable="false" show-icon
        title="批准只授权下方这一个草稿；不会允许 AI 操作其他记录。" />
      <el-skeleton v-if="loading" :rows="5" animated style="margin-top:18px" />
      <el-alert v-else-if="error" type="error" :closable="false" :title="error" style="margin-top:18px" />
      <el-card v-else-if="draft" class="review-card" shadow="never">
        <template #header>
          <strong>{{ kindText[draft.kind] ?? draft.kind }}</strong>
          <span class="review-status">{{ statusText[draft.status] ?? draft.status }}</span>
        </template>
        <p class="review-sub">草稿 ID：{{ draft.draftId }}</p>
        <p class="review-sub">截至 {{ draft.expiresAt }} 前必须批准并保存，逾期无效。</p>
        <pre class="review-json">{{ JSON.stringify(draft.values, null, 2) }}</pre>
        <template v-if="draft.status === 'PENDING'">
          <el-form @submit.prevent="approve">
            <el-form-item label="再次输入 PRP 登录密码，证明是本人批准">
              <el-input v-model="password" type="password" autocomplete="current-password"
                show-password maxlength="256" placeholder="仅在 PRP 网站输入，不会发送给 AI 客户端" />
            </el-form-item>
            <div class="review-actions">
              <el-button type="primary" native-type="submit" :loading="busy"
                :disabled="!password || busy">本人确认授权本条写入</el-button>
              <el-button type="danger" plain :disabled="busy" @click="reject">拒绝写入</el-button>
            </div>
          </el-form>
        </template>
        <template v-else-if="draft.status === 'APPROVED'">
          <p class="review-success">本次草稿已授权，返回 ChatGPT 对话并要求执行“确认入库”即可。未完成之前不会自动保存业务数据。</p>
          <el-button type="danger" plain :loading="busy" @click="reject">撤销本次授权</el-button>
        </template>
        <p v-else class="review-sub">这份草稿无法再次批准或执行。需要修改请在聊天中重新创建。</p>
      </el-card>
    </div>
  </AppLayout>
</template>

<style scoped>
.mcp-review { max-width: 850px; margin: 0 auto; padding-bottom: 28px; }
.back-link { display: inline-block; margin-bottom: 16px; color: var(--el-color-primary); text-decoration: none; }
.review-card { margin-top: 22px; }
.review-status { float: right; font-size: 12px; color: var(--el-color-info); }
.review-sub { color: var(--el-text-color-secondary); font-size: 12px; overflow-wrap: anywhere; }
.review-json { max-height: 50vh; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere;
  background: var(--el-fill-color-light); border-radius: 10px; padding: 18px; line-height: 1.65; font-size: 13px; }
.review-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.review-success { color: var(--el-color-success); line-height: 1.7; }
</style>
