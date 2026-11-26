// Issue #396: read-only API smoke; not browser UAT or permission to deploy.
async function runUnifiedReadSmoke({origin,pathname,confirmTest,readToken,request,signalFor,now=new Date()}) {
  const target="https://prp-test.micor.top";
  if (origin!==target || !pathname.startsWith("/prp/")) return {state:"BLOCKED_WRONG_ORIGIN",cases:[]};
  if (!confirmTest()) return {state:"BLOCKED_TEST_IDENTITY_NOT_CONFIRMED",cases:[]};
  const token=readToken();
  if(typeof token!=="string" || !token || /[\r\n]/.test(token)) return {state:"BLOCKED_NO_SESSION",cases:[]};
  const date=new Date(now.getTime()+8*3600000).toISOString().slice(0,10);
  const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
  const array=Array.isArray;
  const groups=[
    ["U09",[["/users/me",v=>object(v)&&v.id!=null&&typeof v.username==="string"]]],
    ["U01",[["/dashboard/summary",object]]],
    ["U02",[["/modules/domains",array]]],
    ["U03",[["/tasks/summary",object]]],
    ["U04",[[`/wellness/summary/daily?date=${date}`,object],["/wellness/summary/nutrition-trends?days=7",array]]],
    ["U05",[[`/finance/summary/monthly?month=${date.slice(0,7)}`,object]]],
    ["U06",[["/video/folders",array],["/practice/subjects",array]]],
    ["U07",[["/goals",array]]],
    ["U08",[["/ai/conversations/page?limit=1",object]]]
  ];
  const cases=[];
  let stopped=false;
  for(const [id,checks] of groups){
    if(stopped){cases.push({id,state:"PENDING",checks:[]});continue;}
    const results=[];
    for(let i=0;i<checks.length;i++){
      const [path,valid]=checks[i];
      let status;
      try {
        const res=await request(target+"/api"+path,{method:"GET",headers:{Authorization:"Bearer "+token,Accept:"application/json"},redirect:"error",credentials:"omit",cache:"no-store",referrerPolicy:"no-referrer",signal:signalFor(8000)});
        if(res.status!==200){status="HTTP_"+res.status; if([401,429].includes(res.status))stopped=true;}
        else if(!/^application\/(?:[\w.+-]*\+)?json(?:\s*;|$)/i.test(res.headers.get("content-type")||"")) status="NOT_JSON";
        else {
          const body=await res.json();
          status=body?.code==="SUCCESS"&&valid(body.data)?"OK":"RESPONSE_CONTRACT_MISMATCH";
        }
      } catch { status="REQUEST_FAILED"; }
      results.push({check:i+1,result:status});
      if(stopped||status!=="OK"&&id==="U09"){stopped=true;break;}
    }
    cases.push({id,state:results.length===checks.length&&results.every(x=>x.result==="OK")?"API_PASS":"REVIEW_REQUIRED",checks:results});
  }
  return {state:cases.every(x=>x.state==="API_PASS")?"API_SMOKE_PASS":"API_SMOKE_INCOMPLETE",cases:cases.sort((a,b)=>a.id.localeCompare(b.id))};
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = {runUnifiedReadSmoke};
} else {
  void runUnifiedReadSmoke({
    origin: location.origin, pathname: location.pathname,
    confirmTest: () => confirm("Confirm this is the designated synthetic test account, not a production or personal account. Run GET-only smoke?"),
    readToken: () => localStorage.getItem("matrix-prp-token"),
    request: (url, opts) => fetch(url, opts),
    signalFor: ms => AbortSignal.timeout(ms)
  }).then(report => console.log(JSON.stringify(report, null, 2))).catch(() => console.log("BLOCKED_LOCAL_RUNTIME"));
}
