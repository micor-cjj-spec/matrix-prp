const test=require("node:test"),assert=require("node:assert/strict");
const {executeTask}=require("./unified_staging_task_receipt.cjs");
function fixture(){
  const event={action:"created",repository:{id:1261866723,full_name:"micor-cjj-spec/matrix-prp",default_branch:"main",owner:{id:123868412}},
    issue:{number:396,state:"open"},comment:{id:123456,body:"/prp-uat-smoke",author_association:"OWNER",user:{id:123868412,type:"User"}},sender:{id:123868412}};
  const env={GITHUB_EVENT_NAME:"issue_comment",GITHUB_REF:"refs/heads/main",GITHUB_REPOSITORY:"micor-cjj-spec/matrix-prp",GITHUB_REPOSITORY_ID:"1261866723",GITHUB_ACTOR_ID:"123868412",GITHUB_RUN_ATTEMPT:"1",GITHUB_RUN_ID:"45500000000",GITHUB_SHA:"a".repeat(40),
    PRP_STAGING_UAT_ENABLED:"true",PRP_STAGE_UAT_USER:"prp_uat_fixture",PRP_STAGE_UAT_PASSWORD:"SYNTHETIC_PASSWORD",PRP_STAGE_UAT_OWNER_ID:"7"};
  const user={id:7,username:env.PRP_STAGE_UAT_USER,administrator:false},token="synthetic.fixture.signature";
  const calls=[];
  const transport=async(url,opts)=>{
    calls.push({url,opts});const p=new URL(url).pathname;
    const data=p==="/api/auth/login"?{user,token,tokenType:"Bearer",expiresInSeconds:600}:p==="/api/users/me"?user:
      ["/api/modules/domains","/api/wellness/summary/nutrition-trends","/api/video/folders","/api/practice/subjects","/api/goals"].includes(p)?[]:{};
    return {status:200,headers:{get:()=>"application/json"},json:async()=>({code:"SUCCESS",data})};
  };
  return {args:{event,env,transport,signalFor:()=>undefined,now:new Date("2026-11-25T00:00:00Z")},calls};
}
test("admitted request binds run, SHA, comment and redacted actual-shaped report",async()=>{
  const {args,calls}=fixture(),r=await executeTask(args);
  assert.equal(r.state,"API_SMOKE_PASS");assert.equal(r.apiPassed,9);assert.equal(r.checksExecuted,11);
  assert.equal(r.requestCommentId,123456);assert.equal(r.runId,"45500000000");assert.equal(r.workflowSha,"a".repeat(40));
  assert.equal(calls.length,12);assert.equal(calls[0].opts.method,"POST");assert.ok(calls.slice(1).every(c=>c.opts.method==="GET"));
  assert.equal(r.liveVerified,false);assert.equal(r.deploymentAuthorized,false);assert.equal(r.productionAuthorized,false);
  for(const secret of [args.env.PRP_STAGE_UAT_PASSWORD,args.env.PRP_STAGE_UAT_USER,"synthetic.fixture.signature"])assert.ok(!JSON.stringify(r).includes(secret));
});
test("denied requester or malformed run metadata never accesses transport",async()=>{
  for(const mutate of [x=>x.event.sender.id=1,x=>x.event.comment.body="OTHER",x=>x.env.GITHUB_RUN_ATTEMPT="2",x=>x.env.GITHUB_SHA="bad",x=>x.env.GITHUB_RUN_ID="0"]){
    const {args,calls}=fixture();mutate(args);await assert.rejects(executeTask(args),/TASK_/);assert.equal(calls.length,0);
  }
});
test("failed login has correlated blocked receipt, no raw error",async()=>{
  const {args}=fixture();let calls=0;args.transport=async()=>{calls++;throw Error("PRIVATE_RESPONSE")};
  const r=await executeTask(args);assert.equal(calls,1);assert.equal(r.state,"BLOCKED_RUNNER");assert.equal(r.report,null);assert.equal(r.requestCommentId,123456);assert.ok(!JSON.stringify(r).includes("PRIVATE_RESPONSE"));
});
test("partial API error retained only as reviewed ordinal status",async()=>{
  const {args}=fixture(),original=args.transport;args.transport=async(url,opts)=>url.endsWith("/api/tasks/summary")?{status:503}:original(url,opts);
  const r=await executeTask(args);assert.equal(r.state,"API_SMOKE_INCOMPLETE");assert.equal(r.apiPassed,8);assert.equal(r.checksExecuted,11);assert.equal(r.report.cases.find(c=>c.id==="U03").checks[0].result,"HTTP_503");
});

test("explicit activation defaults off and fails before network",async()=>{
  for(const value of [undefined,"","false","TRUE","1"]){
    const {args,calls}=fixture();args.env.PRP_STAGING_UAT_ENABLED=value;
    await assert.rejects(executeTask(args),/TASK_EXECUTION_DISABLED/);assert.equal(calls.length,0);
  }
});
