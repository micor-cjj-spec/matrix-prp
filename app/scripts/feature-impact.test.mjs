import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {resolve, dirname} from 'node:path'
import {fileURLToPath} from 'node:url'
import {validateRegistry, analyzeChangedFiles, toMarkdown} from './feature-impact.mjs'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const features = JSON.parse(readFileSync(resolve(repo,'app/config/feature-registry.json'),'utf8')).modules

test('registry maps only actual test/document files and declares API prefixes', () => {
  assert.deepEqual(validateRegistry(features), [])
})

test('video controller and mobile page affect video only', () => {
  const report = analyzeChangedFiles([
    'app/backend/src/main/java/com/matrix/prp/video/VideoController.java',
    'app/mobile/src/pages/video/index.vue',
  ], features)
  assert.deepEqual(report.affectedFeatures.map(x => x.code), ['videos'])
  assert.ok(report.affectedFeatures[0].apiPrefixes.includes('/api/video'))
  assert.ok(report.affectedFeatures[0].suggestedTests.some(x => x.endsWith('/VideoDatabaseIT.java')))
  assert.equal(report.unclassifiedFiles.length, 0)
})

test('web API and linked docs map to their registered domain', () => {
  const report = analyzeChangedFiles([
    'app/web/src/api/finance.ts',
    'app/docs/data/model.md',
  ], features)
  assert.ok(report.affectedFeatures.some(x => x.code === 'finance'))
  assert.equal(report.unclassifiedFiles.length, 0)
  assert.ok(report.suggestedCommands.some(x => x.includes('npm run build')))
})

test('changing shared auth flags every feature for review', () => {
  const report = analyzeChangedFiles([
    'app/backend/src/main/java/com/matrix/prp/auth/service/JwtService.java',
  ], features)
  assert.equal(report.globalEffect, true)
  assert.equal(report.risk, '高')
  assert.equal(report.affectedFeatures.length, features.filter(x=>x.type==='feature').length)
})

test('unknown paths are not silently treated as safe', () => {
  const report = analyzeChangedFiles(['app/surprise/new-service.ts'], features)
  assert.deepEqual(report.unclassifiedFiles, ['app/surprise/new-service.ts'])
  assert.equal(report.risk, '中')
  assert.match(toMarkdown(report), /未归类文件/)
})

test('generated registry changes are cross-cutting and map to all features', () => {
  const report = analyzeChangedFiles(['app/config/feature-registry.json'], features)
  assert.equal(report.globalEffect, true)
  assert.ok(report.affectedFeatures.some(x=>x.code==='knowledge'))
})

test('notification migration prompts database integration verification', () => {
  const report = analyzeChangedFiles(['app/docker/mysql/init/004-notification-center.sql'], features)
  assert.ok(report.affectedFeatures.some(x=>x.code==='notifications'))
  assert.ok(report.suggestedCommands.some(x=>x.includes('MySQL 8.4')))
})

test('changed paths are normalized, deduplicated, and output deterministic markdown', () => {
  const a = analyzeChangedFiles(['./app/web/src/api/video.ts','app/web/src/api/video.ts'], features)
  assert.deepEqual(a.changedFiles, ['app/web/src/api/video.ts'])
  assert.deepEqual(a.affectedFeatures.map(x=>x.code), ['videos'])
  assert.equal(toMarkdown(a),toMarkdown(a))
})
