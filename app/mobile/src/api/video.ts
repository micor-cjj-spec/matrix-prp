import { request } from './client'

export interface VideoFolder {
  id: number
  parentId: number | null
  name: string
  sortOrder: number
}
export interface VideoItem {
  id: number
  folderId: number | null
  title: string
  sizeBytes: number
  createdAt: string
  positionSeconds: number
}
export interface VideoPlayback { url: string; expiresAtEpochSeconds: number }

export async function listFolders() {
  return request<VideoFolder[]>({ method: 'GET', url: '/video/folders' })
}
export async function listVideos(folderId: number | null) {
  return request<VideoItem[]>({
    method: 'GET',
    url: folderId == null ? '/video/items' : `/video/items?folderId=${folderId}`,
  })
}
export async function playback(id: number) {
  return request<VideoPlayback>({ method: 'GET', url: `/video/items/${id}/playback` })
}
export async function saveProgress(id: number, positionSeconds: number, durationSeconds: number) {
  return request<VideoItem>({
    method: 'PUT',
    url: `/video/items/${id}/progress`,
    data: { positionSeconds, durationSeconds },
  })
}
