import axios from 'axios'
import { getStoredToken, removeStoredToken } from '@/utils/token'

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`,
  timeout: 8000,
})

apiClient.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      removeStoredToken()
      window.dispatchEvent(new CustomEvent('matrix-prp:unauthorized'))
    }
    return Promise.reject(error)
  },
)
