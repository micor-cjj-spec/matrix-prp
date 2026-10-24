<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { apiUrl } from '@/api/client'
import {
  browserPairingConfig, createBrowserPairingRequest, exchangeBrowserPairingToken,
  hasOAuthCallback, readBrowserPairingCallback, MCP_BROWSER_PAIRING_STORAGE_KEY,
  type McpBrowserPairingConfig, type McpPendingBrowserPairing,
} from '@/api/mcpBrowserPairing'
import {
  authorizeMcpClient, listMcpClients, mcpScopes, revokeMcpClient,
  type McpClientGrant,
} from '@/api/mcpClients'
import {
  createMcpIdentityTicket, listMcpIdentityLinks, unlinkMcpIdentity,
  type McpIdentityLink, type McpLinkTicket,
} from '@/api/mcpIdentity'

// This is a separate, admin-approved public Keycloak S256 client, NOT
// ChatGPT's client. All VITE_ config is public and contains no credentials.
const pairingPassword = ref('')
const pairingBusy = ref(false)
const pairingStatus = ref('')
const pairingError = ref('')
const pairingCleanupWarning = ref('')
const pendingBrowserPairing = ref(false)
let browserConfig: McpBrowserPairingConfig | null = null
try {
  const redirect = new URL('me/mcp-clients', new URL(import.meta.env.BASE_URL, window.location.origin))
  browserConfig = browserPairingConfig(
    import.meta.env.VITE_MCP_PAIRING_ISSUER,
    import.meta.env.VITE_MCP_PAIRING_CLIENT_ID,
    import.meta.env.VITE_MCP_PAIRING_RESOURCE,
    redirect.toString(),
  )
} catch {
  pairingError.value = '浏览器 OAuth 配对配置不合法，请联系 PRP 管理员。'
}

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

async function revokePairingOnlyGrant(clientId: string): Promise<boolean> {
  try {
    await revokeMcpClient(clientId)
    pairingCleanupWarning.value = ''
    return true
  } catch {
    // A failure must be prominent: this is an active task-read grant, not
    // harmless browser state. Never claim cleanup or link success hides it.
    pairingCleanupWarning.value =
      '临时配对客户端授权未能自动撤销！请在下方“已登记的客户端”中手动撤销：' + clientId
    return false
  }
}

async function beginBrowserPairing() {
  const config = browserConfig
  if (!config || !pairingPassword.value || pairingBusy.value) return
  pairingBusy.value = true
  pairingError.value = ''
  pairingStatus.value = ''
  pairingCleanupWarning.value = ''
  let grantIssued = false
  try {
    const ownerPassword = pairingPassword.value
    // A temporary task-read grant is needed for the one-use ticket and must
    // be revoked even if ticket creation or browser navigation fails.
    await authorizeMcpClient(config.clientId, ['prp.tasks.read'], ownerPassword)
    grantIssued = true
    const ticket = await createMcpIdentityTicket(config.clientId, ownerPassword)
    const request = await createBrowserPairingRequest(config, ticket.code)
    sessionStorage.setItem(MCP_BROWSER_PAIRING_STORAGE_KEY, JSON.stringify(request.pending))
    pendingBrowserPairing.value = true
    pairingPassword.value = ''
    // Same-tab redirect keeps the state in tab-scoped sessionStorage.
    window.location.assign(request.url)
  } catch {
    sessionStorage.removeItem(MCP_BROWSER_PAIRING_STORAGE_KEY)
    pendingBrowserPairing.value = false
    pairingPassword.value = ''
    pairingError.value = '启动 OAuth 关联失败，请检查密码、Keycloak 配置或浏览器设置。'
    if (grantIssued) await revokePairingOnlyGrant(config.clientId)
    await refresh()
  } finally {
    pairingBusy.value = false
  }
}

async function cancelBrowserPairing() {
  if (pairingBusy.value || !browserConfig) return
  pairingBusy.value = true
  pairingStatus.value = ''
  sessionStorage.removeItem(MCP_BROWSER_PAIRING_STORAGE_KEY)
  pendingBrowserPairing.value = false
  const cleaned = await revokePairingOnlyGrant(browserConfig.clientId)
  if (cleaned) pairingStatus.value = '已取消未完成的 OAuth 配对并撤销临时客户端权限。'
  await refresh()
  pairingBusy.value = false
}

async function inspectUnfinishedBrowserPairing() {
  if (!browserConfig || hasOAuthCallback(window.location.href)) return
  const raw = sessionStorage.getItem(MCP_BROWSER_PAIRING_STORAGE_KEY)
  if (!raw) return
  let shouldCancel = true
  try {
    const value = JSON.parse(raw) as McpPendingBrowserPairing
    shouldCancel = value.version !== 1 || value.clientId !== browserConfig.clientId ||
      !Number.isFinite(value.createdAt) || value.createdAt > Date.now() ||
      Date.now() - value.createdAt >= 9 * 60 * 1000
  } catch { shouldCancel = true }
  pendingBrowserPairing.value = true
  if (shouldCancel) await cancelBrowserPairing()
}

