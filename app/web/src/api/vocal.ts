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
export interface VocalSong {
  id: number
  title: string
  artist: string
  originalKey: string
  status: 'PLANNED' | 'LEARNING' | 'MASTERED'
  note: string
  sectionCount: number
  createdAt: string
  updatedAt: string
}
export interface VocalSongRequest {
  title: string
  artist: string
  originalKey: string
  status: VocalSong['status']
  note: string
}
export interface VocalSection {
  id: number
  songId: number
  title: string
  startMarker: string
  endMarker: string
  focus: string
  sortOrder: number
  createdAt: string
  updatedAt: string
}
export interface VocalSectionRequest {
  title: string
  startMarker: string
  endMarker: string
  focus: string
  sortOrder: number
}
export interface VocalLesson {
  id: number
  lessonDate: string
  teacherName: string
  summary: string
  feedback: string
  assignmentCount: number
  createdAt: string
  updatedAt: string
}
export interface VocalLessonRequest {
  lessonDate: string
  teacherName: string
  summary: string
  feedback: string
}
export interface VocalAssignment {
  id: number
  lessonId: number | null
  songId: number | null
  sectionId: number | null
  title: string
  detail: string
  dueDate: string | null
  status: 'TODO' | 'IN_PROGRESS' | 'DONE'
  completedAt: string | null
  createdAt: string
  updatedAt: string
  songTitle: string | null
  sectionTitle: string | null
}
export interface VocalAssignmentRequest {
  lessonId: number | null
  songId: number | null
  sectionId: number | null
  title: string
  detail: string
  dueDate: string | null
  status: VocalAssignment['status']
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
  songId: number | null
  sectionId: number | null
  songTitle: string | null
  sectionTitle: string | null
}
export const vocalApi = {
  exercises: async () =>
    (await apiClient.get<ApiResponse<VocalExercise[]>>('/vocal/exercises')).data.data,
  takes: async () =>
    (await apiClient.get<ApiResponse<VocalTake[]>>('/vocal/takes')).data.data,
  upload: async (audio: Blob, exerciseCode: string, note: string, durationSeconds: number,
      points: PitchPoint[], songId: number | null = null, sectionId: number | null = null) => {
    const body = new FormData()
    const mime = audio.type.split(';')[0]
    const suffix = mime === 'audio/mp4' || mime === 'video/mp4' ? 'm4a'
      : mime === 'audio/ogg' ? 'ogg' : mime.includes('wav') ? 'wav' : 'webm'
    body.append('file', audio, 'practice.' + suffix)
    body.append('exerciseCode', exerciseCode)
    body.append('note', note)
    body.append('durationSeconds', String(durationSeconds))
    body.append('samples', JSON.stringify(points))
    if (songId !== null) body.append('songId', String(songId))
    if (sectionId !== null) body.append('sectionId', String(sectionId))
    return (await apiClient.post<ApiResponse<VocalTake>>('/vocal/takes', body, { timeout: 90000 })).data.data
  },
  audio: async (id: number) =>
    (await apiClient.get<Blob>('/vocal/takes/' + id + '/audio',
      { responseType: 'blob', timeout: 60000 })).data,
  coach: async (id: number) =>
    (await apiClient.post<ApiResponse<VocalTake>>('/vocal/takes/' + id + '/coach', {},
      { timeout: 160000 })).data.data,
  remove: async (id: number) => { await apiClient.delete('/vocal/takes/' + id) },
  songs: async () =>
    (await apiClient.get<ApiResponse<VocalSong[]>>('/vocal/songs')).data.data,
  saveSong: async (value: VocalSongRequest, id?: number) =>
    (await (id
      ? apiClient.put<ApiResponse<VocalSong>>('/vocal/songs/' + id, value)
      : apiClient.post<ApiResponse<VocalSong>>('/vocal/songs', value))).data.data,
  removeSong: async (id: number) => { await apiClient.delete('/vocal/songs/' + id) },
  sections: async (songId: number) =>
    (await apiClient.get<ApiResponse<VocalSection[]>>('/vocal/songs/' + songId + '/sections')).data.data,
  saveSection: async (songId: number, value: VocalSectionRequest, id?: number) =>
    (await (id
      ? apiClient.put<ApiResponse<VocalSection>>('/vocal/sections/' + id, value)
      : apiClient.post<ApiResponse<VocalSection>>('/vocal/songs/' + songId + '/sections', value))).data.data,
  removeSection: async (id: number) => { await apiClient.delete('/vocal/sections/' + id) },
  lessons: async () =>
    (await apiClient.get<ApiResponse<VocalLesson[]>>('/vocal/lessons')).data.data,
  saveLesson: async (value: VocalLessonRequest, id?: number) =>
    (await (id
      ? apiClient.put<ApiResponse<VocalLesson>>('/vocal/lessons/' + id, value)
      : apiClient.post<ApiResponse<VocalLesson>>('/vocal/lessons', value))).data.data,
  removeLesson: async (id: number) => { await apiClient.delete('/vocal/lessons/' + id) },
  assignments: async () =>
    (await apiClient.get<ApiResponse<VocalAssignment[]>>('/vocal/assignments')).data.data,
  saveAssignment: async (value: VocalAssignmentRequest, id?: number) =>
    (await (id
      ? apiClient.put<ApiResponse<VocalAssignment>>('/vocal/assignments/' + id, value)
      : apiClient.post<ApiResponse<VocalAssignment>>('/vocal/assignments', value))).data.data,
  removeAssignment: async (id: number) => { await apiClient.delete('/vocal/assignments/' + id) },
}
