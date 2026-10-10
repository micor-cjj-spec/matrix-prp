import { request, setToken } from './client'

export interface LoginResponse {
  token: string
  user: {
    id: number
    username: string
    displayName: string
  }
}

export async function login(username: string, password: string) {
  const response = await request<LoginResponse>({
    method: 'POST',
    url: '/auth/login',
    data: { username, password },
  })
  setToken(response.token)
  return response
}

export async function registerAccount(username: string, password: string, displayName: string, invitationCode: string) {
  const response = await request<LoginResponse>({
    method: 'POST',
    url: '/auth/register',
    data: { username, password, displayName, invitationCode },
  })
  setToken(response.token)
  return response
}
