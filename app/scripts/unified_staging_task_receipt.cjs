// #396: offline-tested, fixed task adapter. No active workflow or secret setup.
const fs=require("node:fs");
const {admit}=require("./unified_staging_task_request.cjs");
const {executeApprovedSmoke}=require("./unified_staging_live_runner.cjs");
const {reviewSmokeReport}=require("./unified_staging_smoke_review.cjs");
function contextFrom(env){
  return {eventName:env.GITHUB_EVENT_NAME,ref:env.GITHUB_REF,
    repository:env.GITHUB_REPOSITORY,repositoryId:env.GITHUB_REPOSITORY_ID,
    actorId:env.GITHUB_ACTOR_ID,runAttempt:env.GITHUB_RUN_ATTEMPT};
}
async function executeTask({event,env,transport,signalFor,now}){
  const gate=admit(event,contextFrom(env));
  if(!gate.admitted)throw Error("TASK_REQUEST_NOT_ADMITTED");
  if(!/^[1-9][0-9]{0,19}$/.test(env.GITHUB_RUN_ID||"")||
     !/^[0-9a-f]{40}$/.test(env.GITHUB_SHA||""))
    throw Error("TASK_CONTEXT_INVALID");
  const receipt={schemaVersion:1,kind:"PRP_STAGING_READ_SMOKE_RECEIPT",
    source:"github_task_candidate",repository:"micor-cjj-spec/matrix-prp",
    issue:396,requestCommentId:gate.requestCommentId,runId:env.GITHUB_RUN_ID,
    runAttempt:1,workflowSha:env.GITHUB_SHA,operation:"READ_SMOKE_ONLY",
    state:"BLOCKED_RUNNER",report:null,apiPassed:0,checksExecuted:0,
    liveVerified:false,deploymentAuthorized:false,productionAuthorized:false};
  try{
    const result=await executeApprovedSmoke({args:["--run-approved-staging-smoke"],
      env,transport,signalFor,now});
    const summary=reviewSmokeReport(result.report,"operator_report_unverified");
    receipt.state=summary.state;
    receipt.report=result.report;
    receipt.apiPassed=summary.apiPassed;
    receipt.checksExecuted=summary.checksExecuted;
  }catch{/* No exception messages or payloads in public output. */}
  return receipt;
}
async function main(){
  const env=process.env;
  const filename=env.GITHUB_EVENT_PATH;
  if(!filename||fs.statSync(filename).size>1024*1024)throw Error("TASK_CONTEXT_INVALID");
  const event=JSON.parse(fs.readFileSync(filename,"utf8"));
  const receipt=await executeTask({event,env,transport:(url,opts)=>fetch(url,opts),
    signalFor:ms=>AbortSignal.timeout(ms)});
  // Single machine-readable line; correlate with GitHub run and exact preflight comment.
  console.log("PRP_UAT_RECEIPT="+JSON.stringify(receipt));
  if(receipt.state!=="API_SMOKE_PASS")process.exitCode=receipt.state==="BLOCKED_RUNNER"?2:1;
}
module.exports={executeTask};
if(require.main===module)main().catch(()=>{console.error("TASK_REQUEST_BLOCKED");process.exitCode=2;});
