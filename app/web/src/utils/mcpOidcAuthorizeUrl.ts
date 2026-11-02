/**
 * Validate PRP's opt-in first-party Keycloak authorization redirect before
 * leaving the user's trusted PRP origin. Never accept a server-selected
 * callback, scope, grant type, or a fallback issuer.
 *
 * This client-side check is defense in depth; the backend still enforces
 * S256, state, nonce, signed ID Token and the exact callback.
 */
export function checkedFirstPartyAuthorizeUrl(
  authorizeUrl: string,
  approvedEndpoint: string | undefined,
  prpOrigin: string,
  basePath: string,
): string {
  if (!approvedEndpoint || !approvedEndpoint.startsWith('https://')) {
    throw new Error('OIDC_PINNED_ISSUER_REQUIRED')
  }
  if (!basePath.startsWith('/') || !basePath.endsWith('/') || basePath.includes('//')
      || basePath.includes('..') || basePath.includes('?') || basePath.includes('#')) {
    throw new Error('OIDC_INVALID_PRP_BASE')
  }

  let expected: URL
  let target: URL
  let origin: URL
  try {
    expected = new URL(approvedEndpoint)
    target = new URL(authorizeUrl)
    origin = new URL(prpOrigin)
  } catch {
    throw new Error('OIDC_INVALID_URL')
  }

  if (expected.protocol !== 'https:' || expected.username || expected.password
      || expected.search || expected.hash || !expected.pathname.endsWith('/protocol/openid-connect/auth')
      || expected.href !== approvedEndpoint || target.protocol !== 'https:'
      || target.username || target.password || target.hash
      || `${target.origin}${target.pathname}` !== approvedEndpoint
      || origin.protocol !== 'https:' || origin.username || origin.password
      || origin.pathname !== '/' || origin.search || origin.hash) {
    throw new Error('OIDC_UNTRUSTED_AUTHORIZATION_ENDPOINT')
  }

  const params = target.searchParams
  const keys = [
    'response_type', 'client_id', 'redirect_uri', 'scope',
    'state', 'nonce', 'code_challenge', 'code_challenge_method',
  ]
  const seen: string[] = []
  params.forEach((_value, key) => { seen.push(key) })
  if (seen.length !== keys.length
      || !keys.every(key => params.getAll(key).length === 1)
      || !seen.every(key => keys.includes(key))) {
    throw new Error('OIDC_NONCANONICAL_AUTHORIZATION_QUERY')
  }

  const expectedCallback = `${origin.origin}${basePath}me/mcp-link/callback`
  if (params.get('response_type') !== 'code'
      || params.get('client_id') !== 'prp-first-party-link'
      || params.get('redirect_uri') !== expectedCallback
      || params.get('scope') !== 'openid'
      || params.get('code_challenge_method') !== 'S256'
      || !/^[A-Za-z0-9_-]{43}$/.test(params.get('state') || '')
      || !/^[A-Za-z0-9_-]{43}$/.test(params.get('nonce') || '')
      || !/^[A-Za-z0-9_-]{43}$/.test(params.get('code_challenge') || '')) {
    throw new Error('OIDC_UNEXPECTED_AUTHORIZATION_PARAMETERS')
  }
  return target.toString()
}
