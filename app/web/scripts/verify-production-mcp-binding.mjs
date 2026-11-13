import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

const endpoint = 'https://auth.micor.top/realms/prp-mcp-prod/protocol/openid-connect/auth'
const files = (await readdir('dist/assets')).filter(name => name.endsWith('.js'))
const bundles = await Promise.all(files.map(name => readFile(join('dist/assets', name), 'utf8')))
if (!bundles.some(text => text.includes(endpoint))) throw new Error('Production OAuth endpoint missing from built frontend')
if (bundles.some(text => text.includes('auth-test.micor.top') || text.includes('prp-test.micor.top')))
  throw new Error('Staging OAuth host found in production frontend')
console.log('PRODUCTION_FRONTEND_OAUTH_PIN_VERIFIED_NOT_DEPLOYED')
