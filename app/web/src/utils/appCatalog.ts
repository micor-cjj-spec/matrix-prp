import { domains, features } from '@/generated/features'

export type AppGroup = 'learning' | 'health' | 'life' | 'finance' | 'other'
export interface AppEntry {
  code: string
  name: string
  route: string
  group: AppGroup
  kind: 'domain' | 'feature'
}
export const groupNames: Record<AppGroup, string> = {
  learning: '学习', health: '健康', life: '生活', finance: '财务', other: '更多工具',
}
export const groupOrder: AppGroup[] = ['learning', 'health', 'life', 'finance', 'other']

// This mapping only classifies existing modules. New registered features still appear
// automatically under "更多工具" if no classification has been assigned yet.
const groups: Record<string, AppGroup> = {
  learning: 'learning', videos: 'learning', practice: 'learning', knowledge: 'learning',
  wellness: 'health',
  life: 'life', tasks: 'life', records: 'life', reviews: 'life', tags: 'life',
  finance: 'finance',
}

export function getAppEntries(isAdmin: boolean): AppEntry[] {
  const landing: AppEntry[] = domains
    .filter(d => d.enabled && d.status === 'landing' && d.webRoute && d.visibleInNav)
    .map(d => ({ code: d.code, name: d.name, route: d.webRoute!, group: groups[d.code] ?? 'other', kind: 'domain' }))
  const tools: AppEntry[] = features
    .filter(f => f.enabled && f.visibleInNav && f.webRoute
      && f.code !== 'dashboard' && f.code !== 'notifications'
      && (f.visibility !== 'admin' || isAdmin))
    .map(f => ({ code: f.code, name: f.name, route: f.webRoute, group: groups[f.code] ?? 'other', kind: 'feature' }))
  return [...landing, ...tools]
}
