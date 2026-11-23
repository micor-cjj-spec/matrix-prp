#!/usr/bin/env node
/**
 * Non-authoritative PR release-scope advisory.
 * It cannot permit publication, unlock production, or substitute for runtime evidence.
 * PRP ships a combined backend.jar + web bundle, not isolated module artifacts.
 */
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const KINDS = new Set(['docs', 'tests', 'ui', 'backend', 'shared', 'migration', 'security', 'platform', 'unknown'])
const ALWAYS_REQUIRED = [
  'trusted_main_ci_and_exact_sha',
  'isolated_staging_smoke',
  'owner_release_approval',
  'publication_hold_gate',
  'production_environment_protection',
  'artifact_sha_and_controller_check',
  'production_backup_and_rollback_controls',
  'post_deploy_smoke_and_deployed_sha',
]
const CHECKS = {
  ui: 'real_browser_mobile_pwa_uat',
  backend: 'backend_business_and_tenant_regression',
  shared: 'cross_module_api_and_ui_regression',
  migration: 'isolated_migration_backup_restore_rehearsal',
  security: 'oauth_permissions_and_identity_isolation_review',
  platform: 'deployment_workflow_and_ssh_controller_contract',
  unknown: 'manual_classification_and_owner_review',
}

function isSafePath(path) {
  return typeof path === 'string' && path.length > 0 && path.length <= 512 &&
    /^[A-Za-z0-9._/-]+$/.test(path) && !path.startsWith('/') &&
    path.split('/').every(segment => segment.length && segment !== '.' && segment !== '..')
}

export function classifyPath(path) {
  if (!isSafePath(path)) throw new Error('Unsafe or malformed file path')
  if (path === 'README.md' || path === 'CHANGELOG.md' || path.startsWith('app/docs/') || path.startsWith('docs/')) return 'docs'
  if (path.startsWith('app/backend/src/test/') || path.startsWith('app/mobile/test/') ||
      path.startsWith('app/web/test/') || /(?:\.test\.[cm]?[jt]sx?|\.spec\.[jt]sx?|\/test_[a-z0-9_]+\.py)$/.test(path)) return 'tests'

  if (path.startsWith('app/backend/src/main/resources/db/migration/') ||
      path.startsWith('app/docker/mysql/') ||
      path === 'app/deploy/migration-policy.json') return 'migration'

  if (/(^|\/)(auth|security|oauth|oidc|keycloak|jwt|secrets?|permission|permissions|mcp)(\/|[-_.])/i.test(path) ||
      /(?:[\/-])(token|grant|identity|scope|consent)(?:[\/-]|\.)/i.test(path)) return 'security'

  if (path.startsWith('.github/') || path.startsWith('app/deploy/') ||
      path.startsWith('app/scripts/') || path.startsWith('app/docker/') ||
      /^app\/(backend\/pom\.xml|web\/(package(?:-lock)?\.json|vite\.config\.ts)|mobile\/package(?:-lock)?\.json)$/.test(path) ||
      path.startsWith('app/backend/.mvn/')) return 'platform'

  if (path.startsWith('app/config/') ||
      path.startsWith('app/backend/src/main/java/com/matrix/prp/common/') ||
      path.startsWith('app/backend/src/main/java/com/matrix/prp/config/') ||
      path.startsWith('app/web/src/api/') || path.startsWith('app/web/src/router/') ||
      path.startsWith('app/web/src/layouts/') || path.startsWith('app/mobile/src/api/') ||
      path.startsWith('app/backend/src/main/resources/')) return 'shared'

  if (path.startsWith('app/backend/src/main/')) return 'backend'
  if (path.startsWith('app/web/src/') || path.startsWith('app/web/public/') ||
      path === 'app/web/index.html' || path.startsWith('app/mobile/src/') ||
      path.startsWith('app/mobile/pages/') || path.startsWith('app/mobile/public/')) return 'ui'

  return 'unknown'
}