async function finishBrowserPairing() {
  const original = window.location.href
  if (!hasOAuthCallback(original)) return
  // Remove code/state from the address bar *before* any OAuth/token requests.
  window.history.replaceState(window.history.state, '', window.location.pathname)
  const pendingRaw = sessionStorage.getItem(MCP_BROWSER_PAIRING_STORAGE_KEY)
  sessionStorage.removeItem(MCP_BROWSER_PAIRING_STORAGE_KEY)
  pendingBrowserPairing.value = false
  pairingBusy.value = true
  pairingStatus.value = ''
  pairingError.value = ''
  let linkedSuccessfully = false
  try {
    if (!browserConfig) throw new Error('OAuth 配对尚未配置')
    let pending: McpPendingBrowserPairing | null = null
    try { pending = pendingRaw ? JSON.parse(pendingRaw) as McpPendingBrowserPairing : null }
    catch { pending = null }
    const { code, verifier, ticket } = readBrowserPairingCallback(original, browserConfig, pending)
    // OAuth bearer is transient and never copied into storage, URL or chat.
    const bearer = await exchangeBrowserPairingToken(browserConfig, code, verifier)
    const response = await fetch(apiUrl('/mcp/link'), {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + bearer,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ ticket }),
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
    })
    if (!response.ok) throw new Error('PRP 关联服务拒绝了已验证 OAuth 身份')
    const result = await response.json() as { data?: { issuer?: string, subject?: string } }
    if (!result.data?.issuer || !result.data.subject) throw new Error('PRP 未确认身份关联')
    linkedSuccessfully = true
  } catch (err) {
    pairingError.value = err instanceof Error ? err.message : 'OAuth 配对失败，请重新发起'
  } finally {
    // Success, denial, token/CORS failure, issuer mismatch and timeout all
    // revoke the temporary owner grant. A browser that never returns cannot
    // run this cleanup; the pending flow remains cancellable on revisit.
    const revoked = browserConfig ? await revokePairingOnlyGrant(browserConfig.clientId) : false
    if (linkedSuccessfully) {
      pairingStatus.value = revoked
        ? 'Keycloak 身份已关联 PRP，临时配对权限已撤销；现在可单独批准 ChatGPT 的任务只读权限。'
        : 'Keycloak 身份已关联 PRP，但临时配对权限仍需手动撤销。'
    }
    await Promise.all([refresh(), refreshIdentities()])
    pairingBusy.value = false
  }
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
onMounted(() => {
  void refresh()
  void refreshIdentities()
  if (hasOAuthCallback(window.location.href)) void finishBrowserPairing()
  else void inspectUnfinishedBrowserPairing()
})
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
      <el-card v-if="browserConfig" shadow="never" class="section">
        <template #header>浏览器一键关联 Keycloak 身份</template>
        <p>适用于 iPhone 和电脑。通过独立的 Keycloak 公共配对客户端完成 PKCE S256 登录，不需要在 ChatGPT 里粘贴任何关联码。临时任务只读授权会在完成关联后自动撤销。</p>
        <el-form label-position="top" @submit.prevent="beginBrowserPairing">
          <el-form-item label="再次输入 PRP 密码以启动绑定">
            <el-input v-model="pairingPassword" type="password" show-password
              autocomplete="current-password" maxlength="256"
              placeholder="仅发送给 PRP，不发送到 Keycloak 或 AI 客户端" />
          </el-form-item>
          <el-button native-type="submit" type="primary"
            :loading="pairingBusy" :disabled="!pairingPassword || pairingBusy">
            跳转 Keycloak 安全登录并关联
          </el-button>
        </el-form>
        <el-alert v-if="pendingBrowserPairing" type="warning" :closable="false"
          title="检测到未完成的 OAuth 配对：临时任务读取授权可能仍有效，请完成登录或取消并撤销。" class="section" />
        <el-button v-if="pendingBrowserPairing" type="warning" plain :loading="pairingBusy"
          :disabled="pairingBusy" @click="cancelBrowserPairing">取消配对并撤销临时授权</el-button>
        <el-alert v-if="pairingStatus" type="success" :closable="false" :title="pairingStatus" class="section" />
        <el-alert v-if="pairingError" type="error" :closable="false" :title="pairingError" class="section" />
        <el-alert v-if="pairingCleanupWarning" type="error" :closable="false"
          :title="pairingCleanupWarning" class="section" />
        <p>需管理员事先在 Keycloak 注册独立配对客户端，并允许当前 PRP 页面域名的 CORS。不能复用 ChatGPT 的 OAuth Client ID。</p>
      </el-card>
      <el-card shadow="never" class="section">
        <template #header>关联 PRP 与外部 OAuth 账号（高级方式）</template>
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
