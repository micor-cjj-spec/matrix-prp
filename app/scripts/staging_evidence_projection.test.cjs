const test=require("node:test"),assert=require("node:assert/strict");
const {projectStagingReview}=require("./staging_evidence_projection.cjs");
const NOW=1700000100;
function fixture(){
  const candidate={commit:"a".repeat(40),artifactDigest:"sha256:"+"b".repeat(64),schema:31};
  const expectedRun={requestCommentId:123,runId:"456",runAttempt:1,workflowSha:"c".repeat(40)};
  const cases=Array.from({length:9},(_,i)=>({id:"U0"+(i+1),state:"API_PASS",
    checks:Array.from({length:[3,5].includes(i)?2:1},(_,j)=>({check:j+1,result:"OK"}))}));
  const receipt={schemaVersion:1,kind:"PRP_STAGING_READ_SMOKE_RECEIPT",source:"github_task_candidate",
    repository:"micor-cjj-spec/matrix-prp",issue:396,...expectedRun,operation:"READ_SMOKE_ONLY",
    state:"API_SMOKE_PASS",report:{state:"API_SMOKE_PASS",cases},apiPassed:9,checksExecuted:11,
    liveVerified:false,deploymentAuthorized:false,productionAuthorized:false};
  const identity={...candidate,environment:"prp-unified-396"};
  return {candidate,expectedRun,receipt,before:{...identity,observedAt:NOW-40},
    after:{...identity,observedAt:NOW-5},startedAt:NOW-30,finishedAt:NOW-10};
}
test("complete fixture is only claimed correlation and always blocked",()=>{
  const r=projectStagingReview(fixture(),NOW);
  assert.equal(r.identityCorrelation,"CLAIMED_MATCH_ONLY");assert.equal(r.state,"BLOCKED");
  assert.equal(r.apiPassed,9);assert.equal(r.checksExecuted,11);
  assert.match(r.bindingDigest,/^sha256:[a-f0-9]{64}$/);
  for(const k of ["deploymentAuthorized","productionAuthorized","releaseEligible","liveVerified"])assert.equal(r[k],false);
});
test("missing before or after cannot satisfy stage identity",()=>{
  for(const key of ["before","after"]){const f=fixture();f[key]=null;
    assert.ok(projectStagingReview(f,NOW).findings.includes("STAGE_IDENTITY_MISSING"));}
});
test("commit, archive digest or schema drift cannot correlate",()=>{
  for(const [key,v] of [["commit","d".repeat(40)],["artifactDigest","sha256:"+"e".repeat(64)],["schema",32]]){
    const f=fixture();f.after[key]=v;assert.ok(projectStagingReview(f,NOW).findings.includes("STAGE_IDENTITY_MISMATCH"));}
});
test("wrong environment is rejected",()=>{const f=fixture();f.before.environment="production";
  assert.throws(()=>projectStagingReview(f,NOW),/INVALID_STAGE_IDENTITY/);});
test("stale or incorrectly bracketed observation remains incomplete",()=>{
  for(const change of [f=>f.before.observedAt=NOW-901,f=>f.before.observedAt=NOW-20,
    f=>f.after.observedAt=NOW-20,f=>f.after.observedAt=NOW+1]){
    const f=fixture();change(f);assert.ok(projectStagingReview(f,NOW).findings.includes("STALE_OR_UNBRACKETED_OBSERVATION"));}
});
test("stale smoke cannot correlate",()=>{const f=fixture();assert.ok(projectStagingReview(f,NOW+901).findings.includes("STALE_SMOKE"));});
test("wrong receipt run, comment, workflow or attempt rejected",()=>{
  for(const [key,v] of [["runId","999"],["requestCommentId",124],["workflowSha","d".repeat(40)],["runAttempt",2]]){
    const f=fixture();f.receipt[key]=v;assert.throws(()=>projectStagingReview(f,NOW),/INVALID_RECEIPT_BINDING/);}
});
test("forged authorizations and additional fields rejected",()=>{
  for(const change of [f=>f.receipt.productionAuthorized=true,f=>f.receipt.extra="x",
    f=>f.hold="clear",f=>f.receipt.liveVerified=true]){
    const f=fixture();change(f);assert.throws(()=>projectStagingReview(f,NOW));}
});
test("reuse existing smoke reviewer rejects forged counts and cases",()=>{
  for(const change of [f=>f.receipt.apiPassed=8,f=>f.receipt.report.cases.pop(),f=>f.receipt.checksExecuted=10]){
    const f=fixture();change(f);assert.throws(()=>projectStagingReview(f,NOW));}
});
test("blocked runner stays blocked",()=>{const f=fixture();Object.assign(f.receipt,{state:"BLOCKED_RUNNER",report:null,apiPassed:0,checksExecuted:0});
  assert.ok(projectStagingReview(f,NOW).findings.includes("READ_SMOKE_NOT_PASS"));});
test("digest stable for case order but changes with bound run identity",()=>{
  const f=fixture(),a=projectStagingReview(f,NOW).bindingDigest;f.receipt.report.cases.reverse();
  assert.equal(projectStagingReview(f,NOW).bindingDigest,a);
  f.expectedRun.runId=f.receipt.runId="457";assert.notEqual(projectStagingReview(f,NOW).bindingDigest,a);
});
test("future or reversed smoke window rejected",()=>{
  for(const change of [f=>f.finishedAt=NOW+1,f=>f.startedAt=NOW-1]){
    const f=fixture();change(f);assert.throws(()=>projectStagingReview(f,NOW),/INVALID_OBSERVATION_WINDOW/);}
});
