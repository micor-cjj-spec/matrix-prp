import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const read=name=>readFileSync(new URL('../../../.github/workflows/'+name,import.meta.url),'utf8')
test('all required CI and impact checks run on requirement integration PRs',()=>{
  for(const name of ['ci.yml','feature-impact.yml','prp-dev-collab-contract.yml']){
    const text=read(name)
    const filter=text.match(/(?:^|\n)\s*pull_request:\s*\n\s*branches:\s*\[([^\]\n]+)\]/)
    assert.ok(filter,`${name} must define pull_request branches`)
    const branches=filter[1].split(',').map(branch=>branch.trim().replace(/^['"]|['"]$/g,''))
    assert.ok(branches.includes('main')&&branches.includes('integrate/**'),name)
    assert.ok(branches.includes('dev'),`${name} must also run for dev-targeted PRs`)
    assert.doesNotMatch(text,/pull_request_target:/,name)
  }
  const contract=read('prp-dev-collab-contract.yml')
  assert.doesNotMatch(contract,/\n\s*paths:\s*\n/,'contract checks must run for every task PR')
})
test('integrate/** is not configured as a production deployment trigger',()=>{
  const ci=read('ci.yml'),deploy=read('deploy-prp.yml')
  // CI push on dev supports pre-merge validation, not production publication.
  // Read the complete push branch list rather than pinning a historical list.
  const match = ci.match(/(?:^|\n)\s*push:\s*\n\s*branches:\s*\[([^\]\n]+)\]/)
  assert.ok(match, 'CI must declare explicit push branches')
  const branches = match[1].split(',').map(x => x.trim().replace(/^['"]|['"]$/g, ''))
  assert.ok(branches.includes('main') && branches.includes('dev'),
    'main and dev CI must both run')
  assert.ok(!branches.includes('integrate/**'),
    'integrate/** must never be a push CI trigger')
  assert.match(deploy,/github\.event\.workflow_run\.event == 'push'/)
  assert.match(deploy,/github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(deploy,/github\.ref == 'refs\/heads\/main'/)
  assert.match(deploy,/github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
})

test('automatic deployment workflow is triggered only by completed main CI',()=>{
  const deploy=read('deploy-prp.yml')
  const trigger=deploy.match(/^  workflow_run:\n((?:^ {4}[^\n]*\n)+)/m)
  assert.ok(trigger,'deployment must declare a scoped workflow_run trigger')
  assert.match(trigger[1],/^    workflows: \[CI\]$/m)
  assert.match(trigger[1],/^    types: \[completed\]$/m)
  assert.match(trigger[1],/^    branches: \[main\]$/m)
})
// Pin the complete existing job condition, normalizing YAML folded whitespace.
const expectedPublishGuard=[
  "always() && github.ref == 'refs/heads/main' &&",
  "needs.release_control.result == 'success' &&",
  "(needs.release_control.outputs.publish_allowed == 'true' ||",
  "(github.event_name == 'workflow_dispatch' && inputs.action == 'check')) &&",
  "((github.event_name == 'workflow_run' && needs.build.result == 'success' &&",
  "github.event.workflow_run.conclusion == 'success' &&",
  "github.event.workflow_run.event == 'push' &&",
  "github.event.workflow_run.head_branch == 'main' &&",
  "github.event.workflow_run.head_repository.full_name == github.repository) ||",
  "(github.event_name == 'workflow_dispatch' &&",
  "((inputs.action == 'deploy' && needs.build.result == 'success') ||",
  "((inputs.action == 'promote' || inputs.action == 'check' || inputs.action == 'rollback') && needs.build.result == 'skipped'))))"
].join(' ')
function verifyPublishGuard(deploy){
  const control=deploy.match(/^  release_control:\n([\s\S]*?)(?=^  build:\n)/m)
  assert.ok(control,'release control must precede build')
  assert.match(control[1],/^      publish_allowed: \$\{\{ steps\.control\.outputs\.publish_allowed \}\}$/m)
  assert.match(control[1],/id: control\n\s+run: python3 app\/deploy\/release_control\.py/)
  const publish=deploy.match(/^  publish:\n([\s\S]*?)^    environment:\n      name: production$/m)
  assert.ok(publish,'publish must use the protected production environment')
  assert.match(publish[1],/^    needs: \[build, release_control\]$/m)
  const condition=publish[1].match(/^    if: >-\n((?:^ {6}[^\n]*\n)+)/m)
  assert.ok(condition,'publish must declare an explicit job-level condition')
  assert.equal(condition[1].trim().replace(/\s+/g,' '),expectedPublishGuard,
    'complete publish condition must preserve existing hold, provenance and manual actions')
}
test('production publish job retains main-only CI provenance and the existing publication hold',()=>{
  verifyPublishGuard(read('deploy-prp.yml'))
  // The temporary hold may be removed through an authorized release; its
  // lifecycle and invalid-file handling remain covered by test_release_control.py.
})
test('publish condition regression rejects outer bypass and loss of read-only check',()=>{
  const deploy=read('deploy-prp.yml')
  const tail="needs.build.result == 'skipped'))))"
  assert.ok(deploy.includes(tail),'negative fixture must target the actual publish guard')
  const bypass=deploy.replace(tail,tail+' || true')
  const actions="inputs.action == 'promote' || inputs.action == 'check' || inputs.action == 'rollback'"
  assert.ok(deploy.includes(actions),'negative fixture must target the actual manual actions')
  const noCheck=deploy.replace(actions,"inputs.action == 'promote' || inputs.action == 'rollback'")
  for(const changed of [bypass,noCheck]){
    assert.notEqual(changed,deploy)
    assert.throws(()=>verifyPublishGuard(changed),/complete publish condition/)
  }
})
