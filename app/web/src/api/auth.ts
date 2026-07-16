import { apiClient, type ApiResponse } from './client'

export interface UserProfile {
  id: number
  username: string
  displayName: string
}

export interface LoginResponse {
  token: string
  tokenType: string
  expiresInSeconds: number
  user: UserProfile
}

export async function login(username: string, password: string) {
  const response = await apiClient.post<ApiResponse<LoginResponse>>('/auth/login', {
    username,
    password,
  })
  return response.data.data
}

export async function fetchCurrentUser() {
  const response = await apiClient.get<ApiResponse<UserProfile>>('/users/me')
  return response.data.data
}
