// Offline fixture runner and untrusted operator-report review; no live transport.
const {runUnifiedReadSmoke}=require("./unified_staging_read_smoke.cjs");
function reviewSmokeReport(report,source) {
  const fail=()=>{throw new Error("INVALID_SMOKE_REPORT")};
  const exact=(v,keys)=>v!==null&&typeof v==="object"&&!Array.isArray(v)&&Object.keys(v).sort().join("|")===keys.slice().sort().join("|");
  const count={U01:1,U02:1,U03:1,U04:2,U05:1,U06:2,U07:1,U08:1,U09:1};
  const order=["U09","U01","U02","U03","U04","U05","U06","U07","U08"];
  const blocked=["BLOCKED_WRONG_ORIGIN","BLOCKED_TEST_IDENTITY_NOT_CONFIRMED","BLOCKED_NO_SESSION"];
  const validResult=v=>typeof v==="string"&&(["OK","NOT_JSON","RESPONSE_CONTRACT_MISMATCH","REQUEST_FAILED"].includes(v)||(/^HTTP_[1-5][0-9]{2}$/.test(v)&&v!=="HTTP_200"));
  if(!["offline_fixture","operator_report_unverified"].includes(source)||!exact(report,["state","cases"])||!Array.isArray(report.cases))fail();
  const out={schemaVersion:1,issue:396,source,state:report.state,apiPassed:0,reviewRequired:0,pending:9,checksExecuted:0,liveVerified:false,deploymentAuthorized:false,productionAuthorized:false};
  if(blocked.includes(report.state)){if(report.cases.length!==0)fail();return out}
  if(!["API_SMOKE_PASS","API_SMOKE_INCOMPLETE"].includes(report.state)||report.cases.length!==9)fail();
  const cases=new Map();
  for(const c of report.cases){
    if(!exact(c,["id","state","checks"])||!Object.hasOwn(count,c.id)||cases.has(c.id)||!Array.isArray(c.checks)||c.checks.length>count[c.id])fail();
    for(let i=0;i<c.checks.length;i++){const k=c.checks[i];if(!exact(k,["check","result"])||k.check!==i+1||!validResult(k.result))fail()}
    cases.set(c.id,c);
  }
  let stopped=false;
  for(const id of order){
    const c=cases.get(id);
    if(stopped){if(c.state!=="PENDING"||c.checks.length!==0)fail();continue}
    if(c.checks.length===0)fail();
    for(let i=0;i<c.checks.length;i++){
      const result=c.checks[i].result;
      if(["HTTP_401","HTTP_429"].includes(result)||(id==="U09"&&result!=="OK")){
        stopped=true;if(i!==c.checks.length-1)fail();
      }
    }
    if(c.checks.length!==count[id]&&!stopped)fail();
    const pass=c.checks.length===count[id]&&c.checks.every(k=>k.result==="OK");
    if(c.state!==(pass?"API_PASS":"REVIEW_REQUIRED"))fail();
    out.pending--;out.checksExecuted+=c.checks.length;
    if(pass)out.apiPassed++;else out.reviewRequired++;
  }
  if(report.state!==(out.apiPassed===9?"API_SMOKE_PASS":"API_SMOKE_INCOMPLETE"))fail();
  return out;
}
async function runFixture() {
  const lists=new Set(["/api/modules/domains","/api/wellness/summary/nutrition-trends","/api/video/folders","/api/practice/subjects","/api/goals"]);
  const objects=new Set(["/api/dashboard/summary","/api/tasks/summary","/api/wellness/summary/daily","/api/finance/summary/monthly","/api/ai/conversations/page"]);
  const report=await runUnifiedReadSmoke({
    origin:"https://prp-test.micor.top",pathname:"/prp/",confirmTest:()=>true,
    readToken:()=>"SYNTHETIC_ONLY",signalFor:()=>undefined,now:new Date("2026-11-25T00:00:00Z"),
    request:async (url,opts)=>{
      const u=new URL(url);
      if(u.origin!=="https://prp-test.micor.top"||opts.method!=="GET"||opts.redirect!=="error"||opts.credentials!=="omit"||opts.body!==undefined) throw new Error("FIXTURE_BOUNDARY");
      const data=u.pathname==="/api/users/me"?{id:1,username:"synthetic"}:lists.has(u.pathname)?[]:objects.has(u.pathname)?{}:null;
      if(data===null)throw new Error("UNKNOWN_FIXTURE_PATH");
      return {status:200,headers:{get:()=>"application/json"},json:async()=>({code:"SUCCESS",data})};
    }
  });
  return reviewSmokeReport(report,"offline_fixture");
}
async function main(args){
  if(args.length!==1||!["--fixture","--review-stdin"].includes(args[0]))throw new Error("USAGE");
  if(args[0]==="--fixture")return runFixture();
  let input="",bytes=0;
  process.stdin.setEncoding("utf8");
  for await(const chunk of process.stdin){bytes+=Buffer.byteLength(chunk);if(bytes>16384)throw new Error("REPORT_TOO_LARGE");input+=chunk;}
  return reviewSmokeReport(JSON.parse(input),"operator_report_unverified");
}
module.exports={reviewSmokeReport,runFixture};
if(require.main===module)main(process.argv.slice(2)).then(r=>{
  console.log(JSON.stringify(r,null,2));
  if(r.state!=="API_SMOKE_PASS")process.exitCode=1;
}).catch(()=>{console.error("INVALID_OR_UNSUPPORTED_SMOKE_REPORT");process.exitCode=2;});
