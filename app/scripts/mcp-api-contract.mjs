#!/usr/bin/env node
// Fail-closed API -> MCP contract check. No network, DB, credentials or production access.
import {existsSync, readFileSync, readdirSync, writeFileSync} from 'node:fs'
import {dirname, join, relative, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const JAVA_ROOT = join(ROOT, 'app/backend/src/main/java/com/matrix/prp')
const BASELINE = 'app/config/mcp-api-baseline.json'
const CONTRACT = 'app/config/mcp-capabilities.json'
const readJson = path => JSON.parse(readFileSync(join(ROOT, path), 'utf8'))
const unique = xs => [...new Set(xs)].sort()
const normalizePath = (a, b = '') => ('/' + a + '/' + b).replace(/\/+/g, '/').replace(/\/$/, '') || '/'

function mappingPaths(args) {
  const value = args.trim()
  if (!value) return ['']
  const named = /(?:^|[,\s])(?:value|path)\s*=\s*(\{[^}]*\}|"[^"]*")/.exec(value)
  const selected = named ? named[1] : /^[{"]/.test(value) ? value : null
  if (!selected) return ['']
  const paths = [...selected.matchAll(/"([^"]*)"/g)].map(x => x[1])
  if (!paths.length || paths.some(x => x && !x.startsWith('/'))) {
    throw Error('Unsupported Spring request mapping path: ' + value)
  }
  return paths
}

export function parseControllerRoutes(source, file) {
  if (!/@RestController\b/.test(source)) return []
  const classAt = source.search(/\bclass\s+[A-Za-z_]\w*/)
  if (classAt < 0) throw Error(file + ': missing controller class')
  const annotations = [...source.matchAll(/@(Request|Get|Post|Put|Patch|Delete)Mapping\b\s*(?:\(([^)]*)\))?/g)]
  const typeMapping = annotations.filter(a => a.index < classAt && a[1] === 'Request').at(-1)
  const base = typeMapping ? mappingPaths(typeMapping[2] || '') : ['']
  const out = []
  for (const a of annotations) {
    if (a.index < classAt) continue
    const args = a[2] || ''
    const verbs = a[1] === 'Request'
      ? [...args.matchAll(/RequestMethod\.(GET|POST|PUT|PATCH|DELETE)/g)].map(x => x[1])
      : [a[1].toUpperCase()]
    if (!verbs.length) throw Error(file + ': @RequestMapping without explicit HTTP method')
    for (const verb of unique(verbs)) for (const prefix of base) for (const path of mappingPaths(args)) {
      const uri = normalizePath(prefix, path)
      out.push({route: verb + ' ' + uri, controller: file})
    }
  }
  return out
}

function javaFiles(dir) {
  return readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const path = join(dir, entry.name)
    return entry.isDirectory() ? javaFiles(path) : entry.isFile() && entry.name.endsWith('.java') ? [path] : []
  })
}

export function discoverRoutes() {
  const out = []
  for (const path of javaFiles(JAVA_ROOT)) {
    const source = readFileSync(path, 'utf8')
    if (!/@RestController\b/.test(source)) continue
    const file = relative(JAVA_ROOT, path).replaceAll('\\', '/')
    out.push(...parseControllerRoutes(source, file))
  }
  return out.sort((a, b) => a.route.localeCompare(b.route) || a.controller.localeCompare(b.controller))
}

function toolRegistry() {
  const found = new Set()
  for (const path of javaFiles(join(JAVA_ROOT, 'mcp'))) {
    const source = readFileSync(path, 'utf8')
    for (const m of source.matchAll(/@McpTool\s*\(\s*name\s*=\s*"([^"]+)"/g)) found.add(m[1])
  }
  const config = readFileSync(join(JAVA_ROOT, 'mcp/McpToolConfiguration.java'), 'utf8')
  const scopes = new Map([...config.matchAll(/Map\.entry\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)/g)]
    .map(m => [m[1], m[2]]))
  const oauth = readFileSync(join(JAVA_ROOT, 'mcp/McpOAuthMetadataController.java'), 'utf8')
  return {tools: found, scopes, oauth}
}

