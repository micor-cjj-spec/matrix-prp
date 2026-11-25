// P3.6 offline advisory projection. No transport, CLI, or runtime integration.
const {reviewSmokeReport}=require("./unified_staging_smoke_review.cjs");
const {createHash}=require("node:crypto");
const exact=(v,keys)=>v!==null&&typeof v==="object"&&!Array.isArray(v)&&
  Object.keys(v).sort().join("|")===keys.slice().sort().join("|");
const sha=v=>typeof v==="string"&&/^[a-f0-9]{40}$/.test(v)&&v.length===40;
const digest=v=>typeof v==="string"&&/^sha256:[a-f0-9]{64}$/.test(v)&&v.length===71;
const pos=v=>Number.isSafeInteger(v)&&v>0;
const requireValid=(ok,reason)=>{if(!ok)throw Error(reason)};
const candidateKeys=["commit","artifactDigest","schema"];
const identityKeys=[...candidateKeys,"environment","observedAt"];
const receiptKeys=["schemaVersion","kind","source","repository","issue","requestCommentId",
  "runId","runAttempt","workflowSha","operation","state","report","apiPassed","checksExecuted",
  "liveVerified","deploymentAuthorized","productionAuthorized"];
const candidateValid=c=>sha(c.commit)&&digest(c.artifactDigest)&&pos(c.schema)&&c.schema<=1000000;
const matches=(c,i)=>candidateKeys.every(k=>c[k]===i[k]);
const sameContext=(a,b)=>a.requestCommentId===b.requestCommentId&&a.runId===b.runId&&
  a.runAttempt===b.runAttempt&&a.workflowSha===b.workflowSha;
function projectStagingReview(input,now) {
  requireValid(exact(input,["candidate","expectedRun","receipt","before","after","startedAt","finishedAt"])&&pos(now),
    "INVALID_REVIEW_INPUT");
  const {candidate:c,expectedRun:e,receipt:r,before,after,startedAt,finishedAt}=input;
  requireValid(exact(c,candidateKeys)&&candidateValid(c),"INVALID_CANDIDATE");
  requireValid(exact(e,["requestCommentId","runId","runAttempt","workflowSha"])&&
    pos(e.requestCommentId)&&typeof e.runId==="string"&&/^[1-9][0-9]{0,19}$/.test(e.runId)&&
    e.runAttempt===1&&sha(e.workflowSha),"INVALID_RUN_CONTEXT");
  requireValid(exact(r,receiptKeys)&&r.schemaVersion===1&&r.kind==="PRP_STAGING_READ_SMOKE_RECEIPT"&&
    r.source==="github_task_candidate"&&r.repository==="micor-cjj-spec/matrix-prp"&&
    r.issue===396&&r.operation==="READ_SMOKE_ONLY"&&sameContext(e,r)&&
    r.liveVerified===false&&r.deploymentAuthorized===false&&r.productionAuthorized===false,
    "INVALID_RECEIPT_BINDING");
  const blocked=r.state==="BLOCKED_RUNNER";
  let summary=null;
  if(blocked)requireValid(r.report===null&&r.apiPassed===0&&r.checksExecuted===0,"INVALID_BLOCKED_RECEIPT");
  else {
    summary=reviewSmokeReport(r.report,"operator_report_unverified");
    requireValid(r.state===summary.state&&r.apiPassed===summary.apiPassed&&
      r.checksExecuted===summary.checksExecuted,"RECEIPT_AGGREGATE_MISMATCH");
  }
  for(const identity of [before,after]) {
    if(identity===null)continue;
    requireValid(exact(identity,identityKeys)&&candidateValid(identity)&&
      identity.environment==="prp-unified-396"&&pos(identity.observedAt),"INVALID_STAGE_IDENTITY");
  }
  requireValid(pos(startedAt)&&pos(finishedAt)&&startedAt<=finishedAt&&finishedAt<=now,
    "INVALID_OBSERVATION_WINDOW");
  const findings=[];
  if(!summary||summary.state!=="API_SMOKE_PASS")findings.push("READ_SMOKE_NOT_PASS");
  if(!before||!after)findings.push("STAGE_IDENTITY_MISSING");
  else {
    if(!matches(c,before)||!matches(c,after))findings.push("STAGE_IDENTITY_MISMATCH");
    if(before.observedAt>startedAt||after.observedAt<finishedAt||after.observedAt>now||
      now-before.observedAt>900||finishedAt-startedAt>900)
      findings.push("STALE_OR_UNBRACKETED_OBSERVATION");
  }
  if(now-finishedAt>900)findings.push("STALE_SMOKE");
  const binding={commit:c.commit,artifactDigest:c.artifactDigest,schema:c.schema,
    requestCommentId:e.requestCommentId,runId:e.runId,runAttempt:e.runAttempt,workflowSha:e.workflowSha,
    startedAt,finishedAt,before:before&&{commit:before.commit,artifactDigest:before.artifactDigest,
      schema:before.schema,environment:before.environment,observedAt:before.observedAt},
    after:after&&{commit:after.commit,artifactDigest:after.artifactDigest,schema:after.schema,
      environment:after.environment,observedAt:after.observedAt},
    cases:summary?r.report.cases.map(k=>({id:k.id,state:k.state,
      checks:k.checks.map(j=>({check:j.check,result:j.result}))})).sort((a,b)=>a.id.localeCompare(b.id)):null};
  return {schemaVersion:1,source:"offline_unverified_staging_review",state:"BLOCKED",
    bindingDigest:"sha256:"+createHash("sha256").update(JSON.stringify(binding)).digest("hex"),
    readSmoke:summary?.state||"BLOCKED_RUNNER",apiPassed:r.apiPassed,checksExecuted:r.checksExecuted,
    identityCorrelation:findings.length===0?"CLAIMED_MATCH_ONLY":"INCOMPLETE",
    findings:[...findings,"SOURCE_AUTHENTICITY_NOT_ESTABLISHED","BUSINESS_UAT_NOT_ESTABLISHED",
      "ARTIFACT_BYTES_NOT_VERIFIED_HERE","BACKUP_RESTORE_NOT_ESTABLISHED","HOLD_AND_RISK_NOT_REVIEWED",
      "INDEPENDENT_HUMAN_PROOF_NOT_ESTABLISHED"],
    deploymentAuthorized:false,productionAuthorized:false,releaseEligible:false,liveVerified:false};
}
module.exports={projectStagingReview};
