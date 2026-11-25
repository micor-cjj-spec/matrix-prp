// #396: pure request admission predicate. Not a live trigger or authorization system.
const fs=require("node:fs");
const REPO="micor-cjj-spec/matrix-prp", REPO_ID=1261866723, OWNER_ID=123868412;
const COMMAND="/prp-uat-smoke";
function admit(event,context){
  const reject=reason=>({admitted:false,reason});
  if(context?.eventName!=="issue_comment"||context.ref!=="refs/heads/main"||
     context.repository!==REPO||context.repositoryId!==String(REPO_ID)||
     context.actorId!==String(OWNER_ID)||context.runAttempt!=="1")
    return reject("CONTEXT_MISMATCH");
  if(event?.action!=="created"||event.repository?.id!==REPO_ID||
     event.repository.full_name!==REPO||event.repository.owner?.id!==OWNER_ID||
     event.repository.default_branch!=="main")return reject("REPOSITORY_OR_EVENT_MISMATCH");
  if(event.issue?.number!==396||event.issue.state!=="open"||
     Object.hasOwn(event.issue,"pull_request"))return reject("ISSUE_MISMATCH");
  const c=event.comment;
  if(!c||c.user?.id!==OWNER_ID||c.user.type!=="User"||
     c.author_association!=="OWNER"||event.sender?.id!==OWNER_ID)
    return reject("REQUESTER_MISMATCH");
  if(c.body!==COMMAND||!Number.isSafeInteger(c.id)||c.id<=0)
    return reject("COMMAND_MISMATCH");
  return {admitted:true,issue:396,requestCommentId:c.id,operation:"READ_SMOKE_ONLY"};
}
function main(){
  try{
    const env=process.env;
    const filename=env.GITHUB_EVENT_PATH;
    if(!filename||fs.statSync(filename).size>1024*1024)throw Error();
    const event=JSON.parse(fs.readFileSync(filename,"utf8"));
    const result=admit(event,{eventName:env.GITHUB_EVENT_NAME,ref:env.GITHUB_REF,
      repository:env.GITHUB_REPOSITORY,repositoryId:env.GITHUB_REPOSITORY_ID,
      actorId:env.GITHUB_ACTOR_ID,runAttempt:env.GITHUB_RUN_ATTEMPT});
    console.log(JSON.stringify(result));
    if(!result.admitted)process.exitCode=2;
  }catch{console.error("REQUEST_EVENT_INVALID");process.exitCode=2;}
}
module.exports={admit};
if(require.main===module)main();
