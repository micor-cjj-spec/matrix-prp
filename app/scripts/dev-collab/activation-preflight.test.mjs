import test from 'node:test'
import assert from 'node:assert/strict'
import {evaluateActivationEvidence} from './activation-preflight.mjs'

const SHA='a'.repeat(40),REF='prp-collab-state',REQ='REQ-20261031-001'
const good=()=>({
 main:{name:'main',protected:true},
 stateBranch:{name:REF,protected:true,commit:{sha:SHA}},headSha:SHA,
 appId:1234,
 rule:{target:'branch',enforcement:'active',id:45,
   conditions:{ref_name:{include:['refs/heads/'+REF],exclude:[]}},
   rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
   bypass_actors:[{actor_type:'Integration',actor_id:1234,bypass_mode:'always'}]},
 environment:{name:'prp-collab-controller',protection_rules:[
   {type:'required_reviewers',reviewers:[{type:'User',reviewer:{login:'reviewer'}}]}]},
 installationRepos:{total_count:1,repositories:[{full_name:'micor-cjj-spec/matrix-prp'}]},
 snapshot:{schema_version:1,requirement_id:REQ,issue_number:132,title:'Pilot',
   version:0,status:'ACTIVE',processed_requests:[],tasks:[
     {task_id:'T-001',issue_number:133,title:'Core',status:'READY',claim:null,
       depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs']}]}
})
test('all observable prerequisites only permit an administrator to review pilot, not claim',()=>{
 const result=evaluateActivationEvidence(good())
 assert.equal(result.status,'PRECONDITIONS_OBSERVED')
 assert.deepEqual(result.blockers,[])
 assert.equal(result.allow_claim,false)
 assert.equal(result.allow_merge,false)
 assert.equal(result.allow_deploy,false)
})
test('current unprotected state and absent app/environment fail closed',()=>{
 const x=good();x.stateBranch.protected=false
 x.rule=null;x.appId=NaN;x.environment=null;x.installationRepos=null
 const out=evaluateActivationEvidence(x)
 assert.equal(out.status,'NO_GO')
 assert.ok(out.blockers.includes('STATE_BRANCH_UNPROTECTED'))
 assert.ok(out.blockers.some(x=>x.startsWith('STATE_RULESET_')))
 assert.ok(out.blockers.includes('ENVIRONMENT_REVIEW_NOT_VERIFIED'))
 assert.ok(out.blockers.includes('DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED'))
})
test('a broad App token cannot pass even with correct state rules',()=>{
 const x=good();x.installationRepos={total_count:2,
 repositories:[{full_name:'micor-cjj-spec/matrix-prp'},{full_name:'another/repository'}]}
 assert.ok(evaluateActivationEvidence(x).blockers.includes('DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED'))
})
test('unreviewed environment and any task claim block initial pilot',()=>{
 const x=good();x.environment.protection_rules=[]
 x.snapshot.tasks[0].status='CLAIMED'
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('ENVIRONMENT_REVIEW_NOT_VERIFIED'))
 assert.ok(out.blockers.includes('INVALID_STATE_SNAPSHOT')||
   out.blockers.includes('NOT_CLEAN_INITIAL_PILOT_STATE'))
})
test('mismatched state SHA or missing snapshot rejects stale readiness evidence',()=>{
 const x=good();x.headSha='b'.repeat(40);x.snapshot=null
 const out=evaluateActivationEvidence(x)
 assert.ok(out.blockers.includes('STATE_REF_UNVERIFIED'))
 assert.ok(out.blockers.includes('INVALID_STATE_SNAPSHOT'))
})
