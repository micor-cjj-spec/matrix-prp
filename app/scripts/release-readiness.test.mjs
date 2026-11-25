import test from 'node:test'
import assert from 'node:assert/strict'
import {parseOwnerRequest, validateHoldSnapshot, assessGithubPrecheck, summaryMarkdown, REQUIRED_JOBS} from './release-readiness.mjs'

const A = 'a'.repeat(40)
const B = 'b'.repeat(40)
const REPO = 'micor-cjj-spec/matrix-prp'
const holdRaw = JSON.stringify({schema_version:1,reason:'Collaboration pilot: production frozen'})

function event(sha=A, login='micor-cjj-spec') {
  return {action:'created',repository:{full_name:REPO},issue:{number:323},
    comment:{user:{login},body:'PRP-RELEASE-CHECK sha='+sha}}
}
function run(sha=A,options={}) {
  return {id:123,name:'CI',event:'push',head_branch:'main',head_sha:sha,
    head_repository:{full_name:REPO},status:'completed',conclusion:'success',...options}
}
function jobs(overrides={}) {
  return REQUIRED_JOBS.map(name => ({name,status:'completed',
    conclusion:overrides[name] || 'success'}))
}
function inputs(overrides={}) {
  return {requestedSha:A,checkedOutSha:A,currentMainSha:A,hold:true,
    ciRuns:[run()],ciJobs:jobs(),...overrides}
}

test('only an exact owner comment on Issue 323 is allowed', () => {
  assert.equal(parseOwnerRequest(event(),REPO),A)
  assert.throws(()=>parseOwnerRequest(event(A,'another-user'),REPO))
  assert.throws(()=>parseOwnerRequest({...event(),issue:{number:260}},REPO))
  assert.throws(()=>parseOwnerRequest({...event(),repository:{full_name:'another/repo'}},REPO))
  assert.throws(()=>parseOwnerRequest({...event(),action:'edited'},REPO))
})

test('comment parser rejects trailing content, newlines and unsafe requests', () => {
  for(const body of [
    'PRP-RELEASE-CHECK sha='+A+'\nrun: deploy',
    'PRP-RELEASE-CHECK sha='+A.toUpperCase(),
    'PRP-RELEASE-CHECK sha='+A+' ',
    'PRP-RELEASE-CHECK sha='+A+'\n',
    'PRP-RELEASE-CHECK sha=main',
    'PRP-RELEASE-CHECK sha='+A+';deploy',
  ]) assert.throws(()=>parseOwnerRequest({...event(),comment:{user:{login:'micor-cjj-spec'},body}},REPO))
})

test('hold stays active despite all successful GitHub CI jobs', () => {
  const r=assessGithubPrecheck(inputs())
  assert.equal(r.state,'HELD')
  assert.deepEqual(r.blockers,['PUBLICATION_HOLD_ACTIVE'])
  assert.equal(r.workflow_run_id,123)
  assert.equal(r.production_authorized,false)
  assert.equal(r.production_live_verified,false)
})

test('no hold plus successful CI still requires production approval and UAT', () => {
  const r=assessGithubPrecheck(inputs({hold:false}))
  assert.equal(r.state,'GITHUB_CI_PRECHECK_PASS_ONLY')
  assert.equal(r.production_authorized,false)
  assert.ok(r.not_checked.includes('production_environment_approval'))
  assert.ok(r.not_checked.includes('production_backup_restore'))
})

test('stale main SHA blocks even successful old CI', () => {
  const r=assessGithubPrecheck(inputs({currentMainSha:B,hold:false}))
  assert.equal(r.state,'BLOCKED')
  assert.ok(r.blockers.includes('STALE_OR_UNMATCHED_MAIN_SHA'))
  assert.equal(r.production_authorized,false)
})

test('workflow checkout must match requested commit', () => {
  const r=assessGithubPrecheck(inputs({checkedOutSha:B,hold:false}))
  assert.ok(r.blockers.includes('STALE_OR_UNMATCHED_MAIN_SHA'))
})

test('a green PR CI is not a real main push CI', () => {
  const r=assessGithubPrecheck(inputs({ciRuns:[run(A,{event:'pull_request'})],hold:false}))
  assert.equal(r.state,'BLOCKED')
  assert.ok(r.blockers.includes('NO_SUCCESSFUL_EXACT_MAIN_PUSH_CI'))
})

test('a successful CI for a different SHA never counts', () => {
  const r=assessGithubPrecheck(inputs({ciRuns:[run(B)],hold:false}))
  assert.ok(r.blockers.includes('NO_SUCCESSFUL_EXACT_MAIN_PUSH_CI'))
})