export function assessReleaseScope(impact) {
  if (!impact || typeof impact !== 'object' || Array.isArray(impact) ||
      !Array.isArray(impact.changedFiles) || !Array.isArray(impact.affectedFeatures) ||
      !Array.isArray(impact.crossCutting) || !Array.isArray(impact.unclassifiedFiles) ||
      typeof impact.globalEffect !== 'boolean') throw new Error('Incomplete feature-impact report')

  const files = impact.changedFiles
  const normalized = [...new Set(files)]
  if (!files.every(isSafePath) || normalized.length !== files.length) throw new Error('Untrusted changed-file list')
  if (!impact.unclassifiedFiles.every(isSafePath) ||
      !impact.unclassifiedFiles.every(path => files.includes(path))) throw new Error('Invalid unclassified paths')
  if (!impact.affectedFeatures.every(f => f && typeof f.code === 'string' && /^[a-z0-9-]+$/.test(f.code))) {
    throw new Error('Invalid affected feature')
  }

  const changes = files.map(path => ({path, kind: classifyPath(path)}))
  const kinds = new Set(changes.map(c => c.kind))
  if (impact.unclassifiedFiles.length) kinds.add('unknown')
  if (![...kinds].every(k => KINDS.has(k))) throw new Error('Invalid change kind')

  const runtimeKinds = [...kinds].filter(k => k !== 'docs' && k !== 'tests')
  const runtimeTouched = runtimeKinds.length > 0
  const sharedImpact = impact.globalEffect || impact.crossCutting.length > 0 ||
    kinds.has('shared') || changes.some(c => /^(app\/web\/src\/(styles|layouts|router)\/|app\/web\/index\.html)/.test(c.path))

  const risk = !files.length || kinds.has('unknown') ? 'UNCLASSIFIED' :
    !runtimeTouched ? 'NO_RUNTIME_CHANGE' :
    ['security','migration','platform'].some(k => kinds.has(k)) ? 'HIGH_REVIEW' :
    sharedImpact ? 'SHARED_REVIEW' : 'FEATURE_REVIEW'

  const specialized = new Set()
  for (const kind of kinds) if (CHECKS[kind]) specialized.add(CHECKS[kind])
  if (sharedImpact) specialized.add(CHECKS.shared)
  if (runtimeTouched) specialized.add('candidate_specific_impact_and_dependency_review')

  const affected = [...new Set(impact.affectedFeatures.map(f => f.code))].sort()
  return {
    schema_version: 1,
    analysis_type: 'non_authoritative_pull_request_advisory',
    artifact_topology: 'monolithic_backend_jar_plus_web',
    risk,
    release_action: risk === 'NO_RUNTIME_CHANGE' ? 'NO_APPLICATION_RELEASE_NEEDED' : 'MANUAL_RELEASE_REVIEW_REQUIRED',
    affected_feature_codes: affected,
    shared_impact: sharedImpact,
    changes,
    required_release_controls: runtimeTouched ? ALWAYS_REQUIRED : [],
    suggested_extra_evidence: [...specialized].sort(),
    findings: [
      ...(kinds.has('unknown') || !files.length ? ['Unknown or empty diff: never infer release safety.'] : []),
      ...(sharedImpact ? ['Shared code/layout changed: affected modules cannot be assessed in isolation.'] : []),
      'File impact is advisory; a release packages all code at the selected commit.',
      'A module-specific UAT exemption cannot override global publication hold, main CI, backup, production approval or controller safeguards.',
    ],
    deployment_authorized: false,
    production_state_verified: false,
  }
}

const safeMarkdown = s => String(s).replace(/[|<>\r\n\\`]/g, ch => ({
  '|': '\\|', '<': '&lt;', '>': '&gt;', '\r': ' ', '\n': ' ', '\\': '\\\\', '`': '\\`',
})[ch])

export function toMarkdown(report) {
  const out = [
    '## PRP · 发布范围与专项验收建议（仅预检）', '',
    '**注意：这不是生产发布批准，也不是线上版本证明。**', '',
    '| 项目 | 检查结果 |', '| --- | --- |',
    '| 候选风险 | ' + report.risk + ' |',
    '| 发布建议 | ' + report.release_action + ' |',
    '| 已识别功能 | ' + (report.affected_feature_codes.map(safeMarkdown).join(', ') || '未识别') + ' |',
    '| 跨模块影响 | ' + (report.shared_impact ? '是' : '未静态发现（需人工审查）') + ' |',
    '| 部署授权 | **否** |', '',
    '### 变更分类', '',
    '| 文件 | 分类 |', '| --- | --- |',
  ]
  for (const c of report.changes) out.push('| ' + safeMarkdown(c.path) + ' | ' + safeMarkdown(c.kind) + ' |')
  if (!report.changes.length) out.push('| 无可核实的变更文件 | unknown |')
  out.push('', '### 不可跳过的发布控制', '')
  for (const gate of report.required_release_controls) out.push('- ' + safeMarkdown(gate))
  if (!report.required_release_controls.length) out.push('- 本次仅识别文档/测试变更，无应用发布需求。')
  out.push('', '### 建议补充的专项验收', '')
  for (const gate of report.suggested_extra_evidence) out.push('- ' + safeMarkdown(gate))
  if (!report.suggested_extra_evidence.length) out.push('- 无专项业务验收建议。')
  out.push('', '### 边界', '')
  for (const line of report.findings) out.push('- ' + safeMarkdown(line))
  return out.join('\n') + '\n'
}

export function runCli(argv) {
  const args = {}
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--impact', '--json', '--out'].includes(argv[i]) || !argv[i + 1] ||
        argv[i+1].startsWith('--')) throw new Error('Expected --impact, --json and --out paths')
    args[argv[i].slice(2)] = argv[i + 1]
  }
  if (Object.keys(args).length !== 3) throw new Error('Expected --impact, --json and --out')
  const impact = JSON.parse(readFileSync(resolve(args.impact), 'utf8'))
  const report = assessReleaseScope(impact)
  writeFileSync(resolve(args.json), JSON.stringify(report, null, 2) + '\n')
  writeFileSync(resolve(args.out), toMarkdown(report))
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, toMarkdown(report))
  process.stdout.write(report.risk + ' (advisory; production not authorized)\n')
  return report
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { runCli(process.argv.slice(2)) }
  catch (err) { console.error('Release-scope analysis rejected: ' + err.message); process.exitCode = 1 }
}
