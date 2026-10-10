import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchCurrentUser, login, register, type RegisterRequest, type UserProfile } from '@/api/auth'
import { getStoredToken, removeStoredToken, setStoredToken } from '@/utils/token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getStoredToken())
  const user = ref<UserProfile | null>(null)

  const isAuthenticated = computed(() => Boolean(token.value))

  async function loginWithPassword(username: string, password: string) {
    const response = await login(username, password)
    token.value = response.token
    user.value = response.user
    setStoredToken(response.token)
  }

  async function registerWithInvitation(request: RegisterRequest) {
    const response = await register(request)
    token.value = response.token
    user.value = response.user
    setStoredToken(response.token)
  }

  async function loadCurrentUser() {
    if (!token.value) return
    try {
      user.value = await fetchCurrentUser()
    } catch (error) {
      logout()
      throw error
    }
  }

  function logout() {
    token.value = null
    user.value = null
    removeStoredToken()
  }

  return {
    token,
    user,
    isAuthenticated,
    loginWithPassword,
    registerWithInvitation,
    loadCurrentUser,
    logout,
  }
})
