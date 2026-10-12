import { apiClient, type ApiResponse } from './client'
import { getStoredToken, removeStoredToken } from '@/utils/token'

export interface Conversation { id: string; title: string; updatedAt: string }
export interface ChatMessage { id: number; role: 'user' | 'assistant'; content: string; createdAt: string }
export interface AiUsage {
  month: string; requests: number; reservedTokens: number; inputTokens: number
  outputTokens: number; maxRequests: number; maxReservedTokens: number
}
export interface StreamEvent { event: 'meta' | 'delta' | 'done' | 'error'; data: Record<string, unknown> }

export async function listConversations() {
  return (await apiClient.get<ApiResponse<Conversation[]>>('/ai/conversations')).data.data
}
export async function listMessages(id: string) {
  return (await apiClient.get<ApiResponse<ChatMessage[]>>(`/ai/conversations/${encodeURIComponent(id)}/messages`)).data.data
}
export async function fetchUsage() {
  return (await apiClient.get<ApiResponse<AiUsage>>('/ai/usage')).data.data
}
export async function streamChat(conversationId: string | null, content: string,
                                 onEvent: (message: StreamEvent) => void, signal?: AbortSignal, contextScopes: string[] = [], contextToken?: string) {
  const response = await fetch('/api/ai/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getStoredToken() ?? ''}` },
    body: JSON.stringify({ conversationId, content, contextScopes,
      contextToken }),
    signal,
  })
  if (response.status === 401) {
    removeStoredToken()
    window.dispatchEvent(new CustomEvent('matrix-prp:unauthorized'))
  }
  if (!response.ok || !response.body) throw new Error(`AI HTTP ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim()
        const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (event && data && ['meta', 'delta', 'done', 'error'].includes(event))
          onEvent({ event: event as StreamEvent['event'], data: JSON.parse(data) as Record<string, unknown> })
      }
    }
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
