/**
 * First-party browser pairing for the owner-controlled PRP MCP identity link.
 *
 * This uses a SEPARATELY registered public, PKCE-only Keycloak client.
 * It must never reuse ChatGPT's client ID/private key or a production admin
 * token. OAuth access tokens remain in memory, are never logged or persisted,
 * and are accepted only by PRP's existing JWKS-validated /api/mcp/link route.
 */
export interface McpBrowserPairingConfig {
  issuer: string
  clientId: string
  resource: string
  redirectUri: string
}

export interface McpPendingBrowserPairing {
  version: 1
  state: string
  verifier: string
  ticket: string
  createdAt: number
  clientId: string
  issuer: string
}

export const MCP_BROWSER_PAIRING_STORAGE_KEY = 'matrix-prp:mcp-browser-pairing:v1'
const PAIRING_MAX_AGE_MS = 9 * 60 * 1000

function canonicalHttps(value: string, label: string): string {
  const parsed = new URL(value)
  if (parsed.protocol !== 'https:' || !parsed.hostname ||
    parsed.username || parsed.password || parsed.hash || parsed.search ||
    (parsed.port && parsed.port !== '443')) {
    throw new Error(`无效的${label} URL 配置`)
  }
  return parsed.toString().replace(/\/$/, '')
}

/** Return null instead of exposing an interactive wizard without its prerequisites. */
export function browserPairingConfig(
  issuer: string | undefined,
  clientId: string | undefined,
  resource: string | undefined,
  pageUrl: string,
): McpBrowserPairingConfig | null {
  if (!issuer?.trim() || !clientId?.trim() || !resource?.trim()) return null
  const normalizedClient = clientId.trim()
  // An independent static public pairing client; never impersonate ChatGPT.
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._~-]{1,127}$/.test(normalizedClient)) {
    throw new Error('无效的配对 OAuth 客户端 ID')
  }
  const url = new URL(pageUrl)
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' &&
    (url.hostname === '127.0.0.1' || url.hostname === 'localhost'))) {
    throw new Error('配对页面必须使用 HTTPS 或本地开发地址')
  }
  if (url.search || url.hash || !url.pathname.endsWith('/me/mcp-clients')) {
    throw new Error('配对回调必须是固定的 MCP 客户端管理页面')
  }
  const normalizedResource = canonicalHttps(resource.trim(), 'MCP Resource')
  if (!new URL(normalizedResource).pathname.endsWith('/api/mcp')) {
    throw new Error('MCP Resource 必须是 /api/mcp')
  }
  return {
    issuer: canonicalHttps(issuer.trim(), 'OAuth Issuer'),
    clientId: normalizedClient,
    resource: normalizedResource,
    redirectUri: url.toString(),
  }
}

function base64url(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function randomUrlSafe(bytes = 32): string {
  const entropy = new Uint8Array(bytes)
  crypto.getRandomValues(entropy)
  return base64url(entropy)
}

export async function createBrowserPairingRequest(
  config: McpBrowserPairingConfig,
  ticket: string,
  createdAt = Date.now(),
): Promise<{ url: string, pending: McpPendingBrowserPairing }> {
  if (!/^[A-Za-z0-9_-]{43}$/.test(ticket)) throw new Error('PRP 一次性配对码格式无效')
  const state = randomUrlSafe()
  const verifier = randomUrlSafe(48)
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  const codeChallenge = base64url(new Uint8Array(digest))
  const url = new URL(config.issuer + '/protocol/openid-connect/auth')
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('client_id', config.clientId)
  url.searchParams.set('redirect_uri', config.redirectUri)
  url.searchParams.set('scope', 'openid prp.tasks.read')
  url.searchParams.set('resource', config.resource)
  url.searchParams.set('code_challenge', codeChallenge)
  url.searchParams.set('code_challenge_method', 'S256')
  url.searchParams.set('state', state)
  return {
    url: url.toString(),
    pending: {
      version: 1, state, verifier, ticket, createdAt,
      clientId: config.clientId, issuer: config.issuer,
    },
  }
}

export function hasOAuthCallback(url: string): boolean {
  const query = new URL(url).searchParams
  return query.has('code') || query.has('state') || query.has('error')
}

export function readBrowserPairingCallback(
  callbackUrl: string,
  config: McpBrowserPairingConfig,
  pending: McpPendingBrowserPairing | null,
  now = Date.now(),
): { code: string, verifier: string, ticket: string } {
  if (!pending || pending.version !== 1) throw new Error('没有有效的 OAuth 配对请求，请重新发起')
  if (!Number.isFinite(pending.createdAt) || now < pending.createdAt ||
      now - pending.createdAt >= PAIRING_MAX_AGE_MS) {
    throw new Error('账号配对请求已过期，请重新发起')
  }
  if (pending.issuer !== config.issuer || pending.clientId !== config.clientId ||
      !/^[A-Za-z0-9_-]{43}$/.test(pending.ticket) ||
      !/^[A-Za-z0-9_-]{64}$/.test(pending.verifier)) {
    throw new Error('账号配对请求与当前配置不匹配')
  }
  const url = new URL(callbackUrl)
  if (url.origin + url.pathname !== config.redirectUri) {
    throw new Error('OAuth 返回地址与受信任的回调地址不一致')
  }
  const params = url.searchParams
  if (params.has('error')) throw new Error('Keycloak 授权被取消或拒绝')
  if (params.getAll('state').length !== 1 || params.get('state') !== pending.state) {
    throw new Error('OAuth state 不匹配，已拒绝关联')
  }
  // Keycloak 26.8 emits RFC 9207 iss. Deny absent or mismatching issuer.
  if (params.getAll('iss').length !== 1 || params.get('iss') !== config.issuer) {
    throw new Error('OAuth Issuer 不匹配，已拒绝关联')
  }
  const code = params.getAll('code')
  if (code.length !== 1 || !code[0]) throw new Error('OAuth 授权码缺失或重复')
  return { code: code[0], verifier: pending.verifier, ticket: pending.ticket }
}

export async function exchangeBrowserPairingToken(
  config: McpBrowserPairingConfig,
  code: string,
  verifier: string,
): Promise<string> {
  const form = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    code,
    code_verifier: verifier,
    resource: config.resource,
  })
  const response = await fetch(config.issuer + '/protocol/openid-connect/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: form,
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    referrerPolicy: 'no-referrer',
  })
  if (!response.ok) throw new Error('Keycloak 授权码交换失败，请检查配对客户端和 CORS 配置')
  const raw = await response.text()
  if (raw.length > 50000) throw new Error('Keycloak 返回内容超出安全限制')
  const data: unknown = JSON.parse(raw)
  if (!data || typeof data !== 'object' || !('access_token' in data) ||
      !('token_type' in data) || data.token_type !== 'Bearer' ||
      typeof data.access_token !== 'string' || !data.access_token) {
    throw new Error('Keycloak 未返回可用的 Bearer Token')
  }
  return data.access_token
}
