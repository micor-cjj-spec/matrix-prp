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
