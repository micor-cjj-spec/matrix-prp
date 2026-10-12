import { apiClient, type ApiResponse } from './client'
import { getStoredToken } from '@/utils/token'

export interface VideoFolder { id: number; parentId: number | null; name: string; sortOrder: number }
export interface VideoItem {
  id: number
  folderId: number | null
  title: string
  sizeBytes: number
  createdAt: string
  positionSeconds: number
}
export interface StorageUsage { fileCount: number; bytesUsed: number; quotaBytes: number }
export interface UploadSession { uploadId: string; chunkSize: number; partCount: number }
export interface UploadState extends UploadSession { state: string; receivedParts: number[] }
export interface VideoPlayback { url: string; expiresAtEpochSeconds: number }

export async function getStorageUsage() {
  return (await apiClient.get<ApiResponse<StorageUsage>>('/video/storage/usage')).data.data
}
export async function getFolders() {
  return (await apiClient.get<ApiResponse<VideoFolder[]>>('/video/folders')).data.data
}
export async function createFolder(name: string, parentId: number | null) {
  return (await apiClient.post<ApiResponse<VideoFolder>>('/video/folders', { name, parentId })).data.data
}
export async function renameFolder(id: number, name: string) {
  return (await apiClient.put<ApiResponse<VideoFolder>>(`/video/folders/${id}`, { name })).data.data
}
export async function deleteFolder(id: number) {
  await apiClient.delete(`/video/folders/${id}`)
}
export async function getVideos(folderId: number | null) {
  return (await apiClient.get<ApiResponse<VideoItem[]>>('/video/items', {
    params: folderId == null ? {} : { folderId },
  })).data.data
}
export async function updateVideo(id: number, title: string, folderId: number | null) {
  return (await apiClient.put<ApiResponse<VideoItem>>(`/video/items/${id}`, { title, folderId })).data.data
}
export async function deleteVideo(id: number) {
  await apiClient.delete(`/video/items/${id}`)
}
export async function startUpload(title: string, folderId: number | null, sizeBytes: number) {
  return (await apiClient.post<ApiResponse<UploadSession>>('/video/uploads', {
    title, folderId, sizeBytes,
  })).data.data
}
export async function getUploadState(id: string) {
  return (await apiClient.get<ApiResponse<UploadState>>(`/video/uploads/${id}`)).data.data
}
export async function uploadPart(id: string, number: number, chunk: Blob) {
  await apiClient.put(`/video/uploads/${id}/parts/${number}`, chunk, {
    headers: { 'Content-Type': 'application/octet-stream' },
    timeout: 180_000,
  })
}
export async function completeUpload(id: string) {
  return (await apiClient.post<ApiResponse<VideoItem>>(`/video/uploads/${id}/complete`)).data.data
}
export async function getPlayback(id: number) {
  const playback = (await apiClient.get<ApiResponse<VideoPlayback>>(`/video/items/${id}/playback`)).data.data
  const apiBase = (import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`).replace(/\/$/, '')
  return { ...playback, url: playback.url.startsWith('/api/') ? `${apiBase}${playback.url.slice(4)}` : playback.url }
}
export async function saveVideoProgress(id: number, positionSeconds: number, durationSeconds: number) {
  await apiClient.put(`/video/items/${id}/progress`, { positionSeconds, durationSeconds })
}

/** Re-select the same file to resume an interrupted upload. The server validates the user. */
export async function uploadVideo(file: File, folderId: number | null, onProgress: (percent: number) => void) {
  if (!file.name.toLowerCase().endsWith('.mp4')) throw new Error('目前仅支持 MP4')
  const key = `matrix-prp-upload:${folderId ?? 'root'}:${file.name}:${file.size}:${file.lastModified}`
  let session: UploadSession
  let received = new Set<number>()
  const cached = localStorage.getItem(key)
  if (cached) {
    try {
      session = JSON.parse(cached) as UploadSession
      const state = await getUploadState(session.uploadId)
      if (state.state === 'COMPLETE') {
        const result = await completeUpload(session.uploadId)
        localStorage.removeItem(key)
        return result
      }
      received = new Set(state.receivedParts)
    } catch {
      session = await startUpload(file.name, folderId, file.size)
      localStorage.setItem(key, JSON.stringify(session))
    }
  } else {
    session = await startUpload(file.name, folderId, file.size)
    localStorage.setItem(key, JSON.stringify(session))
  }
  onProgress(Math.round(received.size / session.partCount * 100))
  for (let part = 0; part < session.partCount; part++) {
    if (received.has(part)) continue
    const start = part * session.chunkSize
    const chunk = file.slice(start, Math.min(start + session.chunkSize, file.size))
    let lastError: unknown
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await uploadPart(session.uploadId, part, chunk)
        lastError = undefined
        break
      } catch (error) {
        lastError = error
      }
    }
    if (lastError) throw lastError
    received.add(part)
    onProgress(Math.round(received.size / session.partCount * 100))
  }
  const result = await completeUpload(session.uploadId)
  localStorage.removeItem(key)
  return result
}
