export function buildApiUrl(baseURL: string, path: string): string {
  if (!baseURL.trim()) throw new Error('API base URL is missing')
  if (!path.startsWith('/')) throw new Error('API path must begin with /')
  return `${baseURL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}
