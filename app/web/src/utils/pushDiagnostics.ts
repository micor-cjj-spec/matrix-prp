/**
 * Browser Web Push diagnostics. No push endpoint, JWT or cryptographic
 * subscription secret should appear in user-facing error messages.
 */
export type PushStage =
  | 'environment'
  | 'permission'
  | 'vapid'
  | 'serviceWorker'
  | 'browserSubscription'
  | 'serverRegistration'

export const pushStageLabels: Record<PushStage, string> = {
  environment: '检查运行环境',
  permission: '申请通知权限',
  vapid: '获取服务端 VAPID 公钥',
  serviceWorker: '注册 Service Worker',
  browserSubscription: '创建浏览器推送订阅',
  serverRegistration: '向服务器登记当前设备',
}

export function isIosDevice(): boolean {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
    (/Macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1)
}

export function isInstalledPwa(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
}

export function decodeVapidPublicKey(key: string): Uint8Array {
  const trimmed = key.trim()
  if (!/^[A-Za-z0-9+/_-]+={0,2}$/.test(trimmed)) {
    throw new Error('VAPID 公钥不是有效的 Base64/Base64URL')
  }
  const base64 = trimmed.replace(/-/g, '+').replace(/_/g, '/')
  let decoded: string
  try {
    decoded = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='))
  } catch {
    throw new Error('VAPID 公钥无法解码')
  }
  if (decoded.length !== 65 || decoded.charCodeAt(0) !== 4) {
    throw new Error('VAPID 公钥必须是 65 字节的 P-256 非压缩公钥')
  }
  return Uint8Array.from(decoded, (char) => char.charCodeAt(0))
}

export function samePublicKey(previous: ArrayBuffer | null, current: Uint8Array): boolean {
  if (!previous) return true // Some browser versions do not expose subscription options.
  const bytes = new Uint8Array(previous)
  return bytes.length === current.length && bytes.every((byte, index) => byte === current[index])
}

export interface PushFailure {
  message: string
  nextStep: string
}

export function describePushFailure(stage: PushStage, error: unknown): PushFailure {
  const exception = error instanceof Error ? error : null
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status
  const httpStatus = typeof status === 'number' ? status : null
  const step = pushStageLabels[stage]

  if (stage === 'environment') {
    return { message: '当前环境不支持系统推送', nextStep: '请使用 HTTPS；iPhone 需先添加到主屏幕，再从图标打开。' }
  }
  if (stage === 'permission') {
    return { message: '未获得系统通知权限', nextStep: '请在 iPhone 设置中允许该主屏幕应用发送通知，然后重新尝试。' }
  }
  if (stage === 'vapid') {
    return { message: step + '失败', nextStep: '请检查 /api/push/vapid-public-key 是否正常，并确认配置的是 65 字节 P-256 公钥。' }
  }
  if (stage === 'serviceWorker') {
    return { message: step + '失败' + (exception?.name ? '（' + exception.name + '）' : ''), nextStep: '检查 HTTPS 和 /sw.js 是否返回 JavaScript 文件，且未被重定向到登录页。' }
  }
  if (stage === 'browserSubscription') {
    if (exception?.name === 'NotAllowedError') {
      return { message: '浏览器拒绝了推送订阅（NotAllowedError）', nextStep: 'iPhone 请从主屏幕应用启动，并确认系统通知权限和推送策略。' }
    }
    if (exception?.name === 'AbortError') {
      return { message: '浏览器推送服务订阅失败（AbortError）', nextStep: '检查网络是否能连接 Apple 推送服务，关闭可能阻断推送的代理后重试。' }
    }
    return { message: step + '失败' + (exception?.name ? '（' + exception.name + '）' : ''), nextStep: '检查浏览器推送支持情况、网络及是否更换过 VAPID 公钥。' }
  }
  if (httpStatus === 400) {
    return { message: step + '失败（HTTP 400）', nextStep: '检查服务端推送端点白名单和订阅密钥校验，查看 API 返回的错误信息。' }
  }
  if (httpStatus === 401 || httpStatus === 403) {
    return { message: step + '失败（HTTP ' + httpStatus + '）', nextStep: '请重新登录，再尝试登记推送设备。' }
  }
  if (httpStatus === 404) {
    return { message: step + '失败（HTTP 404）', nextStep: '检查 HTTPS 反向代理是否正确转发 /api/push/subscriptions。' }
  }
  if (httpStatus !== null && httpStatus >= 500) {
    return { message: step + '失败（HTTP ' + httpStatus + '）', nextStep: '检查后端日志、数据库连接和 004-notification-center.sql 数据迁移。' }
  }
  return {
    message: step + '失败' + (httpStatus !== null ? '（HTTP ' + httpStatus + '）' : ''),
    nextStep: '查看浏览器开发者工具 Network/Console，以及服务器日志确认具体错误。',
  }
}
