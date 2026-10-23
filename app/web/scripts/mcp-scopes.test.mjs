import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { mcpScopes } from '../src/api/mcpScopes.ts'

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
 assert.match(view, /const scopes = ref<string\[\]>\(\['prp\.tasks\.read'\]\)/)
})
