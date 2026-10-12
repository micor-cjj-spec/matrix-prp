import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const app = join(dirname(fileURLToPath(import.meta.url)), '..')
const file = path => readFileSync(join(app, path), 'utf8')
const router = file('web/src/router/index.ts')
const layout = file('web/src/layouts/AppLayout.vue')
const css = file('web/src/styles/main.css')
const catalog = file('web/src/utils/appCatalog.ts')
const registry = JSON.parse(file('config/feature-registry.json'))

test('exactly four first-level destinations are present', () => {
  const tabs = [...layout.matchAll(/\{ code: '(home|apps|chat|me)', label: '[^']+', to: '([^']+)'/g)]
  assert.deepEqual(tabs.map(match => match[1]), ['home', 'apps', 'chat', 'me'])
  assert.deepEqual(tabs.map(match => match[2]), ['/', '/apps', '/chat', '/me'])
  assert.match(css, /grid-template-columns:repeat\(4,minmax\(0,1fr\)\);position:fixed/)
  assert.match(css, /env\(safe-area-inset-bottom/)
})

test('authenticated new routes and original business routes remain reachable', () => {
  const routes = [...router.matchAll(/path:\s*'([^']+)'/g)].map(match => match[1])
  for (const path of ['/apps','/chat','/me','/me/settings','/me/guide','/me/about']) {
    assert.ok(routes.includes(path), 'Missing shell route ' + path)
    const definition = router.slice(router.indexOf("path: '" + path + "'"))
    assert.match(definition.slice(0, 250), /requiresAuth: true/)
  }
  for (const entry of registry.modules) {
    if (entry.webRoute) assert.ok(routes.includes(entry.webRoute), 'Removed business route ' + entry.webRoute)
  }
})

test('application menu derives entries from registry and hides admin-only tools', () => {
  assert.match(catalog, /import \{ domains, features \} from '@\/generated\/features'/)
  assert.match(catalog, /f\.visibility !== 'admin' \|\| isAdmin/)
  assert.match(catalog, /groups\[f\.code\] \?\? 'other'/)
  assert.match(file('web/src/views/AppsView.vue'), /toggleFavorite\(item\.code\)/)
  assert.match(file('web/src/views/ChatView.vue'), /尚未集成完整的 Matrix AI Orchestrator/)
})

test('shell pages are explicitly separated from registered business routes', () => {
  const check = file('scripts/sync-features.mjs')
  for (const path of ['/apps','/chat','/me','/me/settings','/me/guide','/me/about'])
    assert.ok(check.includes("'" + path + "'"), 'Missing exempt shell route ' + path)
  assert.match(check, /!shellRoutes\.has\(path\)/)
})
