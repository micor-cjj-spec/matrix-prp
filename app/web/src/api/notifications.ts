import { apiClient, type ApiResponse } from './client'

export type Frequency = 'ONCE' | 'DAILY' | 'WEEKDAYS' | 'WEEKLY' | 'MONTHLY'
export interface ReminderPayload {
  title: string
  body: string
  category: string
  scheduleType: Frequency
  timezone: string
  localTime: string | null
  weekdays: string
  monthDay: number | null
  onceAt: string | null
}
export interface Reminder extends ReminderPayload {
  id: number
  nextFireAt: string | null
  enabled: number | boolean
}
export interface InboxItem {
  id: number
  title: string
  body: string
  category: string
  createdAt: string
  readAt: string | null
}
export interface Device {
  id: number
  deviceName: string
  createdAt: string
}
const data = async <T>(request: Promise<{ data: ApiResponse<T> }>) => (await request).data.data
export const getReminders = () => data(apiClient.get<ApiResponse<Reminder[]>>('/notification-rules'))
export const createReminder = (payload: ReminderPayload) => data(apiClient.post<ApiResponse<number>>('/notification-rules', payload))
export const updateReminder = (id: number, payload: ReminderPayload) => data(apiClient.put<ApiResponse<void>>(`/notification-rules/${id}`, payload))
export const changeReminderStatus = (id: number, enabled: boolean) =>
  data(apiClient.patch<ApiResponse<void>>(`/notification-rules/${id}/status`, null, { params: { enabled } }))
export const removeReminder = (id: number) => data(apiClient.delete<ApiResponse<void>>(`/notification-rules/${id}`))
export const sendNow = (payload: ReminderPayload) => data(apiClient.post<ApiResponse<number>>('/notification-rules/send-now', payload))
export const getInbox = () => data(apiClient.get<ApiResponse<InboxItem[]>>('/notifications'))
export const markRead = (id: number) => data(apiClient.patch<ApiResponse<void>>(`/notifications/${id}/read`))
export const getDevices = () => data(apiClient.get<ApiResponse<Device[]>>('/push/subscriptions'))
export const getVapidKey = () => data(apiClient.get<ApiResponse<string>>('/push/vapid-public-key'))
export const registerSubscription = (payload: { endpoint: string; p256dh: string; auth: string; deviceName: string }) =>
  data(apiClient.post<ApiResponse<string>>('/push/subscriptions', payload))
export const removeDevice = (id: number) => data(apiClient.delete<ApiResponse<void>>(`/push/subscriptions/${id}`))
export const testPush = () => data(apiClient.post<ApiResponse<number>>('/push/test'))

