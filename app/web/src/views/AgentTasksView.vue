<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  getAgentCapabilities, listAgentTasks, createAgentTask, approveAgentTask, cancelAgentTask,
  type AgentTask, type AgentTaskType, type AgentCapabilities,
} from '@/api/agentTasks'
const capability = ref<AgentCapabilities | null>(null)
const tasks = ref<AgentTask[]>([])
const taskType = ref<AgentTaskType>('PLAN')
const prompt = ref('')
const busy = ref(false)
const loading = ref(true)
const statusNames: Record<string,string> = {
  PENDING_APPROVAL:'待审批', RUNNING:'处理中', COMPLETED:'已完成', FAILED:'执行失败', CANCELLED:'已取消',
}
const typeNames: Record<AgentTaskType,string> = { PLAN:'方案规划', SUMMARIZE:'内容总结', ANALYZE:'问题分析' }
async function refresh() {
  try {
    const [cap, list] = await Promise.all([getAgentCapabilities(), listAgentTasks()])
    capability.value = cap
    tasks.value = list
  } catch { ElMessage.error('无法读取 Agent 工作台，请确认已登录管理员账号及数据库 V10 已迁移') }
  finally { loading.value = false }
}
async function create() {
  if (!prompt.value.trim()) return
  busy.value = true
  try {
    await createAgentTask(taskType.value, prompt.value.trim())
    prompt.value = ''
    ElMessage.success('已创建待审批任务，不会自动提交到 OpenClaw')
    await refresh()
  } catch { ElMessage.error('创建失败，请检查任务内容') }
  finally { busy.value = false }
}
async function approve(task: AgentTask) {
  if (!capability.value?.openclawEnabled) return
  try {
    await ElMessageBox.confirm(
      '这会将任务内容发送给管理员配置的 OpenClaw 隔离 Agent。确认本次任务仅允许文本规划，不执行服务器命令？',
      '批准 Agent 任务', { type: 'warning', confirmButtonText: '明确批准并提交' })
  } catch { return }
  busy.value = true
  try {
    await approveAgentTask(task.id)
    ElMessage.success('已批准，任务开始处理。可点击刷新查看结果')
    await refresh()
  } catch { ElMessage.error('批准失败：可能尚未启用隔离 Gateway 或任务已处理') }
  finally { busy.value = false }
}
async function cancel(task: AgentTask) {
  busy.value = true
  try {
    await cancelAgentTask(task.id)
    await refresh()
  } catch { ElMessage.error('取消失败，仅待审批任务可取消') }
  finally { busy.value = false }
}
onMounted(refresh)
</script>
<template>
  <AppLayout>
    <div class="agent-workspace">
      <RouterLink to="/me" class="agent-back">‹ 返回我的</RouterLink>
      <header class="page-header">
        <div><p class="eyebrow">MATRIX AI / AGENT</p><h1>OpenClaw 任务工作台</h1>
          <p>管理员专属。创建草稿、逐项审批、查看 Agent 的文本结果与审计记录。</p></div>
        <el-button @click="refresh" :loading="loading">刷新状态</el-button>
      </header>
      <el-alert :type="capability?.openclawEnabled ? 'success' : 'warning'"
        :closable="false" show-icon
        :title="capability?.openclawEnabled ? '隔离 Gateway 配置已启用（不代表已通过网络健康检查）' : '隔离 Gateway 尚未启用；可以创建任务草稿，但无法批准执行'" />
      <p class="agent-note">OpenClaw 使用独立受限 Agent，Codex 仍关闭。本页面只允许规划、总结与分析，不提供 Shell、文件修改或部署操作。</p>
      <el-card shadow="never" class="agent-panel">
        <template #header><strong>新建待审批任务</strong></template>
        <el-form label-position="top" @submit.prevent="create">
          <el-form-item label="任务类型">
            <el-select v-model="taskType" style="width:100%">
              <el-option v-for="(label,key) in typeNames" :key="key" :value="key" :label="label" />
            </el-select>
          </el-form-item>
          <el-form-item label="任务描述">
            <el-input v-model="prompt" type="textarea" :rows="4" :maxlength="2000"
              show-word-limit placeholder="描述需要规划或分析的问题；不要粘贴生产密钥或敏感数据"/>
          </el-form-item>
          <el-button type="primary" native-type="submit" :disabled="!prompt.trim() || busy" :loading="busy">
            创建草稿（不执行）
          </el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="agent-panel">
        <template #header><strong>任务记录</strong></template>
        <el-empty v-if="!tasks.length" description="暂无 Agent 任务"/>
        <div v-for="task in tasks" :key="task.id" class="agent-task">
          <div class="agent-row">
            <strong>{{ typeNames[task.taskType] }} · {{ statusNames[task.status] || task.status }}</strong>
            <span class="agent-date">{{ task.createdAt }}</span>
          </div>
          <p class="agent-prompt">{{ task.prompt }}</p>
          <div class="agent-actions" v-if="task.status === 'PENDING_APPROVAL'">
            <el-button size="small" type="primary" :disabled="busy || !capability?.openclawEnabled" @click="approve(task)">审核并提交</el-button>
            <el-button size="small" :disabled="busy" @click="cancel(task)">取消任务</el-button>
          </div>
          <p v-if="task.status==='RUNNING'" class="agent-note">处理中。请刷新查看任务结果。</p>
          <p v-if="task.status==='FAILED'" class="agent-note">调用失败（{{ task.errorCode }}），系统不会自动重试，避免重复执行。</p>
          <div v-if="task.result" class="agent-result">{{ task.result }}</div>
          <small v-if="task.approvedAt">审批时间：{{ task.approvedAt }} · 审批人 ID：{{ task.approvedBy }}</small>
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>
<style scoped>
.agent-workspace{max-width:980px;margin:0 auto}.agent-back{display:inline-block;margin-bottom:18px;color:#306cd1;text-decoration:none}
.agent-note{font-size:13px;color:#667891;line-height:1.7}.agent-panel{margin:18px 0}
.agent-task{padding:18px 0;border-bottom:1px solid #e6edf6}.agent-task:last-child{border-bottom:0}
.agent-row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.agent-date,.agent-task small{color:#8390a6;font-size:12px}
.agent-prompt{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}
.agent-actions{display:flex;gap:8px}.agent-result{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f8fd;border-radius:12px;padding:16px;line-height:1.7;margin:12px 0}
</style>
