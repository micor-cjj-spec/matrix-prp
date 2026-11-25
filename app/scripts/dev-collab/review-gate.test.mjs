import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyTaskEvidence, verifyRequirementClose, verifyIntegrationRelease, verifyIntegrationPolicy, REQUIRED_CHECKS } from './review-gate.mjs'
const sha='a'.repeat(40),merge='b'.repeat(40),integration='c'.repeat(40)
const make=()=>({schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
  status:'ACTIVE',version:3,title:'MVP',processed_requests:[],
  tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'IN_REVIEW',
    claim:{claim_id:'11111111-1111-4111-8111-111111111111',worker_id:'chat-A',actor:'micor-cjj-spec'},
    depends_on:[],allowed_paths:['app/scripts/dev-collab/'],pr_number:138,head_sha:sha}]})
const pack=()=>({
  pr:{number:138,changed_files:1,merged:true,merged_at:'2026-10-31T18:00:00Z',merge_commit_sha:merge,
    base:{ref:'integrate/REQ-20261031-001',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
    head:{sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}}},
  branch:{name:'integrate/REQ-20261031-001',protected:true,commit:{sha:integration}},
  comparison:{status:'ahead',behind_by:0,base_commit:{sha:merge},merge_base_commit:{sha:merge},commits:[]},
  files:[{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}],
  checks:{total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
    name,id:i+1,head_sha:sha,status:'completed',conclusion:'success',
    started_at:'2026-10-31T18:00:00Z',app:{slug:'github-actions'}
  }))}
})
const refuses=(fn,code)=>assert.throws(fn,e=>e.code===code)
test('acceptance verification binds PR, merged integration and 7 exact GitHub checks',()=>{
  const r=verifyTaskEvidence(make(),'T-001',pack())
  assert.equal(r.verified,true)
  assert.equal(r.checks,7)
  assert.equal(r.integration_sha,integration)
})
test('draft or unmerged PR cannot complete a task',()=>{
  const e=pack();e.pr.merged=false
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'PR_NOT_MERGED')
})
test('candidate targets a distinct integration branch, never unreviewed main',()=>{
  const e=pack();e.pr.base.ref='main'
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'WRONG_INTEGRATION_BASE')
})
test('head SHA must match the originally submitted task artifact',()=>{
  const e=pack();e.pr.head.sha='d'.repeat(40)
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'WRONG_PR_OR_HEAD')
})
test('integration branch must be protected',()=>{
  const e=pack();e.branch.protected=false
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'UNPROTECTED_INTEGRATION_BRANCH')
})
test('proof must establish merged commit is still ancestor of integration head',()=>{
  const e=pack();e.comparison.behind_by=1
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'MERGE_NOT_ON_BASE')
})
test('checks must be complete, latest and from verified GitHub Actions app',()=>{
  const e=pack();e.checks.check_runs.pop()
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'INCOMPLETE_CHECK_PAGINATION')
  const f=pack();f.checks.check_runs[0].app.slug='other-app'
  refuses(()=>verifyTaskEvidence(make(),'T-001',f),'CHECK_MISSING_backend-tests')
  const g=pack();g.checks.check_runs[0].conclusion='failure'
  refuses(()=>verifyTaskEvidence(make(),'T-001',g),'CHECK_NOT_GREEN_backend-tests')
})
test('newer failing check defeats earlier green result',()=>{
  const e=pack();e.checks.check_runs.push({...e.checks.check_runs[0],
    started_at:'2026-10-31T19:00:00Z',conclusion:'failure',id:99})
  e.checks.total_count++
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'CHECK_NOT_GREEN_backend-tests')
})
test('foreign GitHub PR repository is refused',()=>{
  const e=pack();e.pr.head.repo.full_name='someone/fork'
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'FOREIGN_HEAD_REPOSITORY')
})
test('a requirement cannot close until every task is done and owner signs off',()=>{
  const s=make()
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true}), 'INCOMPLETE_REQUIREMENT')
  s.tasks[0].status='DONE';s.tasks[0].claim=null
  refuses(()=>verifyRequirementClose(s,{}),'OWNER_APPROVAL_REQUIRED')
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true}),'EXPLICIT_ACCEPTANCE_REQUIRED')
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true}),'INTEGRATION_REVIEW_REQUIRED')
  assert.equal(verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true}).ready_to_close,true)
})

