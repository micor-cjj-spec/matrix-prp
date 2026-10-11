#!/usr/bin/env node
// Matrix PRP PR impact analysis. Source of mapping: app/config/feature-registry.json
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const tick = String.fromCharCode(96)
const code = value => tick + value + tick
const uniq = values => [...new Set(values)].sort()
const stem = key => ({videos: 'video', notifications: 'notifications'})[key] || key
const cap = key => key[0].toUpperCase() + key.slice(1)
const shared = [
  ['app/backend/src/main/java/com/matrix/prp/auth/', '认证及用户隔离'],
  ['app/backend/src/main/java/com/matrix/prp/config/', '后端公共配置'],
  ['app/backend/src/main/java/com/matrix/prp/common/', '公共代码'],
  ['app/backend/src/main/java/com/matrix/prp/modules/', '模块公共接口'],
  ['app/web/src/api/client.ts', 'Web HTTP 客户端'],
  ['app/mobile/src/api/client.ts', 'Mobile HTTP 客户端'],
  ['app/web/src/router/', '路由定义'],
  ['app/config/feature-registry.json', '功能注册表'],
  ['app/backend/src/main/resources/feature-registry.json', '后端功能注册表'],
  ['app/web/src/generated/features.ts', '前端功能注册表'],
  ['app/docker/mysql/init/001-schema.sql', '数据库基础表'],
  ['app/docker/mysql/init/002-auth.sql', '认证数据库表'],
]
const infrastructure = ['app/scripts/', 'app/docker/', 'app/docs/', '.github/',
  'app/web/package.json', 'app/mobile/package.json', 'app/backend/pom.xml',
  'app/web/vite.config.ts', 'app/web/src/layouts/', 'app/web/src/styles/',
  'app/mobile/src/styles/', 'app/web/public/', 'app/mobile/public/',
  'app/backend/src/main/resources/']

export function validateRegistry(modules, fileExists = p => existsSync(join(root, p))) {
  const errors = []
  const codes = new Set()
  for (const m of modules.filter(x => x.type === 'feature')) {
    if (codes.has(m.code)) errors.push('Duplicate feature: ' + m.code)
    codes.add(m.code)
    if (!m.impact || !Array.isArray(m.impact.apiPrefixes) ||
        !Array.isArray(m.impact.tests) || !Array.isArray(m.impact.docs)) {
      errors.push('Missing impact mapping: ' + m.code)
      continue
    }
    if (!m.impact.apiPrefixes.length ||
        !m.impact.apiPrefixes.every(x => /^\/api\/[a-z0-9/-]+$/.test(x))) {
      errors.push('Invalid API prefixes: ' + m.code)
    }
    if (!m.impact.tests.length || !m.impact.docs.length) errors.push('Empty test/doc map: ' + m.code)
    for (const path of [...m.impact.tests, ...m.impact.docs]) {
      if (typeof path !== 'string' || path.includes('..') || !fileExists(path))
        errors.push('Mapped file missing: ' + m.code + ': ' + path)
    }
  }
  return errors
}

