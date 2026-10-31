import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyStateBranchRuleset } from './state-rule-policy.mjs'
const make=()=>({id:100,target:'branch',enforcement:'active',
  conditions:{ref_name:{include:['refs/heads/prp-collab-state'],exclude:[]}},
  rules:[{type:'update'},{type:'deletion'},{type:'non_fast_forward'}],
  bypass_actors:[{actor_type:'Integration',actor_id:1234,bypass_mode:'always'}]})
const fails=(r,code,appId=1234)=>assert.throws(()=>verifyStateBranchRuleset(r,appId),e=>e.code===code)
test('only active exact state-branch rules with designated GitHub App bypass pass',()=>{
 assert.equal(verifyStateBranchRuleset(make(),1234).allowed,true)
})
test('unprotected or weak state branch rules fail closed',()=>{
 const a=make();a.enforcement='evaluate';fails(a,'RULESET_NOT_ACTIVE')
 const b=make();b.rules.pop();fails(b,'MISSING_REQUIRED_STATE_RULES')
 const c=make();c.conditions.ref_name.include=['~ALL'];fails(c,'RULESET_TARGET_NOT_EXACT')
})
test('role and broad GitHub Actions app bypass are not permitted',()=>{
 const r=make();r.bypass_actors.push({actor_type:'RepositoryRole',actor_id:5,bypass_mode:'always'})
 fails(r,'UNSAFE_RULESET_BYPASS')
 const n=make();n.bypass_actors[0].actor_id=999;fails(n,'UNSAFE_RULESET_BYPASS')
 const m=make();m.bypass_actors[0].bypass_mode='pull_request';fails(m,'UNSAFE_RULESET_BYPASS')
})
test('cannot activate without configured numeric app identity',()=>{
 fails(make(),'CONFIGURE_DEDICATED_APP',NaN)
})
