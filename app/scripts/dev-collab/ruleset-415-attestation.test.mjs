import test from 'node:test'
import assert from 'node:assert/strict'
import {OWNER_RULESET_DIGEST,OWNER_RULESET_REVISION,historicalNote,isHistoricalNote,validateOwnerAttestation,verifyOwnerAttestedPolicy} from './ruleset-415-attestation.mjs'
const full={"id":28050327,"name":"protect-collab-integration","target":"branch","source_type":"Repository","source":"micor-cjj-spec/matrix-prp","enforcement":"active","conditions":{"ref_name":{"exclude":[],"include":["refs/heads/integrate/REQ-20261031-001"]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"pull_request","parameters":{"required_approving_review_count":0,"dismiss_stale_reviews_on_push":true,"required_reviewers":[],"require_code_owner_review":false,"require_last_push_approval":false,"required_review_thread_resolution":true,"require_extra_approval_for_unattributed_changes":false,"allowed_merge_methods":["merge"]}},{"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":true,"do_not_enforce_on_create":true,"required_status_checks":[{"context":"backend-tests","integration_id":15368},{"context":"web-build","integration_id":15368},{"context":"mobile-build","integration_id":15368},{"context":"db-migration-integration","integration_id":15368},{"context":"video-db-integration","integration_id":15368},{"context":"impact-report","integration_id":15368},{"context":"dev-collab-contract","integration_id":15368}]}}],"node_id":"RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c","created_at":"2026-11-25T05:47:06.929Z","updated_at":"2026-11-25T05:47:07.076Z","bypass_actors":[],"current_user_can_bypass":"never"}
const req='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',main='a'.repeat(40),observed='2026-11-25T07:40:00Z',created='2026-11-25T07:40:20Z'
const a=()=>({schema_version:1,request_id:req,snapshot_sha256:OWNER_RULESET_DIGEST,rule_updated_at:OWNER_RULESET_REVISION,observed_at:observed,expected_main_sha:main,merge_sha:'5a30345529a1d07819069822a1b90e07b5376fcc'})
const context={requestId:req,mainSha:main,issueCreatedAt:created,now:Date.parse(created)}
test('owner attestation binds exact snapshot, request, main, merge and fresh observation',()=>{
 assert.equal(validateOwnerAttestation(a(),context),true)
 assert.equal(isHistoricalNote(historicalNote(a())),true)
 for(const bad of [{...a(),snapshot_sha256:'f'.repeat(64)},{...a(),request_id:'other'},{...a(),expected_main_sha:'b'.repeat(40)},{...a(),merge_sha:'b'.repeat(40)},{...a(),rule_updated_at:'2026-11-25T00:00:00Z'},{...a(),reviewerAuthorized:true}])assert.throws(()=>validateOwnerAttestation(bad,context))
 assert.throws(()=>validateOwnerAttestation(a(),{...context,now:Date.parse(observed)+600001}),/HISTORICAL_ATTESTATION_EXPIRED/)
 assert.throws(()=>validateOwnerAttestation(a(),{...context,issueCreatedAt:'2026-11-25T07:46:00Z',now:Date.parse('2026-11-25T07:46:00Z')}),/HISTORICAL_ATTESTATION_EXPIRED/)
})
test('redacted list remains explicitly unknown while full visible snapshot matches',()=>{
 const r=structuredClone(full);delete r.bypass_actors
 const result=verifyOwnerAttestedPolicy(r);assert.equal(result.visiblePolicyVerified,true);assert.equal(result.bypassListVisible,false);assert.equal(result.reviewerAuthorized,undefined)
 assert.equal(verifyOwnerAttestedPolicy(full).bypassListVisible,true)
})
test('changed revision, hidden additional policy, bypass and caller fail closed',()=>{
 for(const change of [r=>r.updated_at='2026-11-25T08:00:00Z',r=>r.rules[2].parameters.allowed_merge_methods=['squash'],r=>r.bypass_actors=[{actor_id:1}],r=>r.current_user_can_bypass='always',r=>delete r.current_user_can_bypass,r=>delete r.conditions,r=>r.extra_policy=true,r=>r.rules.pop()]){
 const r=structuredClone(full);change(r);assert.throws(()=>verifyOwnerAttestedPolicy(r))
 }
})
