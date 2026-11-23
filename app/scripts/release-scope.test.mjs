import test from 'node:test'
import assert from 'node:assert/strict'
import {classifyPath, assessReleaseScope, toMarkdown} from './release-scope.mjs'

function impact(files, options = {}) {
  return {
    changedFiles: files,
    affectedFeatures: (options.features || []).map(code => ({code, name: code})),
    crossCutting: options.crossCutting || [],
    unclassifiedFiles: options.unclassifiedFiles || [],
    globalEffect: options.globalEffect || false,
  }
}

test('documentation-only edits do not request an application release', () => {
  const r = assessReleaseScope(impact(['app/docs/technical/deploy-guide.md','README.md']))
  assert.equal(r.risk,'NO_RUNTIME_CHANGE')
  assert.equal(r.release_action,'NO_APPLICATION_RELEASE_NEEDED')
  assert.deepEqual(r.required_release_controls,[])
  assert.equal(r.deployment_authorized,false)
})

test('README reported unclassified by the existing impact tool remains docs-only', () => {
  const r=assessReleaseScope(impact(['README.md'],{unclassifiedFiles:['README.md']}))
  assert.equal(r.risk,'NO_RUNTIME_CHANGE')
  assert.equal(r.release_action,'NO_APPLICATION_RELEASE_NEEDED')
})

test('tests-only changes do not imply a production deploy', () => {
  const r = assessReleaseScope(impact([
    'app/backend/src/test/java/com/matrix/prp/WellnessTest.java',
    'app/scripts/deploy-workflow-contract.test.mjs',
  ]))
  assert.equal(r.risk,'NO_RUNTIME_CHANGE')
  assert.equal(r.production_state_verified,false)
})

test('isolated wellness UI change selects browser UAT but does not add DB-specialist check', () => {
  const r = assessReleaseScope(impact(['app/web/src/views/WellnessView.vue'], {features:['wellness']}))
  assert.equal(r.risk,'FEATURE_REVIEW')
  assert.deepEqual(r.affected_feature_codes,['wellness'])
  assert.ok(r.suggested_extra_evidence.includes('real_browser_mobile_pwa_uat'))
  assert.ok(!r.suggested_extra_evidence.includes('isolated_migration_backup_restore_rehearsal'))
  assert.ok(r.required_release_controls.includes('production_backup_and_rollback_controls'))
  assert.ok(r.required_release_controls.includes('publication_hold_gate'))
})

test('shared layout cannot be treated as only a wellness release', () => {
  const r = assessReleaseScope(impact(['app/web/src/styles/main.css'],{features:['wellness']}))
  assert.equal(r.risk,'SHARED_REVIEW')
  assert.equal(r.shared_impact,true)
  assert.ok(r.suggested_extra_evidence.includes('cross_module_api_and_ui_regression'))
})

test('API client is a shared integration surface', () => {
  const r=assessReleaseScope(impact(['app/web/src/api/wellness.ts']))
  assert.equal(r.shared_impact,true)
  assert.equal(r.risk,'SHARED_REVIEW')
})

test('database migration requires restoration rehearsal and normal global controls', () => {
  const r = assessReleaseScope(impact(['app/backend/src/main/resources/db/migration/V30__wellness.sql']))
  assert.equal(r.risk,'HIGH_REVIEW')
  assert.ok(r.suggested_extra_evidence.includes('isolated_migration_backup_restore_rehearsal'))
  assert.equal(r.deployment_authorized,false)
})

test('OAuth/MCP changes are always flagged for identity review', () => {
  const r=assessReleaseScope(impact(['app/backend/src/main/java/com/matrix/prp/mcp/OidcGrantService.java']))
  assert.equal(r.risk,'HIGH_REVIEW')
  assert.ok(r.suggested_extra_evidence.includes('oauth_permissions_and_identity_isolation_review'))
})

