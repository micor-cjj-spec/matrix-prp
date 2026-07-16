const TOKEN_KEY = 'matrix-prp-token'

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
}

export function getToken() {
  return uni.getStorageSync(TOKEN_KEY) as string | undefined
}

export function setToken(token: string) {
  uni.setStorageSync(TOKEN_KEY, token)
}

export function clearToken() {
  uni.removeStorageSync(TOKEN_KEY)
}

export function request<T>(options: UniApp.RequestOptions): Promise<T> {
  const token = getToken()
  return new Promise((resolve, reject) => {
    uni.request({
      ...options,
      url: `/api${options.url}`,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.header ?? {}),
      },
      success(response) {
        if (response.statusCode === 401) {
          clearToken()
          uni.redirectTo({ url: '/pages/login/index' })
          reject(new Error('Unauthorized'))
          return
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`HTTP ${response.statusCode}`))
          return
        }
        resolve((response.data as ApiResponse<T>).data)
      },
      fail(error) {
        reject(error)
      },
    })
  })
}