test('wrong file scope or stolen rename cannot pass task acceptance',()=>{
  const a=pack();a.files=[{filename:'app/web/src/App.vue',status:'modified'}]
  refuses(()=>verifyTaskEvidence(make(),'T-001',a),'TASK_FILE_OUTSIDE_SCOPE')
  const b=pack();b.files=[{filename:'app/scripts/dev-collab/core.mjs',status:'renamed',previous_filename:'app/backend/pom.xml'}]
  refuses(()=>verifyTaskEvidence(make(),'T-001',b),'RENAME_SOURCE_OUTSIDE_SCOPE')
})
test('CI workflow modification is never authorized by ordinary task acceptance',()=>{
  const s=make();s.tasks[0].allowed_paths=['.github/workflows/']
  const a=pack();a.files=[{filename:'.github/workflows/ci.yml',status:'modified'}]
  refuses(()=>verifyTaskEvidence(s,'T-001',a),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
})
test('incomplete or paginated PR file list fails closed',()=>{
  const a=pack();a.pr.changed_files=2
  refuses(()=>verifyTaskEvidence(make(),'T-001',a),'INCOMPLETE_PR_FILE_LIST')
})

test('critical CI workflow rename cannot bypass changed-file allowlist',()=>{
  const s=make()
  s.tasks[0].allowed_paths=['.github/']
  const evidence=pack()
  evidence.files=[{filename:'.github/workflows/ci-copy.yml',
    previous_filename:'.github/workflows/ci.yml',status:'renamed'}]
  refuses(()=>verifyTaskEvidence(s,'T-001',evidence),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
})

const validDevRelease=()=>{
 const s=make()
 s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const proof={
   pr:{number:139,head:{ref:'dev',sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
      base:{ref:'main',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
      merged:true,merged_at:'2026-11-23T00:00:00Z',merge_commit_sha:merge},
   branch:{name:'main',protected:true,commit:{sha:integration}},
   comparison:{status:'ahead',behind_by:0,
     base_commit:{sha:merge},merge_base_commit:{sha:merge},commits:[]},
   integrationBranch:{name:'integrate/REQ-20261031-001',protected:true,
     commit:{sha:'d'.repeat(40)}},
   integrationComparison:{status:'ahead',behind_by:0,
     base_commit:{sha:'d'.repeat(40)},merge_base_commit:{sha:'d'.repeat(40)},commits:[]},
   mainAncestryComparison:{status:'ahead',behind_by:0,
     base_commit:{sha},merge_base_commit:{sha},commits:[]},
   checks:pack().checks
 }
 return {s,command,proof}
}
test('final closure requires merged same-repo dev -> main and accepted integration ancestry',()=>{
 const {s,command,proof}=validDevRelease()
 const result=verifyIntegrationRelease(s,command,proof)
 assert.equal(result.verified,true)
 assert.equal(result.dev_head_sha,sha)
 assert.equal(result.accepted_integration_sha,'d'.repeat(40))
})
test('direct integrate -> main, feature -> main and fork dev -> main are denied',()=>{
 for(const ref of ['integrate/REQ-20261031-001','feature/unsafe']){
  const {s,command,proof}=validDevRelease()
  proof.pr.head.ref=ref
  refuses(()=>verifyIntegrationRelease(s,command,proof),'WRONG_MAIN_RELEASE_TARGET')
 }
 const {s,command,proof}=validDevRelease()
 proof.pr.head.repo.full_name='another/repository'
 refuses(()=>verifyIntegrationRelease(s,command,proof),'WRONG_MAIN_RELEASE_TARGET')
})
test('missing or unprotected integration branch can never authorize dev-only closure',()=>{
 for(const change of [
  proof=>{proof.integrationBranch=null},
  proof=>{proof.integrationBranch.protected=false},
  proof=>{proof.integrationBranch.name='integrate/REQ-20261031-001-solo'}
 ]){
  const {s,command,proof}=validDevRelease()
  change(proof)
  refuses(()=>verifyIntegrationRelease(s,command,proof),'INTEGRATION_BRANCH_NOT_PROTECTED')
 }
})
test('dev PR must contain accepted integration commit in true ancestry',()=>{
 for(const change of [
  proof=>{proof.integrationComparison=null},
  proof=>{proof.integrationComparison.behind_by=1},
  proof=>{proof.integrationComparison.base_commit.sha='e'.repeat(40)},
  proof=>{proof.integrationComparison.merge_base_commit.sha='e'.repeat(40)},
  proof=>{proof.integrationComparison.commits=undefined}
 ]){
  const {s,command,proof}=validDevRelease()
  change(proof)
  refuses(()=>verifyIntegrationRelease(s,command,proof),'INTEGRATION_NOT_IN_DEV_ANCESTRY')
 }
})
test('no merge, unprotected main, wrong dev SHA or failing head checks prevent closure',()=>{
 let p=validDevRelease()
 p.proof.pr.merged=false
 refuses(()=>verifyIntegrationRelease(p.s,p.command,p.proof),'PR_NOT_MERGED')
 p=validDevRelease();p.proof.branch.protected=false
 refuses(()=>verifyIntegrationRelease(p.s,p.command,p.proof),'MAIN_NOT_PROTECTED')
 p=validDevRelease();p.proof.pr.head.sha='e'.repeat(40)
 refuses(()=>verifyIntegrationRelease(p.s,p.command,p.proof),'WRONG_PR_OR_HEAD')
 p=validDevRelease();p.proof.checks.check_runs[0].conclusion='failure'
 refuses(()=>verifyIntegrationRelease(p.s,p.command,p.proof),'CHECK_NOT_GREEN_backend-tests')
 p=validDevRelease();p.s.tasks[0].status='IN_REVIEW'
 // A task IN_REVIEW must retain a valid claim; otherwise snapshot validation
 // correctly fails first with ACTIVE_CLAIM instead of the intended close gate.
 p.s.tasks[0].claim={claim_id:'11111111-1111-4111-8111-111111111111',
   worker_id:'chat-A',actor:'micor-cjj-spec'}
 refuses(()=>verifyIntegrationRelease(p.s,p.command,p.proof),'INCOMPLETE_REQUIREMENT')
})

test('squash/rebase cannot fake the exact tested dev head as main ancestry',()=>{
 for(const change of [
  proof=>{proof.mainAncestryComparison=null},
  proof=>{proof.mainAncestryComparison.behind_by=1},
  proof=>{proof.mainAncestryComparison.base_commit.sha='f'.repeat(40)},
  proof=>{proof.mainAncestryComparison.merge_base_commit.sha='f'.repeat(40)},
  proof=>{proof.mainAncestryComparison.commits=undefined}
 ]){
  const {s,command,proof}=validDevRelease()
  change(proof)
  refuses(()=>verifyIntegrationRelease(s,command,proof),'DEV_HEAD_NOT_IN_MAIN_ANCESTRY')
 }
})


const integrationPolicyFixture=()=>({
  "id": 28050327,
  "name": "protect-collab-integration",
  "target": "branch",
  "source_type": "Repository",
  "source": "micor-cjj-spec/matrix-prp",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "refs/heads/integrate/REQ-20261031-001"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": false,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
        "required_status_checks": [
          {
            "context": "backend-tests",
            "integration_id": 15368
          },
          {
            "context": "web-build",
            "integration_id": 15368
          },
          {
            "context": "mobile-build",
            "integration_id": 15368
          },
          {
            "context": "db-migration-integration",
            "integration_id": 15368
          },
          {
            "context": "video-db-integration",
            "integration_id": 15368
          },
          {
            "context": "impact-report",
            "integration_id": 15368
          },
          {
            "context": "dev-collab-contract",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c",
  "created_at": "2026-11-25T05:47:06.929Z",
  "updated_at": "2026-11-25T05:47:07.076Z",
  "bypass_actors": [],
  "current_user_can_bypass": "never"
})
test('integration policy requires full exact Ruleset and no bypass',()=>{
 assert.equal(verifyIntegrationPolicy('REQ-20261031-001',integrationPolicyFixture()).verified,true)
 for(const mutate of [
   r=>{delete r.bypass_actors},r=>r.bypass_actors.push({actor_type:'Integration',actor_id:1,bypass_mode:'always'}),r=>r.current_user_can_bypass='always'
 ]){const r=integrationPolicyFixture();mutate(r);refuses(()=>verifyIntegrationPolicy('REQ-20261031-001',r),'INTEGRATION_POLICY_BYPASS_UNVERIFIED')}
 for(const mutate of [r=>r.id++,r=>r.enforcement='evaluate',r=>r.updated_at='2026-11-26T00:00:00Z',r=>r.rules.pop(),r=>r.rules[2].parameters.allowed_merge_methods=['squash'],r=>r.rules[3].parameters.required_status_checks.pop(),r=>r.conditions.ref_name.include=['~ALL']]){
  const r=integrationPolicyFixture();mutate(r);refuses(()=>verifyIntegrationPolicy('REQ-20261031-001',r),'INTEGRATION_POLICY_DRIFT')
 }
 const r=integrationPolicyFixture();r.unexpected=true;refuses(()=>verifyIntegrationPolicy('REQ-20261031-001',r),'INTEGRATION_POLICY_UNKNOWN_FIELDS')
 refuses(()=>verifyIntegrationPolicy('REQ-20261031-002',integrationPolicyFixture()),'INTEGRATION_POLICY_NOT_REGISTERED')
})
