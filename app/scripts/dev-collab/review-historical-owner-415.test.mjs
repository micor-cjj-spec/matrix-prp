import test from 'node:test'
import assert from 'node:assert/strict'
import {verifyHistorical415Binding,verifyHistoricalIntegrationPolicy,trustedHistorical415Context} from './review-historical-owner-415.mjs'
import {REQUIRED_CHECKS} from './review-gate.mjs'
import {OWNER_RULESET_DIGEST,OWNER_RULESET_REVISION,historicalNote} from './ruleset-415-attestation.mjs'
const R='micor-cjj-spec/matrix-prp',H='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65',S='701cd06ba1358b8f09e337296db9f7b9b66a71d9',M='5a30345529a1d07819069822a1b90e07b5376fcc',target='integrate/REQ-20261031-001',id='11111111-1111-4111-8111-111111111111',req='REQ-20261031-001',worker='chat_t001_delivery_20261125',submit='ebd25c98-0723-4637-9e76-d2baf7b90b28'
const env=()=>({GITHUB_ACTIONS:'true',GITHUB_REF:'refs/heads/main',GITHUB_REPOSITORY:R,GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',GITHUB_ACTOR:'micor-cjj-spec',GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',GITHUB_WORKFLOW_REF:R+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main',GITHUB_SHA:'a'.repeat(40),GH_TOKEN:'synthetic'})
const snap=()=>({schema_version:1,requirement_id:req,issue_number:132,title:'MVP',status:'ACTIVE',version:13,tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'IN_REVIEW',claim:{claim_id:id,worker_id:worker,actor:'micor-cjj-spec'},depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],pr_number:415,head_sha:H}],processed_requests:[{request_id:submit,actor:'micor-cjj-spec',fingerprint:'a'.repeat(64),receipt:{type:'submit',task_id:'T-001',request_id:submit,version:13,status:'IN_REVIEW'}}]})
const observed='2026-11-25T07:40:00Z',created='2026-11-25T07:40:20Z',clock=()=>Date.parse(created),rid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const attestation=()=>({schema_version:1,request_id:rid,snapshot_sha256:OWNER_RULESET_DIGEST,rule_updated_at:OWNER_RULESET_REVISION,observed_at:observed,expected_main_sha:'a'.repeat(40),merge_sha:M})
const v=()=>({historical415:true,actor:'micor-cjj-spec',actorId:123868412,expected_version:13,expectedStateSha:S,policyAttestation:attestation(),issueCreatedAt:created,command:{type:'accept',requirement_id:req,task_id:'T-001',request_id:rid,note:historicalNote(attestation()),pr_number:415,head_sha:H,worker_id:worker,claim_id:id}})
const policy=()=>({id:28050327,target:'branch',enforcement:'active',conditions:{ref_name:{include:['refs/heads/'+target],exclude:[]}},bypass_actors:[],rules:[{type:'deletion'},{type:'non_fast_forward'},{type:'pull_request',parameters:{allowed_merge_methods:['merge'],required_review_thread_resolution:true}},{type:'required_status_checks',parameters:{strict_required_status_checks_policy:true,required_status_checks:REQUIRED_CHECKS.map(context=>({context,integration_id:15368}))}}]})
test('historical binding allows only exact version, submit and current claim',()=>{
 assert.equal(verifyHistorical415Binding(snap(),v(),S,env(),clock()),true)
 for(const [s,q,sha,e] of [[{...snap(),version:14},v(),S,env()],[snap(),{...v(),historical415:false},S,env()],[snap(),v(),'b'.repeat(40),env()],[snap(),v(),S,{...env(),GITHUB_REF:'refs/heads/dev'}],[snap(),{...v(),command:{...v().command,claim_id:'wrong'}},S,env()]])assert.throws(()=>verifyHistorical415Binding(s,q,sha,e,clock()))
})
test('changed integration policy fails closed',()=>{
 assert.equal(verifyHistoricalIntegrationPolicy(policy()),true)
 for(const change of [p=>p.bypass_actors.push({actor_id:1}),p=>p.rules[2].parameters.allowed_merge_methods=['squash'],p=>p.rules[3].parameters.required_status_checks.pop(),p=>p.enforcement='disabled']){const p=policy();change(p);assert.throws(()=>verifyHistoricalIntegrationPolicy(p))}
})
test('joint context retains original scope and ancestry gates and checks policy before and after evidence',()=>{
 const repo={id:1261866723,full_name:R},pr={number:415,changed_files:1,merged:true,merged_at:'2026-11-25T06:02:26Z',merge_commit_sha:M,base:{ref:target,repo},head:{sha:H,repo}}
 const branch={name:target,protected:true,commit:{sha:M}},comparison={status:'identical',behind_by:0,base_commit:{sha:M},merge_base_commit:{sha:M},commits:[]}
 const checks={total_count:7,check_runs:REQUIRED_CHECKS.map((name,i)=>({name,id:i+1,head_sha:H,status:'completed',conclusion:'success',app:{slug:'github-actions'}}))}
 let policyCalls=0
 const full=()=>{"id":28050327,"name":"protect-collab-integration","target":"branch","source_type":"Repository","source":"micor-cjj-spec/matrix-prp","enforcement":"active","conditions":{"ref_name":{"exclude":[],"include":["refs/heads/integrate/REQ-20261031-001"]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"pull_request","parameters":{"required_approving_review_count":0,"dismiss_stale_reviews_on_push":true,"required_reviewers":[],"require_code_owner_review":false,"require_last_push_approval":false,"required_review_thread_resolution":true,"require_extra_approval_for_unattributed_changes":false,"allowed_merge_methods":["merge"]}},{"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":true,"do_not_enforce_on_create":true,"required_status_checks":[{"context":"backend-tests","integration_id":15368},{"context":"web-build","integration_id":15368},{"context":"mobile-build","integration_id":15368},{"context":"db-migration-integration","integration_id":15368},{"context":"video-db-integration","integration_id":15368},{"context":"impact-report","integration_id":15368},{"context":"dev-collab-contract","integration_id":15368}]}}],"node_id":"RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c","created_at":"2026-11-25T13:47:06.929+08:00","updated_at":"2026-11-25T13:47:07.076+08:00","bypass_actors":[],"current_user_can_bypass":"never","_links":{"self":{"href":"https://api.github.com/repos/micor-cjj-spec/matrix-prp/rulesets/28050327"},"html":{"href":"https://github.com/micor-cjj-spec/matrix-prp/rules/28050327"}}}
 const visible=()=>{const r=full();delete r.bypass_actors;return r}
 const api=route=>{if(route.endsWith('/rulesets/28050327')){policyCalls++;return visible()}if(route.endsWith('/pulls/415'))return pr;if(route.includes('/branches/'))return branch;if(route.includes('/compare/'))return comparison;if(route.includes('/check-runs'))return checks;if(route.includes('/files'))return [{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}];throw Error('unexpected route')}
 const proof=()=>({historicalEvidenceVerified:true,pr:415,head:H,merge:M,syntheticMerge:'d3562e3a64741b4958e078ceb57574a17084a684',checks:7,mode:'read-only-review',stateWrite:false})
 assert.equal(trustedHistorical415Context(snap(),v(),S,env(),api,proof,clock).historical415Verified,true);assert.equal(policyCalls,2)
 assert.throws(()=>trustedHistorical415Context(snap(),v(),S,env(),api,()=>({...proof(),checks:6}),clock),/HISTORICAL_OWNER_EVIDENCE/)
 branch.protected=false;assert.throws(()=>trustedHistorical415Context(snap(),v(),S,env(),api,proof,clock),/UNPROTECTED_INTEGRATION_BRANCH/)
})

test('history binding rejects expired or changed attestation even with exact task state',()=>{
 const x=v();x.policyAttestation.snapshot_sha256='f'.repeat(64)
 assert.throws(()=>verifyHistorical415Binding(snap(),x,S,env(),clock()))
 assert.throws(()=>verifyHistorical415Binding(snap(),v(),S,env(),clock()+600001),/HISTORICAL_ATTESTATION_EXPIRED/)
})
