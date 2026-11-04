import { describe, expect, it } from 'vitest'
import { latestChatToRestore, shouldApplyLoadedConversation } from '../../web/src/utils/chatRestore'
import { isUserSessionExpired } from '../../web/src/utils/authSession'
import { AI_PHOTO_MAX_BYTES, photoDisposition, scaledPhotoDimensions } from '../../web/src/utils/mealPhoto'

const ready = () => ({
  selectedId: null,
  hasMessages: false,
  isSending: false,
  explicitlyStartedNew: false,
  hasDraft: false,
})

describe('chat conversation restoration', () => {
  const history = [{ id: 'latest' }, { id: 'older' }]

  it('restores the newest history only when no conversation is being composed', () => {
    expect(latestChatToRestore(history, ready())).toBe('latest')
    expect(latestChatToRestore(history, { ...ready(), explicitlyStartedNew: true })).toBeNull()
    expect(latestChatToRestore(history, { ...ready(), hasDraft: true })).toBeNull()
    expect(latestChatToRestore(history, { ...ready(), isSending: true })).toBeNull()
  })

  it('rejects a stale async response and preserves a newly composed message', () => {
    expect(shouldApplyLoadedConversation(history, 'latest', true, 2, 3, ready())).toBe(false)
    expect(shouldApplyLoadedConversation(history, 'latest', true, 3, 3, {
      ...ready(), hasMessages: true,
    })).toBe(false)
    expect(shouldApplyLoadedConversation(history, 'latest', true, 3, 3, ready())).toBe(true)
    expect(shouldApplyLoadedConversation(history, 'older', false, 3, 3, ready())).toBe(true)
  })
})

describe('auth session error classification', () => {
  it('invalidates sessions only when the server definitively rejects the token', () => {
    expect(isUserSessionExpired({ response: { status: 401 } })).toBe(true)
    expect(isUserSessionExpired({ response: { status: 503 } })).toBe(false)
    expect(isUserSessionExpired(new Error('network timeout'))).toBe(false)
    expect(isUserSessionExpired(null)).toBe(false)
  })
})

describe('safe meal photo preprocessing', () => {
  it('retains compliant images but converts larger source images', () => {
    expect(photoDisposition({ name: 'meal.jpg', type: 'image/jpeg', size: AI_PHOTO_MAX_BYTES }))
      .toBe('keep')
    expect(photoDisposition({ name: 'meal.jpg', type: 'image/jpeg', size: AI_PHOTO_MAX_BYTES + 1 }))
      .toBe('convert')
    expect(photoDisposition({ name: 'meal.heic', type: 'image/heic', size: 1_024 }))
      .toBe('convert')
    expect(() => photoDisposition({ name: 'script.svg', type: 'image/svg+xml', size: 1_024 }))
      .toThrow('请选择')
    expect(() => photoDisposition({ name: 'meal.jpg', type: 'image/jpeg', size: 25_000_001 }))
      .toThrow('25 MB')
  })

  it('never enlarges images while resizing to safe canvas dimensions', () => {
    expect(scaledPhotoDimensions(4096, 2048, 2048)).toEqual({ width: 2048, height: 1024 })
    expect(scaledPhotoDimensions(800, 600, 2048)).toEqual({ width: 800, height: 600 })
    expect(() => scaledPhotoDimensions(0, 600, 2048)).toThrow('图片尺寸无效')
  })
})
