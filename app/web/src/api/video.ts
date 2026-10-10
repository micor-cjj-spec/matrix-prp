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
export interface UploadSession { uploadId: string; chunkSize: number; partCount: number }
export interface VideoPlayback { url: string; expiresAtEpochSeconds: number }

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
  return (await apiClient.get<ApiResponse<VideoPlayback>>(`/video/items/${id}/playback`)).data.data
}
export async function saveVideoProgress(id: number, positionSeconds: number, durationSeconds: number) {
  await apiClient.put(`/video/items/${id}/progress`, { positionSeconds, durationSeconds })
}

/** Re-select the same file to resume an interrupted upload. The server validates the user. */
export async function uploadVideo(file: File, folderId: number | null, onProgress: (percent: number) => void) {
  if (!file.name.toLowerCase().endsWith('.mp4')) throw new Error('目前仅支持 MP4')
  const key = `matrix-prp-upload:${folderId ?? 'root'}:${file.name}:${file.size}:${file.lastModified}`
  let session: UploadSession
  const cached = localStorage.getItem(key)
  if (cached) {
    session = JSON.parse(cached) as UploadSession
  } else {
    session = await startUpload(file.name, folderId, file.size)
    localStorage.setItem(key, JSON.stringify(session))
  }
  for (let part = 0; part < session.partCount; part++) {
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
    onProgress(Math.round((part + 1) / session.partCount * 100))
  }
  const result = await completeUpload(session.uploadId)
  localStorage.removeItem(key)
  return result
}
