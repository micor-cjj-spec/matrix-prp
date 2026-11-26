const test=require("node:test");
const assert=require("node:assert/strict");
const {executeApprovedSmoke}=require("./unified_staging_live_runner.cjs");
const args=["--run-approved-staging-smoke"];
const env={PRP_STAGE_UAT_USER:"prp_uat_fixture",PRP_STAGE_UAT_PASSWORD:"SYNTHETIC_PASSWORD",PRP_STAGE_UAT_OWNER_ID:"7"};
const user={id:7,username:"prp_uat_fixture",administrator:false};
const token="synthetic.fixture.signature";
const response=(data,status=200)=>({status,headers:{get:()=>"application/json"},json:async()=>({code:"SUCCESS",data})});
function fixture(overrides={}){
  const calls=[];
  const config={args,env,signalFor:()=>undefined,now:new Date("2026-11-25T00:00:00Z"),transport:async(url,opts)=>{
    calls.push({url,opts});
    const p=new URL(url).pathname;
    if(p==="/api/auth/login")return response({user,token,tokenType:"Bearer",expiresInSeconds:600});
    if(p==="/api/users/me")return response(user);
    return response(["/api/modules/domains","/api/wellness/summary/nutrition-trends","/api/video/folders","/api/practice/subjects","/api/goals"].includes(p)?[]:{});
  },...overrides};
  return {config,calls};
}
test("fixed staging origin, one login, eleven GETs, no credential output",async()=>{
  const {config,calls}=fixture(),out=await executeApprovedSmoke(config);
  assert.equal(out.summary.apiPassed,9);assert.equal(calls.length,12);
  assert.ok(calls.every(c=>c.url.startsWith("https://prp-test.micor.top/api/")&&c.opts.redirect==="error"&&c.opts.credentials==="omit"));
  assert.equal(calls[0].opts.method,"POST");assert.equal(calls[0].url,"https://prp-test.micor.top/api/auth/login");
  assert.equal(calls[0].opts.headers.Authorization,undefined);
  assert.ok(calls.slice(1).every(c=>c.opts.method==="GET"&&c.opts.body===undefined&&c.opts.headers.Authorization==="Bearer "+token));
  assert.equal(out.summary.liveVerified,false);
  for(const secret of [env.PRP_STAGE_UAT_PASSWORD,token,user.username])assert.ok(!JSON.stringify(out).includes(secret));
});
test("explicit opt-in and safe configuration fail before network",async()=>{
  for(const override of [{args:[]},{args:[...args,"extra"]},{env:{...env,NODE_TLS_REJECT_UNAUTHORIZED:"0"}},{env:{...env,PRP_STAGE_UAT_USER:"admin"}},{env:{...env,PRP_STAGE_UAT_OWNER_ID:"0"}},{env:{...env,PRP_STAGE_UAT_PASSWORD:""}}]){
    const {config,calls}=fixture(override);await assert.rejects(executeApprovedSmoke(config),/BLOCKED_/);assert.equal(calls.length,0);
  }
});
test("login mismatch, admin or invalid token stops before GET",async()=>{
  for(const data of [{user:{...user,id:8},token},{user:{...user,administrator:true},token},{user,token:"malformed"}]){
    let n=0;const {config}=fixture({transport:async()=>{n++;return response({...data,tokenType:"Bearer",expiresInSeconds:600})}});
    await assert.rejects(executeApprovedSmoke(config),/BLOCKED_LOGIN_OR_TEST_IDENTITY/);assert.equal(n,1);
  }
});
test("me mismatch stops before business reads",async()=>{
  for(const altered of [{...user,id:8},{...user,administrator:true}]){
    let n=0;const {config}=fixture({transport:async()=>++n===1?response({user,token,tokenType:"Bearer",expiresInSeconds:600}):response(altered)});
    const out=await executeApprovedSmoke(config);assert.equal(n,2);assert.equal(out.summary.pending,8);assert.equal(out.summary.apiPassed,0);
  }
});
test("failed login no retry, no server error leakage",async()=>{
  let n=0;const {config}=fixture({transport:async()=>{n++;throw Error("PRIVATE")}});await assert.rejects(executeApprovedSmoke(config),{message:"BLOCKED_LOGIN_OR_TEST_IDENTITY"});assert.equal(n,1);
});
