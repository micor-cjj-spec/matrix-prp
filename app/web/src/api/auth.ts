import { apiClient, type ApiResponse } from './client'

export interface UserProfile {
  id: number
  username: string
  displayName: string
  administrator: boolean
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

export interface RegisterRequest {
  username: string
  password: string
  displayName: string
  invitationCode: string
}
export async function register(request: RegisterRequest) {
  const response = await apiClient.post<ApiResponse<LoginResponse>>('/auth/register', request)
  return response.data.data
}
export async function createInvitation() {
  const response = await apiClient.post<ApiResponse<{ code: string; expiresAt: string }>>('/auth/invitations', {})
  return response.data.data
}