test('deploy workflow changes are high-risk even when no business module matched', () => {
  const r=assessReleaseScope(impact(['.github/workflows/deploy-prp.yml']))
  assert.equal(r.risk,'HIGH_REVIEW')
  assert.ok(r.suggested_extra_evidence.includes('deployment_workflow_and_ssh_controller_contract'))
})

test('unknown paths fail closed and require manual classification', () => {
  const r=assessReleaseScope(impact(['app/new-engine/worker.bin'],{
    unclassifiedFiles:['app/new-engine/worker.bin']
  }))
  assert.equal(r.risk,'UNCLASSIFIED')
  assert.ok(r.suggested_extra_evidence.includes('manual_classification_and_owner_review'))
  assert.equal(r.deployment_authorized,false)
})

test('empty diff cannot imply safe-to-publish state', () => {
  const r=assessReleaseScope(impact([]))
  assert.equal(r.risk,'UNCLASSIFIED')
  assert.notEqual(r.release_action,'NO_APPLICATION_RELEASE_NEEDED')
})

test('backend business change requires integration and mandatory controls', () => {
  const r=assessReleaseScope(impact(['app/backend/src/main/java/com/matrix/prp/wellness/WellnessService.java']))
  assert.equal(r.risk,'FEATURE_REVIEW')
  assert.ok(r.suggested_extra_evidence.includes('backend_business_and_tenant_regression'))
  assert.ok(r.required_release_controls.includes('owner_release_approval'))
})

test('mixed UI and migration changes inherit high risk', () => {
  const r=assessReleaseScope(impact([
    'app/web/src/views/WellnessView.vue',
    'app/backend/src/main/resources/db/migration/V30__wellness.sql',
  ],{features:['wellness']}))
  assert.equal(r.risk,'HIGH_REVIEW')
  assert.ok(r.suggested_extra_evidence.includes('real_browser_mobile_pwa_uat'))
  assert.ok(r.suggested_extra_evidence.includes('isolated_migration_backup_restore_rehearsal'))
})

test('invalid paths, duplicated files and untrusted classification are rejected', () => {
  assert.throws(()=>assessReleaseScope(impact(['../app/deploy/secret'])),/Untrusted/)
  assert.throws(()=>assessReleaseScope(impact(['app/web/src/view.ts','app/web/src/view.ts'])),/Untrusted/)
  assert.throws(()=>assessReleaseScope(impact(['app/web/src/view.ts'],{unclassifiedFiles:['not-in-diff']})),/Invalid/)
})

test('incomplete reports are not silently considered safe', () => {
  assert.throws(()=>assessReleaseScope({changedFiles:['app/web/src/Hello.vue']}),/Incomplete/)
  assert.throws(()=>assessReleaseScope(null),/Incomplete/)
})

test('report is explicitly advisory, never authorized or production-verified', () => {
  for(const files of [
    ['README.md'],
    ['app/web/src/views/WellnessView.vue'],
    ['app/backend/src/main/resources/db/migration/V30__wellness.sql']
  ]) {
    const r=assessReleaseScope(impact(files))
    assert.equal(r.analysis_type,'non_authoritative_pull_request_advisory')
    assert.equal(r.artifact_topology,'monolithic_backend_jar_plus_web')
    assert.equal(r.deployment_authorized,false)
    assert.equal(r.production_state_verified,false)
    assert.match(toMarkdown(r),/不是生产发布批准/)
  }
})

test('classify path uses a conservative safe allowlist', () => {
  assert.equal(classifyPath('app/web/src/views/WellnessView.vue'),'ui')
  assert.equal(classifyPath('app/deploy/release_control.py'),'platform')
  assert.equal(classifyPath('app/web/src/layouts/Layout.vue'),'shared')
  assert.equal(classifyPath('app/deploy/migration-policy.json'),'migration')
  assert.equal(classifyPath('unrecognized.txt'),'unknown')
  assert.throws(()=>classifyPath('app/web/src/../../deploy'))
})
