<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  getCodexCapabilities,listCodexJobs,getCodexJob,createCodexJob,approveCodexJob,cancelCodexJob,
  type CodexCapabilities,type CodexDetail,type CodexJob,type CodexTaskType,
} from '@/api/codexJobs'

const capability = ref<CodexCapabilities | null>(null)
const jobs=ref<CodexJob[]>([])
const selected=ref<CodexDetail | null>(null)
const taskType=ref<CodexTaskType>('FIX')
const prompt=ref('')
const busy=ref(false)
const loading=ref(true)
const types:Record<CodexTaskType,string>={IMPLEMENT:'实现功能',FIX:'修复缺陷',TESTS:'完善测试'}
const labels:Record<string,string>={
  PENDING_APPROVAL:'待审批',DISPATCHING:'派发中',DISPATCHED:'已派发',
  FAILED:'派发状态不确定',CANCELLED:'已取消',
}
async function refresh() {
  loading.value=true
  try {
    const [cap,list]=await Promise.all([getCodexCapabilities(),listCodexJobs()])
    capability.value=cap;jobs.value=list
    if(selected.value) selected.value=await getCodexJob(selected.value.job.id)
  } catch {ElMessage.error('无法获取 Codex 任务，请检查管理员权限与数据库 V11 迁移')}
  finally {loading.value=false}
}
async function inspect(job:CodexJob) {
  busy.value=true
  try {selected.value=await getCodexJob(job.id)}
  catch {ElMessage.error('任务状态读取失败')}
  finally {busy.value=false}
}
async function create() {
  if(!prompt.value.trim()) return
  busy.value=true
  try {
    await createCodexJob(taskType.value,prompt.value.trim())
    prompt.value=''
    ElMessage.success('已建立待审核任务，不会自动调用 Codex')
    await refresh()
  } catch {ElMessage.error('创建失败，请检查任务内容')}
  finally {busy.value=false}
}
async function approve(job:CodexJob) {
  if(!capability.value?.enabled) return
  try {
    await ElMessageBox.confirm(
      '你将派发一个可能产生模型费用的开发任务到 GitHub 托管 Runner。工作流仅允许修改指定源码目录，执行测试后创建待审核 PR；不会自动合并或部署。请确认任务中没有密钥或个人敏感信息。',
      '审批并派发 Codex 任务',{type:'warning',confirmButtonText:'确认派发',cancelButtonText:'取消'})
  } catch {return}
  busy.value=true
  try {
    await approveCodexJob(job.id)
    ElMessage.success('审批已接受。可刷新查看 GitHub Actions 执行状态')
    await refresh()
  } catch {ElMessage.error('审批失败：可能未启用 Worker 或任务已被处理')}
  finally {busy.value=false}
}
async function cancel(job:CodexJob) {
  busy.value=true
  try {await cancelCodexJob(job.id);await refresh()}
  catch {ElMessage.error('仅待审批任务可以取消')}
  finally {busy.value=false}
}
onMounted(refresh)
</script>
<template>
  <AppLayout>
    <div class="codex-workspace">
      <RouterLink to="/me" class="codex-back">‹ 返回我的</RouterLink>
      <header class="page-header">
        <div><p class="eyebrow">MATRIX AI / CODEX</p><h1>Codex 开发任务</h1>
          <p>管理员审核后派发到隔离 GitHub Runner。只提交 PR，不自动合并或部署生产环境。</p>
        </div>
        <el-button :loading="loading" @click="refresh">刷新</el-button>
      </header>
      <el-alert :closable="false" show-icon :type="capability?.enabled ? 'success' : 'warning'"
        :title="capability?.enabled ? '后台已允许派发（不代表 GitHub 凭据和模型额度验收完成）' : 'Codex Worker 尚未启用：可以创建草稿，但不能派发执行'" />
      <p class="codex-note">目标仓库：{{ capability?.repository || 'micor-cjj-spec/matrix-prp' }}。开发任务可能产生模型与 GitHub Actions 用量费用。</p>
      <el-card shadow="never" class="codex-panel">
        <template #header><strong>创建开发任务草稿</strong></template>
        <el-form label-position="top" @submit.prevent="create">
          <el-form-item label="开发类型">
            <el-select v-model="taskType" style="width:100%">
              <el-option v-for="(label,id) in types" :key="id" :label="label" :value="id" />
            </el-select>
          </el-form-item>
          <el-form-item label="任务说明">
            <el-input v-model="prompt" type="textarea" :rows="5" maxlength="1500" show-word-limit
              placeholder="描述要修改的功能、预期行为和验收条件。不要填写服务器密码、API Key 等敏感信息。" />
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="busy" :disabled="busy || !prompt.trim()">
            保存草稿（不会运行）
          </el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="codex-panel">
        <template #header><strong>开发任务与审核记录</strong></template>
        <el-empty v-if="!jobs.length" description="暂无开发任务" />
        <div v-for="job in jobs" :key="job.id" class="codex-item">
          <div class="codex-row"><strong>{{ types[job.taskType] }} · {{ labels[job.status] ?? job.status }}</strong>
            <small>{{ job.createdAt }}</small></div>
          <p class="codex-prompt">{{ job.prompt }}</p>
          <div class="codex-actions">
            <el-button size="small" @click="inspect(job)">查看执行状态</el-button>
            <el-button v-if="job.status==='PENDING_APPROVAL'" type="primary" size="small"
              :loading="busy" :disabled="busy || !capability?.enabled" @click="approve(job)">审核并派发</el-button>
            <el-button v-if="job.status==='PENDING_APPROVAL'" size="small" :disabled="busy"
              @click="cancel(job)">取消草稿</el-button>
          </div>
          <p v-if="job.status==='FAILED'" class="codex-note">
            派发请求结果无法确认（{{ job.errorCode }}）；系统不会自动再次派发，请先去 GitHub Actions 核对。
          </p>
        </div>
      </el-card>
      <el-dialog :model-value="selected !== null" @close="selected=null" title="Codex 执行详情" width="min(650px, 95vw)">
        <template v-if="selected">
          <p><strong>任务：</strong>{{ selected.job.id }}</p>
          <p><strong>审批状态：</strong>{{ labels[selected.job.status] ?? selected.job.status }}</p>
          <p v-if="selected.execution"><strong>GitHub 运行状态：</strong>
            {{ selected.execution.status }} · {{ selected.execution.conclusion || '尚未结束' }}</p>
          <p v-else class="codex-note">尚未查询到匹配的 GitHub Actions 运行记录；派发后可能短暂延迟。</p>
          <p v-if="selected.execution?.url"><a :href="selected.execution.url" target="_blank" rel="noopener noreferrer">打开 GitHub Actions 日志</a></p>
          <p v-if="selected.execution?.pullRequestUrl"><a :href="selected.execution.pullRequestUrl"
            target="_blank" rel="noopener noreferrer">打开 Codex 创建的 PR（需人工审核）</a></p>
          <p class="codex-note">如果测试失败或生成的补丁不符合安全路径规则，工作流不会创建 PR。</p>
          <template #footer><el-button @click="selected=null">关闭</el-button>
            <el-button type="primary" @click="refresh">刷新状态</el-button></template>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>
<style scoped>
.codex-workspace{max-width:980px;margin:auto}.codex-back{display:inline-block;margin-bottom:16px;color:#306cd1;text-decoration:none}
.codex-panel{margin:18px 0}.codex-note,.codex-item small{color:#677a96;font-size:12px;line-height:1.75}
.codex-item{border-bottom:1px solid #e6edf6;padding:16px 0}.codex-item:last-child{border-bottom:0}
.codex-row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.codex-prompt{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}.codex-actions{display:flex;gap:8px;flex-wrap:wrap}.codex-actions .el-button{margin-left:0}
</style>
