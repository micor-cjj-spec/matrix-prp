import { readFileSync, readdirSync } from 'node:fs'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const roots = [
  'app/backend/src/main',
  'app/web/src',
  'app/mobile/src',
  'app/docker/mysql/init',
]
const textExtensions = new Set(['.java', '.sql', '.yml', '.yaml', '.ts', '.js', '.vue', '.json', '.xml', '.md'])
// Typical signs of UTF-8 bytes decoded as Latin-1 / Windows-1252.
// The escape sequences keep this checker from matching its own source.
const mojibake = /(?:[\u00c2\u00c3\u00e4-\u00e9][\u0080-\u00bf\u0152\u0160\u0178\u2018-\u2022\u2030-\u203a]|\uFFFD)/u
const decoder = new TextDecoder('utf-8', { fatal: true })
let count = 0
const failures = []

function scan(path) {
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const full = join(path, entry.name)
    if (entry.isDirectory()) scan(full)
    else if (entry.isFile() && textExtensions.has(extname(entry.name))) {
      count++
      const bytes = readFileSync(full)
      const relative = full.slice(root.length + 1)
      try {
        const content = decoder.decode(bytes)
        const lines = content.split(/\r?\n/)
        lines.forEach((line, index) => {
          if (mojibake.test(line)) failures.push(relative + ':' + (index + 1))
        })
      } catch {
        failures.push(relative + ': invalid UTF-8')
      }
    }
  }
}
for (const dir of roots) scan(join(root, dir))
if (failures.length) {
  console.error('Potential source-text encoding defects (inspect; never auto-convert):')
  failures.forEach(line => console.error('  ' + line))
  process.exitCode = 1
} else {
  console.log('PASS: ' + count + ' application text files are valid UTF-8 with no common mojibake signatures.')
}