export function audit(routes, baseline, contract, registry, readTest = () => null) {
  const errors = []
  const actual = new Map()
  for (const item of routes) {
    if (actual.has(item.route)) errors.push('Duplicate REST route: ' + item.route)
    actual.set(item.route, item)
  }
  const legacy = new Set()
  for (const [file, entries] of Object.entries(baseline.controllers || {})) {
    if (!Array.isArray(entries)) {errors.push('Invalid baseline entries: ' + file); continue}
    for (const route of entries) {
      if (legacy.has(route)) errors.push('Duplicate frozen baseline: ' + route)
      legacy.add(route)
      if (!actual.has(route)) errors.push('Stale frozen route: ' + route + ' (' + file + ')')
    }
  }
  const classifications = new Map()
  for (const item of contract.routes || []) {
    const {route, status, tool, reason, tests} = item
    if (classifications.has(route)) errors.push('Duplicate MCP mapping: ' + route)
    classifications.set(route, item)
    if (!actual.has(route)) errors.push('Mapping for missing REST route: ' + route)
    if (!['mapped', 'partial', 'excluded'].includes(status)) {
      errors.push('Invalid MCP status for ' + route)
      continue
    }
    if (status === 'excluded') {
      if (tool) errors.push('Excluded route must not name a tool: ' + route)
      if (typeof reason !== 'string' || reason.trim().length < 20)
        errors.push('Exclusion needs a meaningful reason: ' + route)
    } else {
      if (!tool || !registry.tools.has(tool)) errors.push('Unknown MCP tool for ' + route + ': ' + tool)
      if (!registry.scopes.has(tool)) errors.push('Missing required scope registry entry for ' + route)
      const scope = registry.scopes.get(tool)
      if (scope && !registry.oauth.includes('"' + scope + '"')) errors.push('Scope not in OAuth allowlist: ' + scope)
      if (status === 'partial' && (typeof reason !== 'string' || reason.trim().length < 20))
        errors.push('Partial coverage requires a documented limitation: ' + route)
      if (!legacy.has(route)) {
        if (!Array.isArray(tests) || !tests.length) errors.push('New MCP mapping needs tool-call tests: ' + route)
        else for (const test of tests) {
          const source = readTest(test)
          if (!test.startsWith('app/backend/src/test/') || !test.endsWith('.java') || !source || !source.includes(tool))
            errors.push('Missing MCP tool-call test for ' + route + ': ' + test)
        }
      }
    }
  }
  const rows = [...actual.values()].map(item => {
    const entry = classifications.get(item.route)
    let status = entry?.status || (legacy.has(item.route) ? 'legacy-gap' : 'unmapped')
    if (status === 'unmapped') errors.push('New REST route lacks MCP decision: ' + item.route)
    if (!legacy.has(item.route) && status === 'partial')
      errors.push('New REST route cannot ship with partial MCP coverage: ' + item.route)
    return {route: item.route, controller: item.controller, status,
      tool: entry?.tool || null, reason: entry?.reason || null, newRoute: !legacy.has(item.route)}
  }).sort((a, b) => a.route.localeCompare(b.route))
  const counts = Object.fromEntries(['mapped', 'partial', 'excluded', 'legacy-gap', 'unmapped']
    .map(status => [status, rows.filter(row => row.status === status).length]))
  return {total: rows.length, counts, newRoutes: rows.filter(row => row.newRoute).length,
    errors: unique(errors), routes: rows}
}

function moduleSummary(rows) {
  const features = readJson('app/config/feature-registry.json').modules
    .filter(x => x.type === 'feature').flatMap(x => (x.impact?.apiPrefixes || []).map(p => ({code: x.code, prefix: p})))
    .sort((a, b) => b.prefix.length - a.prefix.length)
  const totals = new Map()
  for (const row of rows) {
    const path = row.route.split(' ').slice(1).join(' ')
    const group = features.find(x => path === x.prefix || path.startsWith(x.prefix + '/'))?.code || 'platform'
    if (!totals.has(group)) totals.set(group, {module: group, total: 0, mapped: 0, partial: 0, excluded: 0, 'legacy-gap': 0, unmapped: 0})
    const item = totals.get(group)
    item.total++; item[row.status]++
  }
  return [...totals.values()].sort((a, b) => a.module.localeCompare(b.module))
}

export function toMarkdown(report) {
  const lines = [
    '# PRP REST / MCP capability audit',
    '',
    'Generated from Spring @RestController mappings in source (static analysis, not a live-server probe).',
    '',
    '| Total | Mapped | Partial | Excluded | Legacy gaps | Unmapped new |',
    '| ---: | ---: | ---: | ---: | ---: | ---: |',
    '| ' + [report.total, report.counts.mapped, report.counts.partial, report.counts.excluded,
       report.counts['legacy-gap'], report.counts.unmapped].join(' | ') + ' |',
    '',
    '## Modules', '',
    '| Module | Total | Mapped | Partial | Excluded | Legacy gaps |',
    '| --- | ---: | ---: | ---: | ---: | ---: |'
  ]
  for (const x of moduleSummary(report.routes))
    lines.push('| ' + [x.module, x.total, x.mapped, x.partial, x.excluded, x['legacy-gap']].join(' | ') + ' |')
  lines.push('', '## Uncovered legacy routes', '')
  for (const x of report.routes.filter(x => x.status === 'legacy-gap'))
    lines.push('- ' + x.route + ' (' + x.controller + ')')
  lines.push('', '## Gate violations', '')
  if (!report.errors.length) lines.push('None')
  else for (const error of report.errors) lines.push('- ' + error)
  return lines.join('\n') + '\n'
}

function run() {
  const baseline = readJson(BASELINE)
  const contract = readJson(CONTRACT)
  const readTest = test => {
    if (!/^app\/backend\/src\/test\/[A-Za-z0-9_./-]+\.java$/.test(test)) return null
    const path = join(ROOT, test)
    return existsSync(path) ? readFileSync(path, 'utf8') : null
  }
  const report = audit(discoverRoutes(), baseline, contract, toolRegistry(), readTest)
  const args = process.argv.slice(2)
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--out' && args[i + 1]) writeFileSync(args[++i], toMarkdown(report))
    else if (args[i] === '--json' && args[i + 1]) writeFileSync(args[++i], JSON.stringify(report, null, 2) + '\n')
    else throw Error('Expected --out <file> or --json <file>')
  }
  console.log('MCP API contract: ' + JSON.stringify({total: report.total, counts: report.counts,
    newRoutes: report.newRoutes, violations: report.errors.length}))
  if (report.errors.length) {
    console.error(report.errors.join('\n'))
    process.exitCode = 1
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) run()