export function analyzeChangedFiles(files, modules) {
  const changedFiles = uniq(files.map(p => p.replaceAll('\\', '/').replace(/^\.\//, '')).filter(Boolean))
  const features = modules.filter(m => m.type === 'feature')
  const found = new Map()
  const unclassifiedFiles = []
  const crossCutting = []
  const infrastructureChanges = []
  let globalEffect = false
  const mark = (m, reason) => {
    const item = found.get(m.code) || {code: m.code, name: m.name, reasons: []}
    item.reasons.push(reason)
    found.set(m.code, item)
  }
  for (const path of changedFiles) {
    let classified = false
    const sharedReason = shared.find(([pattern]) => path === pattern || path.startsWith(pattern))
    if (sharedReason) {
      globalEffect = true
      classified = true
      crossCutting.push({path, reason: sharedReason[1]})
    }
    for (const m of features) {
      const backend = 'app/backend/src/main/java/com/matrix/prp/' + m.backendPackage + '/'
      const webView = 'app/web/src/views/' + cap(m.code) + 'View.vue'
      const webApi = 'app/web/src/api/' + stem(m.code) + '.ts'
      const mobileApi = 'app/mobile/src/api/' + stem(m.code) + '.ts'
      const mobile = m.mobileRoute ? 'app/mobile/src/' + m.mobileRoute.replace(/\/index$/, '') + '/' : null
      const impact = m.impact || {tests: [], docs: []}
      const checks = [
        [path.startsWith(backend), '后端业务'],
        [path === webView, 'Web 页面'],
        [path === webApi, 'Web API'],
        [path === mobileApi, 'Mobile API'],
        [mobile !== null && path.startsWith(mobile), 'Mobile 页面'],
        [impact.tests.includes(path), '关联测试'],
        [impact.docs.includes(path), '关联文档'],
        [m.code === 'videos' && path === 'app/docker/mysql/init/003-video-library.sql', '视频数据表'],
        [m.code === 'notifications' && path === 'app/docker/mysql/init/004-notification-center.sql', '通知数据表'],
      ]
      for (const [matched, source] of checks) {
        if (matched) {
          classified = true
          mark(m, source + ': ' + path)
        }
      }
    }
    if (infrastructure.some(prefix => path === prefix || path.startsWith(prefix))) {
      classified = true
      infrastructureChanges.push(path)
    }
    if (!classified) unclassifiedFiles.push(path)
  }
  if (globalEffect) for (const m of features) mark(m, '跨模块变更，需检查兼容性')
  const affectedFeatures = [...found.values()].sort((a,b) => a.code.localeCompare(b.code)).map(v => {
    const m = features.find(f => f.code === v.code)
    return {code:v.code, name:v.name, reasons:uniq(v.reasons),
      apiPrefixes:m.impact?.apiPrefixes || [],
      suggestedTests:m.impact?.tests || [], relevantDocs:m.impact?.docs || []}
  })
  const suggestedCommands = []
  if (affectedFeatures.length || changedFiles.some(p => p.startsWith('app/backend/')))
    suggestedCommands.push('cd app/backend && ./mvnw test')
  if (globalEffect || changedFiles.some(p => p.startsWith('app/web/')))
    suggestedCommands.push('cd app/web && npm run build')
  if (globalEffect || changedFiles.some(p => p.startsWith('app/mobile/')))
    suggestedCommands.push('cd app/mobile && npm run type-check && npm run build:h5')
  if (affectedFeatures.some(f => f.code === 'videos' || f.code === 'notifications') ||
      changedFiles.some(p => p.startsWith('app/docker/mysql/')))
    suggestedCommands.push('CI: MySQL 8.4 集成回归（VideoDatabaseIT / NotificationDatabaseIT）')
  const sensitive = globalEffect || changedFiles.some(p => /\/(auth|security)\//.test(p) || p.startsWith('app/docker/mysql/'))
  const risk = sensitive ? '高' : affectedFeatures.length > 1 || unclassifiedFiles.length ? '中' : '局部'
  return {
    changedFiles, risk, globalEffect, crossCutting, affectedFeatures,
    infrastructureChanges: uniq(infrastructureChanges), unclassifiedFiles,
    suggestedCommands: uniq(suggestedCommands),
    notes: [
      'API 前缀仅作为受影响候选范围，不代表逐条接口均被修改。',
      '测试和文档属于维护建议，需结合实际 diff 审核。',
      '未归类文件不等于没有影响，必须人工确认。',
    ],
  }
}

function sanitize(value) {return String(value).replaceAll('|', '\\|').replaceAll('\n', ' ')}
export function toMarkdown(report) {
  const output = [
    '# Matrix PRP · PR 变更影响报告', '',
    '> 静态文件路径分析：不代表运行时依赖已被完整追踪。', '',
    '**风险：** ' + report.risk + '；**变更文件：** ' + report.changedFiles.length +
      '；**涉及功能：** ' + report.affectedFeatures.length,
    '', '## 受影响功能', '',
    '| 功能 | 命中原因 | API 候选范围 | 建议测试 | 对应文档 |',
    '| --- | --- | --- | --- | --- |',
  ]
  for (const m of report.affectedFeatures) {
    output.push('| ' + sanitize(m.name) + ' (' + code(m.code) + ') | ' +
      m.reasons.map(sanitize).join('；') + ' | ' +
      m.apiPrefixes.map(p => code(p + '/**')).join('、') + ' | ' +
      m.suggestedTests.map(code).join('、') + ' | ' +
      m.relevantDocs.map(code).join('、') + ' |')
  }
  if (!report.affectedFeatures.length) output.push('| 无直接命中 | 仅基础设施或未归类 | 人工确认 | — | — |')
  output.push('', '## 跨模块影响', '')
  if (report.crossCutting.length)
    for (const item of report.crossCutting) output.push('- ' + code(item.path) + '：' + item.reason)
  else output.push('- 无已注册的跨模块入口命中。')
  if (report.infrastructureChanges.length)
    output.push('', '**治理/基础设施变更：** ' + report.infrastructureChanges.map(code).join('、'))
  output.push('', '## 建议验证', '')
  if (report.suggestedCommands.length)
    for (const command of report.suggestedCommands) output.push('- ' + command)
  else output.push('- 依变更选择相关验证。')
  output.push('', '## 未归类文件（需要人工审核）', '')
  if (report.unclassifiedFiles.length)
    for (const path of report.unclassifiedFiles) output.push('- ' + code(path))
  else output.push('- 无。')
  output.push('', '## 报告边界', '')
  for (const note of report.notes) output.push('- ' + note)
  return output.join('\n') + '\n'
}

function parseArguments(argv) {
  const opts = {files: [], base: 'origin/main', head: 'HEAD', out: null, json: null}
  for (let i=0; i<argv.length; i++) {
    const flag = argv[i]
    if (!['--files','--base','--head','--out','--json'].includes(flag)) throw Error('Unknown flag: ' + flag)
    if (i+1 >= argv.length) throw Error('Missing value for: ' + flag)
    const value = argv[++i]
    if (flag === '--files') opts.files.push(value)
    else opts[flag.slice(2)] = value
  }
  return opts
}

export function runCli(argv) {
  const opts = parseArguments(argv)
  const registry = JSON.parse(readFileSync(join(root,'app/config/feature-registry.json'),'utf8'))
  const errors = validateRegistry(registry.modules)
  if (errors.length) throw Error('Registry mapping errors:\n' + errors.join('\n'))
  let files = opts.files
  if (!files.length) {
    const changed = execFileSync('git', ['diff','--name-only','-z','--diff-filter=ACDMRT',
      opts.base + '...' + opts.head], {cwd:root,encoding:'utf8'})
    files = changed.split('\0').filter(Boolean)
  }
  const result = analyzeChangedFiles(files, registry.modules)
  const markdown = toMarkdown(result)
  for (const [path, contents] of [[opts.out, markdown], [opts.json, JSON.stringify(result,null,2)+'\n']]) {
    if (!path) continue
    mkdirSync(dirname(resolve(path)), {recursive:true})
    writeFileSync(path,contents)
  }
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY,markdown)
  process.stdout.write(markdown)
  return result
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {runCli(process.argv.slice(2))}
  catch(error) {console.error('Impact analysis failed: '+error.message); process.exitCode=1}
}
