import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const read=name=>readFileSync(new URL('../../../.github/workflows/'+name,import.meta.url),'utf8')
test('all required CI and impact checks run on requirement integration PRs',()=>{
  for(const name of ['ci.yml','feature-impact.yml','prp-dev-collab-contract.yml']){
    const text=read(name)
    assert.match(text,/pull_request:\s*\n\s*branches: \[main, 'integrate\/\*\*'\]/,name)
    assert.doesNotMatch(text,/pull_request_target:/,name)
  }
  const contract=read('prp-dev-collab-contract.yml')
  assert.doesNotMatch(contract,/\n\s*paths:\s*\n/,'contract checks must run for every task PR')
})
test('integrate/** is not configured as a production deployment trigger',()=>{
  const ci=read('ci.yml'),deploy=read('deploy-prp.yml')
  assert.match(ci,/push:\s*\n\s*branches: \[main, feat\/multi-user-foundation\]/)
  assert.match(deploy,/github\.event\.workflow_run\.event == 'push'/)
  assert.match(deploy,/github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(deploy,/github\.ref == 'refs\/heads\/main'/)
  assert.match(deploy,/github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
})
