import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

const base = process.argv[2] || '/prp/'
assert.match(base, /^\/(?:[a-zA-Z0-9_-]+\/)*$/, 'Expected a root-relative base path ending with /')

const dist = resolve('dist')
const html = readFileSync(resolve(dist, 'index.html'), 'utf8')
const manifest = JSON.parse(readFileSync(resolve(dist, 'manifest.webmanifest'), 'utf8'))
const worker = readFileSync(resolve(dist, 'sw.js'), 'utf8')

assert.ok(html.includes(base + 'assets/'), 'index.html must load built assets from ' + base + 'assets/')
assert.ok(html.includes('href="' + base + 'manifest.webmanifest"'), 'Manifest link must use public base')
assert.ok(html.includes('href="' + base + 'icon.svg"'), 'Icon link must use public base')
assert.equal(manifest.start_url, './', 'PWA must start relative to its manifest location')
assert.equal(manifest.scope, './', 'PWA scope must be relative to its manifest location')
assert.equal(manifest.id, './', 'PWA identity must be relative to manifest location')
assert.ok(manifest.icons?.every((icon) => icon.src.startsWith('./')), 'Manifest icons must be relative')
assert.ok(worker.includes('self.registration.scope'), 'Worker notification navigation must use registered scope')
assert.ok(existsSync(resolve(dist, 'icon.svg')), 'PWA icon must be present in dist')

console.log('PWA build paths verified for ' + base)
