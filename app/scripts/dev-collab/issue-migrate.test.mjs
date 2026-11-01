import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {authorizeOwnerIssuedMigration} from './issue-migrate.mjs'
const state='062036f7021e215ffbfdcbf5689d207a0549b68b'
const proposal='fb57656dca6df5f12e083fc0430263b4d88e452d'
const valid=()=>({oneShotMigration:true,actor:'micor-cjj-spec',
 command:{type:'migrate_v1',requirement_id:'REQ-20261031-001',
  request_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  expected_state_sha:state,expected_proposal_sha:proposal}})
test('explicit authenticated owner Issue can request only pinned V0 to V1',()=>{
 assert.equal(authorizeOwnerIssuedMigration(valid(),state,proposal),true)
})
test('wrong Issue actor, stale V0 and wrong proposal are rejected',()=>{
 for(const [request,b,p] of [
  [{...valid(),actor:'other-user'},state,proposal],
  [{...valid(),oneShotMigration:false},state,proposal],
  [valid(),'0'.repeat(40),proposal],
  [valid(),state,'1'.repeat(40)],
  [{...valid(),command:{...valid().command,expected_proposal_sha:'1'.repeat(40)}},state,proposal],
  [{...valid(),command:{...valid().command,type:'migrate_v2'}},state,proposal]
 ])assert.throws(()=>authorizeOwnerIssuedMigration(request,b,p),
  e=>e.code==='MIGRATION_ISSUE_NOT_APPROVED')
})

test('owner-issued migration uses the full reviewed apply gate, not read-only verification',()=>{
 const source=readFileSync(new URL('./issue-migrate.mjs',import.meta.url),'utf8')
 assert.ok(source.includes("mode:'apply'"))
 assert.ok(source.includes("approvalPhrase:'APPLY-REQ-20261031-001-V1'"))
 assert.ok(source.includes('appInstallation:repos'))
 assert.ok(source.includes("pulls/144/reviews?per_page=100"))
 assert.ok(source.includes('verifyMigrationEvidence({before,after,pr,prFiles,reviews,rule:ruleset'))
 assert.doesNotMatch(source,/mode:'verify'/)
})
