import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { mcpScopes, advertisedMcpScopes, defaultMcpReadScopes } from '../src/api/mcpScopes.ts'

test('owner grant UI matches backend supported scopes', () => {
 const java = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/mcp/McpOAuthMetadataController.java', import.meta.url), 'utf8')
 const declaration = java.match(/SCOPES = List\.of\(([\s\S]*?)\);/)
 assert.ok(declaration)
 const backend = [...declaration[1].matchAll(/"(prp\.[a-z.]+)"/g)].map(m => m[1]).sort()
 const frontend = mcpScopes.map(scope => scope.value)
 assert.equal(new Set(frontend).size, frontend.length)
 assert.deepEqual([...frontend].sort(), backend)
 assert.ok(frontend.includes('prp.write.update'))
 assert.ok(frontend.includes('prp.write.delete'))
 assert.ok(mcpScopes.every(scope => scope.label.trim()))
})
test('write scopes are not selected by default', () => {
 const view = readFileSync(new URL('../src/views/McpClientsView.vue', import.meta.url), 'utf8')
 assert.match(view, /const scopes = ref<string\[\]>\(\[\]\)/)
 assert.deepEqual(defaultMcpReadScopes(advertisedMcpScopes(['prp.wellness.read','prp.wellness.write.create'])), ['prp.wellness.read'])
 assert.throws(() => advertisedMcpScopes(['prp.wellness.read','unknown']))
 assert.throws(() => advertisedMcpScopes(['prp.wellness.read','prp.wellness.read']))
 assert.deepEqual(defaultMcpReadScopes([]), [])
 assert.deepEqual(defaultMcpReadScopes(advertisedMcpScopes(['prp.tasks.read','prp.wellness.read','prp.records.read','prp.practice.read'])), ['prp.wellness.read'])
 assert.deepEqual(defaultMcpReadScopes(advertisedMcpScopes(['prp.tasks.read'])), ['prp.tasks.read'])
})

test('first-party linking uses discovered read scopes and cannot imply a task grant', () => {
 const view = readFileSync(new URL('../src/views/McpClientsView.vue', import.meta.url), 'utf8')
 const callback = readFileSync(new URL('../src/views/McpOidcCallbackView.vue', import.meta.url), 'utf8')
 // An independent review/video-only realm advertises no task or wellness read.
 // Owner must deliberately select and approve the displayed read scopes.
 assert.deepEqual(defaultMcpReadScopes(advertisedMcpScopes([
   'prp.reviews.read', 'prp.video.read'
 ])), [])
 assert.match(view, /const readableScopeLabels = computed/)
 assert.match(view, /scope\.value\.endsWith\('\.read'\)/)
 assert.match(view, /readableScopeLabels\.join\('、'\)/)
 assert.match(view, /身份绑定本身不会新增数据读取授权/)
 assert.doesNotMatch(view, /批准“读取任务”权限/)
 assert.match(callback, /身份关联不会自动新增读取权限/)
 assert.doesNotMatch(callback, /尝试读取自己的 PRP 任务/)
})
