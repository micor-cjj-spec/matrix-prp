import { apiClient, apiUrl, type ApiResponse } from './client'
import { getStoredToken } from '@/utils/token'
import { createSseParser } from './sseParser'

export interface Conversation { id: string; title: string; updatedAt: string }
export interface AiMessageBlock { messageId: number; type: 'navigation' | 'wellness_draft'; module: string; label: string; route: string }
export interface ChatMessage { id: number; role: 'user' | 'assistant'; content: string; createdAt: string }
export interface AiUsage {
  month: string; requests: number; reservedTokens: number; inputTokens: number
  outputTokens: number; maxRequests: number; maxReservedTokens: number
}
export interface StreamEvent { event: 'meta' | 'delta' | 'tool' | 'done' | 'error'; data: Record<string, unknown> }
export class AiStreamHttpError extends Error {
  constructor(public readonly status: number) {
    super(`AI HTTP ${status}`)
    this.name = 'AiStreamHttpError'
  }
}

export async function listConversations() {
  return (await apiClient.get<ApiResponse<Conversation[]>>('/ai/conversations')).data.data
}
export async function listMessages(id: string, beforeId?: number, limit = 200) {
  return (await apiClient.get<ApiResponse<ChatMessage[]>>(
    `/ai/conversations/${encodeURIComponent(id)}/messages`,
    { params: { ...(beforeId === undefined ? {} : { beforeId }), limit } },
  )).data.data
}
export async function listMessageBlocks(id: string) {
  return (await apiClient.get<ApiResponse<AiMessageBlock[]>>(
    '/ai/conversations/' + encodeURIComponent(id) + '/blocks',
  )).data.data
}
export async function fetchUsage() {
  return (await apiClient.get<ApiResponse<AiUsage>>('/ai/usage')).data.data
}
export async function streamChat(conversationId: string | null, content: string,
                                 onEvent: (message: StreamEvent) => void, signal?: AbortSignal, contextScopes: string[] = [], contextToken?: string) {
  const response = await fetch(apiUrl('/ai/chat/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getStoredToken() ?? ''}` },
    body: JSON.stringify({ conversationId, content, contextScopes,
      contextToken }),
    signal,
  })
  // AI 接口鉴权失败不应该清除登录态。
  // 例如 API Key 配置错误、AI 服务额度不足、AI 模块独立权限异常时，不能导致整个 PRP 退出登录。
  if (!response.ok) throw new AiStreamHttpError(response.status)
  if (!response.body) throw new Error('AI streaming response has no body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parser = createSseParser(({ event, data }) => {
    if (event === 'meta' || event === 'delta' || event === 'tool' || event === 'done' || event === 'error') {
      onEvent({ event, data: JSON.parse(data) as Record<string, unknown> })
    }
  })
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      parser.feed(decoder.decode(value, { stream: true }))
    }
    parser.feed(decoder.decode())
  } finally {
    reader.releaseLock()
  }
}

export interface AiContextPreview {
  scopes: string[]
  date: string
  data: Record<string, unknown>
  previewId: string
}
export async function previewAiContext(scopes: string[]): Promise<AiContextPreview> {
  return (await apiClient.post<ApiResponse<AiContextPreview>>('/ai/context/preview', { scopes })).data.data
}

export interface AiContextConfirmation { contextToken: string; scopes: string[] }
export async function confirmAiContext(previewId: string): Promise<AiContextConfirmation> {
  return (await apiClient.post<ApiResponse<AiContextConfirmation>>('/ai/context/confirm', { previewId })).data.data
}

export interface InlineHealthDraftResponse { conversationId: string; messageId: number; draft: { draftId: string } }
export async function prepareInlineHealthDraft(text: string, conversationId: string | null, image?: File | null) {
  const data = new FormData()
  data.append('text', text)
  if (conversationId) data.append('conversationId', conversationId)
  if (image) data.append('image', image)
  const result = await apiClient.post<ApiResponse<InlineHealthDraftResponse>>('/wellness/ai/chat/prepare', data, { timeout: 60000 })
  return result.data.data
}

export interface InlineHealthConfirmation {
  messageId: number; content: string; status: 'SAVED' | 'ALREADY_SAVED' | 'MULTIPLE_PENDING' | 'NO_PENDING'
  route: string
}
export async function confirmPendingHealthDraft(conversationId: string, message: string) {
  return (await apiClient.post<ApiResponse<InlineHealthConfirmation>>(
    '/wellness/ai/chat/confirm-pending', { conversationId, message }, { timeout: 45000 }
  )).data.data
}