test('a successful CI from another repository never counts', () => {
  const r=assessGithubPrecheck(inputs({ciRuns:[run(A,{head_repository:{full_name:'fork/matrix-prp'}})],hold:false}))
  assert.ok(r.blockers.includes('NO_SUCCESSFUL_EXACT_MAIN_PUSH_CI'))
})

test('pending, failed and skipped CI do not count as successful', () => {
  for(const updates of [{status:'queued',conclusion:null},
      {status:'completed',conclusion:'failure'},
      {status:'completed',conclusion:'skipped'}]) {
    const r=assessGithubPrecheck(inputs({ciRuns:[run(A,updates)],hold:false}))
    assert.equal(r.state,'BLOCKED')
  }
})

test('a later failed exact-SHA CI run overrides an older success', () => {
  const r=assessGithubPrecheck(inputs({hold:false,
    ciRuns:[run(A,{id:123}),run(A,{id:124,conclusion:'failure'})],
    ciJobs:jobs()}))
  assert.equal(r.state,'BLOCKED')
  assert.ok(r.blockers.includes('NO_SUCCESSFUL_EXACT_MAIN_PUSH_CI'))
  assert.equal(r.workflow_run_id,null)
})

test('missing, failed, and duplicate required CI jobs block', () => {
  const required=REQUIRED_JOBS[0]
  for(const list of [
    jobs().filter(x=>x.name!==required),
    jobs({[required]:'failure'}),
    [...jobs(),jobs()[0]]
  ]) {
    const r=assessGithubPrecheck(inputs({ciJobs:list,hold:false}))
    assert.equal(r.state,'BLOCKED')
    assert.ok(r.blockers.includes('REQUIRED_JOB_NOT_SUCCESS:'+required))
  }
})

test('unrelated successful extra job does not weaken required jobs', () => {
  const r=assessGithubPrecheck(inputs({hold:false,
    ciJobs:[...jobs(),{name:'unrelated-job',status:'completed',conclusion:'success'}]}))
  assert.equal(r.state,'GITHUB_CI_PRECHECK_PASS_ONLY')
})

test('release hold is validated as a strictly shaped file', () => {
  assert.equal(validateHoldSnapshot(holdRaw,true),true)
  assert.equal(validateHoldSnapshot(null,false),false)
  assert.throws(()=>validateHoldSnapshot(holdRaw,true,true))
  assert.throws(()=>validateHoldSnapshot('{"schema_version":1,"reason":""}',true))
  assert.throws(()=>validateHoldSnapshot('{"schema_version":1,"reason":"x","override":true}',true))
  assert.throws(()=>validateHoldSnapshot('{}',true))
})

test('malformed or untrusted inputs are rejected rather than accepted', () => {
  assert.throws(()=>assessGithubPrecheck(inputs({hold:'false'})))
  assert.throws(()=>assessGithubPrecheck(inputs({requestedSha:'main'})))
  assert.throws(()=>assessGithubPrecheck(inputs({ciJobs:'pass'})))
  assert.throws(()=>assessGithubPrecheck(inputs({ciRuns:[run()],ciJobs:[null]})))
})

test('summary distinguishes CI precheck from LIVE or approval', () => {
  const r=assessGithubPrecheck(inputs({hold:false}))
  const md=summaryMarkdown(r)
  assert.match(md,/not a deployment approval/)
  assert.match(md,/Production authorized \| \*\*NO\*\*/)
  assert.match(md,/LIVE verified \| \*\*NO\*\*/)
})

test('an empty CI response cannot imply ready', () => {
  const r=assessGithubPrecheck(inputs({hold:false,ciRuns:[],ciJobs:[]}))
  assert.equal(r.state,'BLOCKED')
  assert.equal(r.workflow_run_id,null)
})

test('global hold always overrides other precheck failures', () => {
  const r=assessGithubPrecheck(inputs({ciRuns:[],ciJobs:[],currentMainSha:B}))
  assert.equal(r.state,'HELD')
  assert.ok(r.blockers.includes('STALE_OR_UNMATCHED_MAIN_SHA'))
})

 test('failed extra job cannot be hidden by six green required jobs', () => {
  const r=assessGithubPrecheck(inputs({hold:false,
    ciJobs:[...jobs(),{name:'additional-integration',status:'completed',conclusion:'failure'}]}))
  assert.equal(r.state,'BLOCKED')
  assert.ok(r.blockers.includes('CI_JOB_NOT_SUCCESS'))
})
