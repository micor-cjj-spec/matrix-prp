import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchCurrentUser, login, register, type RegisterRequest, type UserProfile } from '@/api/auth'
import { getStoredToken, removeStoredToken, setStoredToken } from '@/utils/token'
import { isUserSessionExpired } from '@/utils/authSession'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getStoredToken())
  const user = ref<UserProfile | null>(null)
  let profileRequest: Promise<void> | null = null

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
    if (!token.value || user.value) return
    // The startup bootstrap and navigation guard share one in-flight lookup.
    if (profileRequest) return profileRequest
    const expectedToken = token.value
    profileRequest = (async () => {
      try {
        const profile = await fetchCurrentUser()
        if (token.value === expectedToken) user.value = profile
      } catch (error) {
        // Preserve a valid stored JWT when the server is temporarily unreachable.
        if (token.value === expectedToken && isUserSessionExpired(error)) logout()
        throw error
      }
    })()
    try { await profileRequest }
    finally { profileRequest = null }
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
