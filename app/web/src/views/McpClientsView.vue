<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  authorizeMcpClient, listMcpClients, mcpScopes, revokeMcpClient,
  type McpClientGrant,
} from '@/api/mcpClients'
import {
  createMcpIdentityTicket, listMcpIdentityLinks, unlinkMcpIdentity,
  type McpIdentityLink, type McpLinkTicket,
} from '@/api/mcpIdentity'

const clients = ref<McpClientGrant[]>([])
const identities = ref<McpIdentityLink[]>([])
const pairClientId = ref('')
const pairPassword = ref('')
const unlinkPassword = ref('')
const ticket = ref<McpLinkTicket | null>(null)
const pairing = ref(false)
const pairError = ref('')
const clientId = ref('')
const scopes = ref<string[]>(['prp.tasks.read'])
const password = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try { clients.value = await listMcpClients() }
  catch { error.value = '连接管理未启用或暂时不可用。请检查 PRP MCP OAuth 配置。' }
  finally { loading.value = false }
}

async function refreshIdentities() {
  try { identities.value = await listMcpIdentityLinks() }
  catch { identities.value = [] }
}

async function issueTicket() {
  if (!pairClientId.value.trim() || !pairPassword.value) return
  pairing.value = true
  pairError.value = ''
  ticket.value = null
  try {
    ticket.value = await createMcpIdentityTicket(pairClientId.value.trim(), pairPassword.value)
    pairPassword.value = ''
    ElMessage.success('一次性关联码已生成，十分钟内有效')
  } catch {
    pairPassword.value = ''
    pairError.value = '创建关联码失败：请先批准这个客户端，并检查 PRP 密码。'
  } finally { pairing.value = false }
}

async function unlinkIdentity() {
  if (!unlinkPassword.value) return
  try {
    await ElMessageBox.confirm('解除后外部 OAuth 账号将无法访问当前 PRP 用户的数据，确认解除吗？', '解除 OAuth 关联', { type: 'warning' })
  } catch { return }
  pairing.value = true
  try {
    await unlinkMcpIdentity(unlinkPassword.value)
    unlinkPassword.value = ''
    ticket.value = null
    await refreshIdentities()
    ElMessage.success('OAuth 身份关联已解除')
  } catch {
    unlinkPassword.value = ''
    ElMessage.error('解除失败：请核对当前 PRP 账号密码')
  } finally { pairing.value = false }
}

async function approve() {
  if (!clientId.value.trim() || !password.value || scopes.value.length === 0) return
  busy.value = true
  try {
    await authorizeMcpClient(clientId.value.trim(), scopes.value, password.value)
    password.value = ''
    ElMessage.success('已授权客户端指定权限')
    await refresh()
  } catch {
    password.value = ''
    ElMessage.error('授权失败，请核对账号密码、客户端 ID 和权限配置')
  } finally { busy.value = false }
}

async function revoke(client: McpClientGrant) {
  try { await ElMessageBox.confirm(
    '撤销后，此客户端新发起的 MCP 请求将被拒绝。确定撤销吗？',
    '撤销 MCP 客户端授权', { type: 'warning' },
  ) } catch { return }
  busy.value = true
  try { await revokeMcpClient(client.clientId); ElMessage.success('已撤销授权'); await refresh() }
  catch { ElMessage.error('撤销失败，请重试') }
  finally { busy.value = false }
}
onMounted(() => { void refresh(); void refreshIdentities() })
</script>

