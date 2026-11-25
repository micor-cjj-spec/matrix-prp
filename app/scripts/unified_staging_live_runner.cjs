// #396: opt-in, test-host-only candidate. Do not run against a live host without separate approval.
const {runUnifiedReadSmoke}=require("./unified_staging_read_smoke.cjs");
const {reviewSmokeReport}=require("./unified_staging_smoke_review.cjs");
const TARGET="https://prp-test.micor.top";
const FLAG="--run-approved-staging-smoke";
function configFrom(args,env){
  if(args.length!==1||args[0]!==FLAG)throw Error("BLOCKED_EXPLICIT_OPT_IN_REQUIRED");
  if(env.NODE_TLS_REJECT_UNAUTHORIZED==="0")throw Error("BLOCKED_TLS_DISABLED");
  const username=env.PRP_STAGE_UAT_USER;
  const password=env.PRP_STAGE_UAT_PASSWORD;
  const owner=env.PRP_STAGE_UAT_OWNER_ID;
  if(typeof username!=="string"||!/^prp_uat_[a-z0-9_]{1,24}$/.test(username)||
     typeof password!=="string"||password.length<12||password.length>128||
     typeof owner!=="string"||!/^([1-9][0-9]{0,14})$/.test(owner))
    throw Error("BLOCKED_TEST_CREDENTIAL_CONFIG");
  return {username,password,ownerId:Number(owner)};
}
function isExpectedUser(user,identity){
  return user!==null&&typeof user==="object"&&user.username===identity.username&&
    user.id===identity.ownerId&&user.administrator===false;
}
function jsonType(res){
  return /^application\/(?:[\w.+-]*\+)?json(?:\s*;|$)/i.test(res.headers.get("content-type")||"");
}
async function executeApprovedSmoke({args,env,transport,signalFor,now=new Date()}){
  const identity=configFrom(args,env);
  const common={redirect:"error",credentials:"omit",cache:"no-store",referrerPolicy:"no-referrer"};
  let token;
  try{
    const response=await transport(TARGET+"/api/auth/login",{
      ...common,method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json"},
      body:JSON.stringify({username:identity.username,password:identity.password}),signal:signalFor(8000)
    });
    if(response.status!==200||!jsonType(response))throw Error("LOGIN");
    const body=await response.json(), data=body?.data;
    if(body?.code!=="SUCCESS"||!isExpectedUser(data?.user,identity)||
       data.tokenType!=="Bearer"||typeof data.expiresInSeconds!=="number"||data.expiresInSeconds<=0||
       typeof data.token!=="string"||data.token.length>8192||!/^[-_a-zA-Z0-9]+\.[-_a-zA-Z0-9]+\.[-_a-zA-Z0-9]+$/.test(data.token))
      throw Error("IDENTITY");
    token=data.token;
  }catch{throw Error("BLOCKED_LOGIN_OR_TEST_IDENTITY");}
  const report=await runUnifiedReadSmoke({
    origin:TARGET,pathname:"/prp/",confirmTest:()=>true,readToken:()=>token,signalFor,now,
    request:async(url,opts)=>{
      // No additional login, POST, arbitrary hosts, redirects or provider calls from the core.
      if(!url.startsWith(TARGET+"/api/")||opts.method!=="GET"||opts.body!==undefined||opts.redirect!=="error"||
         opts.credentials!=="omit"||opts.headers.Authorization!=="Bearer "+token)throw Error("BOUNDARY");
      const res=await transport(url,opts);
      if(url===TARGET+"/api/users/me"&&res.status===200&&jsonType(res)){
        const body=await res.json();
        // Do not permit any business GET until the independent /me response matches the designated identity.
        if(body?.code!=="SUCCESS"||!isExpectedUser(body.data,identity))throw Error("IDENTITY");
        return {status:res.status,headers:res.headers,json:async()=>body};
      }
      return res;
    }
  });
  return {report,summary:reviewSmokeReport(report,"operator_report_unverified")};
}
module.exports={executeApprovedSmoke,configFrom};
if(require.main===module){
  // The flag is an operator acknowledgement, NOT a trusted approval receipt. A separately approved
  // runner and identity are required. No live mode is connected to any workflow in this candidate.
  executeApprovedSmoke({args:process.argv.slice(2),env:process.env,
    transport:(url,opts)=>fetch(url,opts),signalFor:ms=>AbortSignal.timeout(ms)
  }).then(({report,summary})=>{
    console.log(JSON.stringify({report,summary},null,2));
    if(summary.state!=="API_SMOKE_PASS")process.exitCode=1;
  }).catch(err=>{
    const allowed=["BLOCKED_EXPLICIT_OPT_IN_REQUIRED","BLOCKED_TLS_DISABLED","BLOCKED_TEST_CREDENTIAL_CONFIG","BLOCKED_LOGIN_OR_TEST_IDENTITY"];
    console.error(allowed.includes(err?.message)?err.message:"BLOCKED_RUNNER_ERROR");
    process.exitCode=2;
  });
}
