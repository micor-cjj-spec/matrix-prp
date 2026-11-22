import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {authorizeOwnerIssuedMigration} from './issue-migrate.mjs'
const state='062036f7021e215ffbfdcbf5689d207a0549b68b'
const proposal='bf80d5c384d5f687cb980b6e04127fc42167d7a8'
const valid=()=>({oneShotMigration:true,actor:'micor-cjj-spec',
 actorId:123868412,source_issue:265,
 command:{type:'migrate_v1',requirement_id:'REQ-20261031-001',
  request_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  expected_state_sha:state,expected_proposal_sha:proposal}})
test('explicit authenticated owner Issue can request only pinned V0 to V1',()=>{
 assert.equal(authorizeOwnerIssuedMigration(valid(),state,proposal),true)
})
test('wrong Issue actor, stale V0 and wrong proposal are rejected',()=>{
 for(const [request,b,p] of [
  [{...valid(),actor:'other-user'},state,proposal],
  [{...valid(),actorId:9},state,proposal],
  [{...valid(),source_issue:0},state,proposal],
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
 assert.ok(source.includes('validateIssueEvent(env,event,latest)'))
 assert.ok(source.indexOf('validateIssueEvent(env,event,latest)') <
   source.lastIndexOf("git('-C',temp,'push'"))

 assert.ok(source.includes('verifyMigrationEvidence({before,after,pr,prFiles,reviews,rule:ruleset'))
 assert.doesNotMatch(source,/mode:'verify'/)
})

test('owner Issue migration revalidates live human reviews and App scope immediately before push',()=>{
 const source=readFileSync(new URL('./issue-migrate.mjs',import.meta.url),'utf8')
 const issueRecheck=source.indexOf('validateIssueEvent(env,event,latest)')
 const finalPr=source.indexOf("const finalPr=gh('repos/'+REPO+'/pulls/144')")
 const finalFiles=source.indexOf("const finalFiles=gh('repos/'+REPO+'/pulls/144/files?per_page=100')")
 const finalReviews=source.indexOf("const finalReviews=gh('repos/'+REPO+'/pulls/144/reviews?per_page=100')")
 const finalRule=source.indexOf("const finalRule=gh('repos/'+REPO+'/rulesets/'+env.COLLAB_RULESET_ID,env.COLLAB_APP_TOKEN)")
 const finalRepos=source.indexOf("const finalRepos=gh('installation/repositories',env.COLLAB_APP_TOKEN)")
 const verify=source.indexOf('verifyMigrationEvidence({before,after,pr:finalPr')
 const race=source.indexOf("'MIGRATION_POST_REVIEW_RACE'")
 const push=source.lastIndexOf("git('-C',temp,'push','origin','HEAD:'+REF)")
 assert.ok(issueRecheck>0&&finalPr>issueRecheck&&finalFiles>finalPr)
 assert.ok(finalReviews>finalFiles&&finalRule>finalReviews&&finalRepos>finalRule)
 assert.ok(verify>finalRepos&&race>verify&&push>race)
 assert.ok(source.slice(verify,push).includes("mode:'apply'"))
 assert.ok(source.slice(verify,push).includes('reviews:finalReviews'))
 assert.ok(source.slice(verify,push).includes('appInstallation:finalRepos'))
})

test('solo mode remains restricted to the owner-verified Issue path, not a free-form approval switch',()=>{
 const source=readFileSync(new URL('./issue-migrate.mjs',import.meta.url),'utf8')
 assert.match(source,/ownerIssue:validated/)
 assert.match(source,/ownerIssue:authorized/)
 assert.match(source,/validateIssueEvent\(env,event,latest\)/)
 const indexReview=source.indexOf('const finalReviews=')
 const indexEvent=source.indexOf('validateIssueEvent(env,event,latest)')
 const indexSolo=source.indexOf('ownerIssue:authorized')
 const indexPush=source.lastIndexOf("git('-C',temp,'push','origin','HEAD:'+REF)")
 assert.ok(indexEvent>=0&&indexReview>indexEvent&&indexSolo>indexReview&&indexPush>indexSolo)
})