<template>
  <AppLayout>
    <div class="mcp-clients">
      <RouterLink to="/me" class="back">‹ 返回我的</RouterLink>
      <header class="prp-section-header">
        <div><p class="eyebrow">MATRIX PRP / MCP</p><h1>MCP 客户端授权</h1>
          <p>控制外部 AI 客户端可使用的个人数据权限，授权可随时撤销。</p></div>
      </header>
      <el-alert type="warning" :closable="false" show-icon
        title="仅向已核实身份的 OAuth 客户端授权。此页面不会颁发 OAuth 令牌，也不能替代第三方账号关联。" />
      <el-card shadow="never" class="section">
        <template #header>新增或修改客户端授权</template>
        <el-form label-position="top" @submit.prevent="approve">
          <el-form-item label="OAuth 客户端 ID（从可信授权服务器获得）">
            <el-input v-model="clientId" maxlength="128" placeholder="OAuth client_id" autocomplete="off"/>
          </el-form-item>
          <el-form-item label="允许的权限">
            <el-checkbox-group v-model="scopes">
              <div v-for="scope in mcpScopes" :key="scope.value" class="scope-option">
                <el-checkbox :value="scope.value" :label="scope.label" />
              </div>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="再次输入 PRP 账号密码确认授权">
            <el-input v-model="password" type="password" show-password autocomplete="current-password"
              maxlength="256" placeholder="密码只发送给 PRP，不提供给 AI 客户端" />
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="busy"
            :disabled="!clientId.trim() || !password || scopes.length === 0 || busy">批准此客户端</el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="section">
        <template #header>关联 PRP 与外部 OAuth 账号</template>
        <p>先完成上方客户端授权，然后创建一次性关联码。外部 OAuth 客户端必须使用其已验证的 Bearer Token 调用 PRP 的 <code>POST /api/mcp/link</code> 完成关联。</p>
        <el-form label-position="top" @submit.prevent="issueTicket">
          <el-form-item label="待关联的客户端 ID（必须与上方已批准的客户端一致）">
            <el-input v-model="pairClientId" maxlength="128" autocomplete="off" placeholder="OAuth client_id" />
          </el-form-item>
          <el-form-item label="PRP 登录密码（仅用于生成一次性关联码）">
            <el-input v-model="pairPassword" type="password" autocomplete="current-password"
              maxlength="256" placeholder="PRP 登录密码" />
          </el-form-item>
          <el-button type="primary" :disabled="!pairClientId.trim() || !pairPassword || pairing"
            :loading="pairing" native-type="submit">生成账号关联码</el-button>
        </el-form>
        <el-alert v-if="pairError" type="error" :title="pairError" :closable="false" class="section" />
        <div v-if="ticket" class="pair-ticket">
          <strong>一次性关联码（只显示此次；10 分钟内有效）</strong>
          <p class="ticket-code">{{ ticket.code }}</p>
          <p>客户端：{{ ticket.clientId }}，有效期至 {{ ticket.expiresAt }}</p>
          <p>只在你信任的 OAuth 客户端中完成关联，不要把关联码或登录密码发到普通 AI 对话中。</p>
        </div>
        <div class="identity-list">
          <strong>已验证的外部身份</strong>
          <p v-if="!identities.length">当前尚未关联 OAuth 账号。</p>
          <p v-for="identity in identities" :key="identity.issuer + ':' + identity.subject">
            {{ identity.issuer }} · {{ identity.subject }}
          </p>
          <el-button plain :disabled="pairing" @click="refreshIdentities">刷新关联状态</el-button>
        </div>
        <div v-if="identities.length" class="identity-unlink">
          <el-input v-model="unlinkPassword" type="password" autocomplete="current-password"
            maxlength="256" placeholder="输入 PRP 密码解除关联" />
          <el-button type="danger" plain :disabled="!unlinkPassword || pairing"
            :loading="pairing" @click="unlinkIdentity">解除外部身份关联</el-button>
        </div>
      </el-card>
      <el-card shadow="never" class="section">
        <template #header>已登记的客户端</template>
        <el-skeleton v-if="loading" :rows="3" animated />
        <el-alert v-else-if="error" type="info" :closable="false" :title="error" />
        <el-empty v-else-if="!clients.length" description="尚无已授权客户端" />
        <div v-for="client in clients" v-else :key="client.clientId" class="client-row">
          <div class="client-info">
            <strong>{{ client.clientId }}</strong>
            <p>{{ client.scopes.map(scope => mcpScopes.find(s => s.value === scope)?.label ?? scope).join('、') }}</p>
            <el-tag size="small" :type="client.status === 'ACTIVE' ? 'success' : 'info'">
              {{ client.status === 'ACTIVE' ? '已授权' : '已撤销' }}
            </el-tag>
          </div>
          <el-button v-if="client.status === 'ACTIVE'" type="danger" plain :loading="busy"
            @click="revoke(client)">撤销授权</el-button>
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>

<style scoped>
.mcp-clients{max-width:860px;margin:0 auto;padding-bottom:32px}
.back{display:inline-block;margin-bottom:16px;text-decoration:none;color:var(--el-color-primary)}
.section{margin-top:20px}.scope-option{margin-bottom:6px}
.client-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 0;border-bottom:1px solid var(--el-border-color-lighter)}
.pair-ticket{background:var(--el-fill-color-light);border-radius:10px;padding:14px;margin-top:16px}
.ticket-code{font-family:monospace;font-size:14px;overflow-wrap:anywhere}
.identity-list{margin-top:18px}.identity-list p{overflow-wrap:anywhere;font-size:13px;color:var(--el-text-color-secondary)}
.identity-unlink{display:flex;gap:12px;margin-top:12px;flex-wrap:wrap}
.identity-unlink .el-input{flex:1;min-width:220px}
.client-row:last-child{border-bottom:none}.client-info{min-width:0}
.client-info strong,.client-info p{overflow-wrap:anywhere}.client-info p{color:var(--el-text-color-secondary);font-size:13px}
</style>
