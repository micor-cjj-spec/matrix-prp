import { apiClient, type ApiResponse } from './client'

export interface AiProvider {
  id: string
  name: string
  models: string[]
  defaultModel: string
  configured: boolean
  personalKey: boolean
}
export interface AiSettings {
  selectedProvider: string
  selectedModel: string
  providers: AiProvider[]
}
export async function getAiSettings(): Promise<AiSettings> {
  return (await apiClient.get<ApiResponse<AiSettings>>('/ai/settings')).data.data
}
export async function saveAiKey(provider: string, apiKey: string): Promise<AiSettings> {
  return (await apiClient.put<ApiResponse<AiSettings>>(
    `/ai/settings/providers/${encodeURIComponent(provider)}/key`, { apiKey })).data.data
}
export async function removeAiKey(provider: string): Promise<AiSettings> {
  return (await apiClient.delete<ApiResponse<AiSettings>>(
    `/ai/settings/providers/${encodeURIComponent(provider)}/key`)).data.data
}
export async function setAiSelection(provider: string, model: string): Promise<AiSettings> {
  return (await apiClient.put<ApiResponse<AiSettings>>('/ai/settings/selection', { provider, model })).data.data
}
export async function testAiProvider(provider: string, model: string): Promise<void> {
  await apiClient.post(`/ai/settings/providers/${encodeURIComponent(provider)}/test`,
    { provider, model }, { timeout: 30000 })
}

export interface AiInvocationDetail {
  provider: string
  model: string
  credentialSource: string
  status: 'SUCCESS' | 'FAILURE'
  failureCategory: string | null
  elapsedMs: number
  firstTokenMs: number | null
  inputTokens: number | null
  outputTokens: number | null
  occurredAt: string
}
export interface AiTelemetry {
  summary: {
    totalRequests: number
    successfulRequests: number
    failedRequests: number
    averageElapsedMs: number | null
    averageFirstTokenMs: number | null
    inputTokens: number
    outputTokens: number
    unreportedUsageRequests: number
  }
  recent: AiInvocationDetail[]
  costStatus: string
}
export async function fetchAiTelemetry(days: 1 | 7 | 30 = 7): Promise<AiTelemetry> {
  return (await apiClient.get<ApiResponse<AiTelemetry>>('/ai/telemetry', { params: { days, limit: 20 } })).data.data
}
