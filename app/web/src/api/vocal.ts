import { apiClient, type ApiResponse } from './client'

export interface VocalExercise {
  code: string
  name: string
  description: string
  minutes: number
  targetHz: number
}
export interface PitchPoint { time: number; hz: number }
export interface VocalMetrics {
  voicedSamples: number
  medianHz: number | null
  stabilityCents: number | null
  targetHitPercent: number | null
  guidance: string
}
export interface VocalTake {
  id: number
  exerciseCode: string
  note: string
  durationSeconds: number
  sizeBytes: number
  analysis: VocalMetrics
  aiFeedback: string | null
  aiStatus: string
  createdAt: string
}
export const vocalApi = {
  exercises: async () =>
    (await apiClient.get<ApiResponse<VocalExercise[]>>('/vocal/exercises')).data.data,
  takes: async () =>
    (await apiClient.get<ApiResponse<VocalTake[]>>('/vocal/takes')).data.data,
  upload: async (audio: Blob, exerciseCode: string, note: string, durationSeconds: number, points: PitchPoint[]) => {
    const body = new FormData()
    const mime = audio.type.split(';')[0]
    const suffix = mime === 'audio/mp4' || mime === 'video/mp4' ? 'm4a'
      : mime === 'audio/ogg' ? 'ogg' : mime.includes('wav') ? 'wav' : 'webm'
    body.append('file', audio, 'practice.' + suffix)
    body.append('exerciseCode', exerciseCode)
    body.append('note', note)
    body.append('durationSeconds', String(durationSeconds))
    body.append('samples', JSON.stringify(points))
    return (await apiClient.post<ApiResponse<VocalTake>>('/vocal/takes', body, { timeout: 90000 })).data.data
  },
  audio: async (id: number) =>
    (await apiClient.get<Blob>('/vocal/takes/' + id + '/audio',
      { responseType: 'blob', timeout: 60000 })).data,
  coach: async (id: number) =>
    (await apiClient.post<ApiResponse<VocalTake>>('/vocal/takes/' + id + '/coach', {},
      { timeout: 160000 })).data.data,
  remove: async (id: number) => { await apiClient.delete('/vocal/takes/' + id) },
}
