import axios, { AxiosError } from 'axios'
import { loadConfig } from './config.js'

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
}

export async function request<T>(
  method: 'delete' | 'get' | 'patch' | 'post' | 'put',
  path: string,
  data?: unknown,
  params?: Record<string, unknown>,
  apiBaseUrl?: string,
): Promise<T> {
  const config = await loadConfig()
  try {
    const response = await axios.request<ApiResponse<T>>({
      method,
      baseURL: apiBaseUrl ?? config.apiBaseUrl,
      url: path,
      data,
      params,
      headers: config.token ? { Authorization: `Bearer ${config.token}` } : undefined,
      timeout: 10000,
    })
    return response.data.data
  } catch (error) {
    if (error instanceof AxiosError) {
      const status = error.response?.status
      const message = error.response?.data?.message ?? error.message
      throw new Error(status ? `HTTP ${status}: ${message}` : message)
    }
    throw error
  }
}
