const test=require("node:test");
const assert=require("node:assert/strict");
const {runUnifiedReadSmoke}=require("./unified_staging_read_smoke.cjs");
function fixture(overrides={}) {
  const calls=[];
  const cfg={origin:"https://prp-test.micor.top",pathname:"/prp/",confirmTest:()=>true,readToken:()=>"SYNTHETIC_TOKEN",signalFor:()=>undefined,now:new Date("2026-11-25T18:00:00Z"),request:async(url,opts)=>{
    calls.push({url,opts});const p=url.slice("https://prp-test.micor.top".length).split("?")[0];
    const data=p==="/api/users/me"?{id:7,username:"synthetic"}:["/api/modules/domains","/api/wellness/summary/nutrition-trends","/api/video/folders","/api/practice/subjects","/api/goals"].includes(p)?[]:{};
    return {status:200,headers:{get:()=>"application/json"},json:async()=>({code:"SUCCESS",data})};
  },...overrides};return {cfg,calls};
}
test("nine API groups, fixed same-origin GETs, no token in report",async()=>{const {cfg,calls}=fixture();const result=await runUnifiedReadSmoke(cfg);assert.equal(result.state,"API_SMOKE_PASS");assert.equal(result.cases.length,9);assert.equal(calls.length,11);assert.ok(calls.every(c=>c.url.startsWith(cfg.origin+"/api/")&&c.opts.method==="GET"&&c.opts.redirect==="error"&&c.opts.credentials==="omit"&&!c.opts.body));assert.ok(calls.some(c=>c.url.endsWith("date=2026-11-26")));assert.ok(!JSON.stringify(result).includes("SYNTHETIC_TOKEN"));});
test("wrong origin and path never read token or request",async()=>{for(const [origin,pathname] of [["https://micor.top","/prp/"],["https://prp-test.micor.top","/other"],["https://prp-test.micor.top.evil.example","/prp/"]]){const {cfg}=fixture({origin,pathname,readToken:()=>{throw Error("must not read")},request:()=>{throw Error("must not request")}});assert.equal((await runUnifiedReadSmoke(cfg)).state,"BLOCKED_WRONG_ORIGIN");}});
test("declined test identity never reads token",async()=>{const {cfg}=fixture({confirmTest:()=>false,readToken:()=>{throw Error("must not read")}});assert.equal((await runUnifiedReadSmoke(cfg)).state,"BLOCKED_TEST_IDENTITY_NOT_CONFIRMED");});
test("missing session blocks",async()=>{const {cfg,calls}=fixture({readToken:()=>null});assert.equal((await runUnifiedReadSmoke(cfg)).state,"BLOCKED_NO_SESSION");assert.equal(calls.length,0);});
test("401 halts before business endpoints",async()=>{let n=0;const {cfg}=fixture({request:async()=>{n++;return {status:401}}});const r=await runUnifiedReadSmoke(cfg);assert.equal(n,1);assert.equal(r.cases.filter(x=>x.state==="PENDING").length,8);});
test("unexpected JSON gate stops",async()=>{let n=0;const {cfg}=fixture({request:async()=>{n++;return {status:200,headers:{get:()=>"application/json"},json:async()=>({code:"FAIL",data:{secret:"PRIVATE"}})}}});const r=await runUnifiedReadSmoke(cfg);assert.equal(n,1);assert.ok(!JSON.stringify(r).includes("PRIVATE"));});
test("redirect/network failure does not expose error",async()=>{const {cfg}=fixture({request:async()=>{throw Error("PRIVATE")}});const r=await runUnifiedReadSmoke(cfg);assert.equal(r.state,"API_SMOKE_INCOMPLETE");assert.ok(!JSON.stringify(r).includes("PRIVATE"));});
