import { apiClient, type ApiResponse } from './client'

export interface FirstPartyOidcResult {
  issuer: string
  newlyLinked: boolean
}

/** Requires the user's ordinary PRP Bearer session, not an external OAuth JWT. */
export async function beginFirstPartyOidcLink(password: string): Promise<string> {
  const response = await apiClient.post<ApiResponse<{ authorizeUrl: string }>>(
    '/mcp/identity/oidc/start', { password },
  )
  return response.data.data.authorizeUrl
}

/** State, code and issuer are only delivered to PRP; never to ChatGPT/chat. */
export async function finishFirstPartyOidcLink(
  state: string, code: string, iss: string,
): Promise<FirstPartyOidcResult> {
  const response = await apiClient.post<ApiResponse<FirstPartyOidcResult>>(
    '/mcp/identity/oidc/finish', { state, code, iss },
  )
  return response.data.data
}
