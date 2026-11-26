"""CI-only official Grafana MCP product probe; never a deployment or MCP server."""
import base64
import datetime
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

P1="e8e5536f3d0dcdd2852f597a0402529332c24f42"
P2="ee34a882c5a1a2296303a1a751a7869eb661b760"
P3="b0c0521bf345231ac1562db66ef92746828466e3"
AUTH="329ca6eb024ca3486e711fabc0ad2c428cde6221"
SDK="3e7e3afcc8fd2ee5750a76bf3ff579c9f9fe6393"
IMAGES={"prom":"quay.io/prometheus/prometheus@sha256:aafa9d694e6a883c02db516d9f6e5b84e14195f49a2a6456a4cca815edda72b9",
        "python":"python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89",
        "grafana":"grafana/grafana:13.3.2","mcp":"grafana/mcp-grafana:2.4.0"}
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
UID="prp-synthetic"
CASES=[]

def run(*args, timeout=120):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        if args[:2]==("docker","pull"):
            print("OBS_P4_IMAGE_PULL_FAILED="+args[-1]+"|"+p.stderr[-500:],flush=True)
        raise RuntimeError("command failed: "+args[0]+" "+args[1])
    return p.stdout.strip()

def check(value,label):
    if not value:
        raise AssertionError(label)
    CASES.append(label)
    print("OBS_P4_CASE="+label+":PASS",flush=True)

def exact(ref,path,blob=None):
    actual=run("git","rev-parse",ref+":"+path)
    if blob and actual!=blob:
        raise AssertionError("source blob changed: "+path)
    return subprocess.check_output(["git","show",ref+":"+path])

def request(base,path,method="GET",data=None,headers=None):
    h={"Accept":"application/json",**(headers or {})}
    raw=None if data is None else json.dumps(data).encode()
    if raw is not None:
        h["Content-Type"]="application/json"
    req=urllib.request.Request(base+path,raw,h,method=method)
    try:
        with OPENER.open(req,timeout=15) as resp:
            body=resp.read(262145)
            if len(body)>262144:
                raise AssertionError("response bound")
            return resp.status,dict(resp.headers.items()),body
    except urllib.error.HTTPError as exc:
        return exc.code,dict(exc.headers.items()),exc.read(65536)

def api(base,path,method="GET",data=None,headers=None):
    code,_,body=request(base,path,method,data,headers)
    if code not in (200,201,202):
        raise ValueError("HTTP "+str(code))
    return json.loads(body) if body else {}

def eventually(fn,label,seconds=90):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            if fn():
                return
        except (OSError,ValueError,KeyError,RuntimeError):
            pass
        time.sleep(1)
    raise AssertionError("timeout: "+label)

class Client:
    """Test-only HTTP client for the upstream implementation, no server."""
    def __init__(self,base,caller,viewer):
        self.base=base
        self.headers={"Authorization":"Bearer "+caller,
                      "X-Grafana-Service-Account-Token":viewer,
                      "Accept":"application/json, text/event-stream","Host":"mcp:8000"}
        self.seq=0
    def rpc(self,method,params=None,notify=False,extra=None,omit=()):
        self.seq+=1
        message={"jsonrpc":"2.0","method":method}
        if not notify:
            message["id"]=self.seq
        if params is not None:
            message["params"]=params
        headers={k:v for k,v in self.headers.items() if k not in omit}
        code,h,body=request(self.base,"/mcp","POST",message,{**headers,**(extra or {})})
        if code not in (200,202):
            return {"http":code}
        session=next((v for k,v in h.items() if k.lower()=="mcp-session-id"),None)
        if session:
            self.headers["Mcp-Session-Id"]=session
        if notify:
            return {"http":code}
        if "text/event-stream" in next((v for k,v in h.items() if k.lower()=="content-type"),""):
            messages=[json.loads(x[5:].strip()) for x in body.decode().splitlines() if x.startswith("data:")]
            message=next((m for m in messages if m.get("id")==self.seq),None)
        else:
            message=json.loads(body)
        if not isinstance(message,dict) or message.get("id")!=self.seq:
            raise AssertionError("RPC correlation")
        return message
    def init(self):
        response=self.rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},
                                  "clientInfo":{"name":"prp-p4-ci","version":"1"}})
        self.headers["MCP-Protocol-Version"]=response["result"]["protocolVersion"]
        check(self.rpc("notifications/initialized",notify=True).get("http") in (200,202),"mcp-initialized")
    def call(self,expr,uid=UID,**kwargs):
        args={"datasourceUid":uid,"expr":expr,"queryType":"instant","startTime":"now",**kwargs}
        return self.rpc("tools/call",{"name":"query_prometheus","arguments":args})

def failed(response):
    return ("error" in response or response.get("http",0)>=400
            or response.get("result",{}).get("isError") is True)

def serialized(response):
    return json.dumps(response,separators=(",",":"))

def main():
    if os.getenv("GITHUB_ACTIONS")!="true" or os.getenv("RUNNER_ENVIRONMENT")!="github-hosted":
        raise SystemExit("disposable hosted CI only")
    prefix="p41-"+uuid.uuid4().hex[:10]
    names={key:prefix+"-"+key for key in ("prom","p2","p3","grafana","mcp")}
    password=secrets.token_urlsafe(32)
    caller=secrets.token_urlsafe(32)
    admin={"Authorization":"Basic "+base64.b64encode(("admin:"+password).encode()).decode()}
    refs={}
    created=[]
    network=False
    with tempfile.TemporaryDirectory(prefix="p41-") as directory:
        folder=Path(directory)
        folder.chmod(0o755)
        def write(name,data):
            path=folder/name
            path.write_bytes(data if isinstance(data,bytes) else json.dumps(data).encode())
            path.chmod(0o644)
            return path
        write("p2.py",exact(P2,"app/observability/integration/fixture.py","532f0dda888d5410ff64db168890436ba6d79ee2"))
        p2config=json.loads(exact(P2,"app/observability/integration/prometheus.yml","d82f0238c6b5699495203aca88911ef73b7a6cd9"))
        write("p3.py",exact(P3,"app/observability/p3/fixture.py","0384dee80ac635397b8dcc9170bfecce513773cf"))
        rules=json.loads(exact(P3,"app/observability/p3/rules.yml"))
        source=json.loads(exact(P3,"app/observability/p3/source-contract.json","7dab6df72232249b2775dac6bfe2775cf4025772"))
        check(source["p2"]["head"]==P2 and source["p1"]["head"]==P1,"source-contract")
        check(len(rules["groups"][0]["rules"])==13,"exact-p3-rules")
        write("rules.yml",rules)
        write("state.json",{"node":True})
        jobs=[]
        app=next(x for x in p2config["scrape_configs"] if x["job_name"]=="p2-app")
        jobs.append(app)
        for job in ("node","http_health","https_health","p2-mysql","p2-nginx","p2-ci","p2-cgroup","p2-keycloak"):
            jobs.append({"job_name":job,"metrics_path":"/metrics/"+job,"sample_limit":250,
                         "static_configs":[{"targets":["p3:8080"],"labels":{"environment":"synthetic","instance":"fixture-"+job}}]})
        jobs.append({"job_name":"foreign-marker","metrics_path":"/metrics/node","sample_limit":250,
                     "static_configs":[{"targets":["p3:8080"],"labels":{"environment":"foreign","instance":"foreign-marker"}}]})
        write("prom.yml",{"global":{"scrape_interval":"2s","scrape_timeout":"1s","evaluation_interval":"2s"},
                          "rule_files":["/fixture/rules.yml"],"scrape_configs":jobs})
        try:
            for key,tag in IMAGES.items():
                run("docker","pull","--platform","linux/amd64",tag,timeout=300)
                image=json.loads(run("docker","image","inspect",tag))[0]
                check(image["Os"]=="linux" and image["Architecture"]=="amd64" and bool(image["RepoDigests"]),"image-"+key)
                refs[key]=image["Id"]
                print("OBS_P4_IMAGE="+key+"|"+tag+"|"+image["RepoDigests"][0]+"|"+image["Id"],flush=True)
            run("docker","network","create","--internal",prefix)
            network=True
            def start(key,image,mem,options=(),args=(),alias=None):
                created.append(names[key])
                run("docker","run","-d","--pull","never","--name",names[key],"--network",prefix,
                    "--network-alias",alias or key,"--memory",mem,"--memory-swap",mem,
                    "--cpus","0.75","--pids-limit","128","--cap-drop","ALL",
                    "--security-opt","no-new-privileges",*options,refs[image],*args)
            def mount(path,dest):
                return ("--mount","type=bind,src="+str(path)+",dst="+dest+",readonly")
            start("p2","python","128m",mount(folder/"p2.py","/fixture/p2.py"),("python","/fixture/p2.py","app"),"app")
            start("p3","python","128m",mount(folder,"/control"),("python","/control/p3.py","metrics"))
            start("prom","prom","384m",mount(folder,"/fixture"),
                  ("--config.file=/fixture/prom.yml","--storage.tsdb.retention.time=1h",
                   "--storage.tsdb.retention.size=128MB","--query.timeout=5s","--query.max-concurrency=2","--query.max-samples=10000"))
            start("grafana","grafana","384m",("-e","GF_SECURITY_ADMIN_PASSWORD="+password,
                  "-e","GF_AUTH_ANONYMOUS_ENABLED=false","-e","GF_ANALYTICS_REPORTING_ENABLED=false",
                  "-e","GF_ANALYTICS_CHECK_FOR_UPDATES=false","-e","GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false"))
            def address(key,port):
                n=json.loads(run("docker","inspect",names[key]))[0]
                if set(n["NetworkSettings"]["Networks"])!={prefix} or n["HostConfig"]["PortBindings"]:
                    raise AssertionError("network scope")
                return "http://"+n["NetworkSettings"]["Networks"][prefix]["IPAddress"]+":"+str(port)
            prom=address("prom",9090); graf=address("grafana",3000)
            eventually(lambda:api(graf,"/api/health").get("database")=="ok","grafana")
            def prom_query(expr):
                return api(prom,"/api/v1/query?query="+urllib.parse.quote(expr))["data"]["result"]
            eventually(lambda:len(prom_query('node_memory_MemAvailable_bytes'))==2,"positive and foreign series")
            check(any(x["metric"].get("environment")=="foreign" for x in prom_query("node_memory_MemAvailable_bytes")),"foreign-positive-control")
            eventually(lambda:bool(prom_query('jvm_threads_live_threads{job="p2-app"}')),"exact-p2-fixture")
            check(True,"p2-p3-source-scrape")
            api(graf,"/api/datasources","POST",{"name":"PRP synthetic only","uid":UID,
                 "type":"prometheus","url":"http://prom:9090","access":"proxy","isDefault":True},admin)
            account=api(graf,"/api/serviceaccounts","POST",{"name":"p41-viewer","role":"Viewer"},admin)["id"]
            token=api(graf,f"/api/serviceaccounts/{account}/tokens","POST",{"name":"p41-ephemeral","secondsToLive":600},admin)
            viewer=token["key"]
            viewer_header={"Authorization":"Bearer "+viewer}
            check(len(api(graf,"/api/datasources",headers=viewer_header))==1,"one-datasource")
            check(request(graf,"/api/datasources","POST",{"name":"denied","type":"prometheus","url":"http://prom:9090"},viewer_header)[0] in (401,403),"viewer-write-denied")
            start("mcp","mcp","256m",("-e","GRAFANA_URL=http://grafana:3000",
                  "-e","MCP_GRAFANA_SERVER_TOKEN="+caller,"-e","GRAFANA_USAGE_STATS=disabled"),
                  ("-t","streamable-http","--address","0.0.0.0:8000","--allowed-hosts","mcp:8000",
                   "--enabled-tools","prometheus","--disable-write","--disable-api","--disable-rendering",
                   "--disable-assistant","--require-user-credentials","--log-tool-calls",
                   "--prometheus-enforced-matchers",'environment="synthetic"',
                   "--prometheus-guardrail-mode","enforce","--prometheus-guardrail-max-range","1h",
                   "--prometheus-guardrail-max-points","120"))
            mcp=address("mcp",8000)
            eventually(lambda:request(mcp,"/healthz",headers={"Host":"mcp:8000"})[0] in (200,401),"mcp readiness")
            client=Client(mcp,caller,viewer)
            check(client.rpc("initialize",{},omit=("Authorization",)).get("http")==401,"caller-auth-required")
            check(client.rpc("initialize",{},omit=("X-Grafana-Service-Account-Token",)).get("http")==401,"per-user-credential-required")
            client.init()
            catalog=client.rpc("tools/list")["result"]
            check(not catalog.get("nextCursor"),"complete-tool-discovery")
            tools={t["name"] for t in catalog["tools"]}
            permitted={"query_prometheus","query_prometheus_histogram","list_prometheus_metric_names",
                       "list_prometheus_metric_metadata","list_prometheus_label_names","list_prometheus_label_values"}
            check("query_prometheus" in tools and tools<=permitted,"prometheus-only-tools")
            print("OBS_P4_TOOLS="+",".join(sorted(tools)),flush=True)
            response=client.call("node_memory_MemAvailable_bytes")
            value=serialized(response)
            check(not failed(response) and "fixture-node" in value and "foreign-marker" not in value,"enforced-label-scope")
            check(not failed(client.call('jvm_threads_live_threads{job="p2-app"}')),"p2-query")
            denied=client.call('node_memory_MemAvailable_bytes{environment="foreign"}')
            check("foreign-marker" not in serialized(denied),"foreign-selector-not-disclosed")
            check(failed(client.call("node_memory_MemAvailable_bytes","missing-datasource")),"unknown-datasource-rejected")
            check(failed(client.call("node_memory_MemAvailable_bytes[2h]")),"lookback-budget")
            check(failed(client.call("node_memory_MemAvailable_bytes",queryType="range",startTime="now-1h",endTime="now",stepSeconds=1)),"points-budget")
            check(failed(client.rpc("tools/call",{"name":"update_dashboard","arguments":{}})),"write-tool-not-callable")
            override=client.rpc("tools/call",{"name":"query_prometheus","arguments":{"datasourceUid":UID,"expr":"node_memory_MemAvailable_bytes","startTime":"now","queryType":"instant"}},
                                extra={"X-Grafana-URL":"http://p3:8080"})
            check(failed(override) or ("fixture-node" in serialized(override) and "foreign-marker" not in serialized(override)),"url-override-denied-or-ignored")
            invalid=client.rpc("tools/call",{"name":"query_prometheus","arguments":{"datasourceUid":UID,"expr":"node_memory_MemAvailable_bytes","startTime":"now","queryType":"instant"}},
                               extra={"X-Grafana-Service-Account-Token":"synthetic-invalid"})
            check(failed(invalid),"invalid-viewer-denied")
            # Explicitly test the documented limitation; do not claim a strict query allowlist.
            offset=client.call("node_memory_MemAvailable_bytes offset 2h")
            print("OBS_P4_OFFSET_OUTSIDE_BUDGET="+("DENIED" if failed(offset) else "ACCEPTED_NO_GO_FOR_STRICT_TIME_BOUND"),flush=True)
            for _ in range(3):
                check(not failed(client.call("node_memory_MemAvailable_bytes")),"bounded-repeat")
            stats=run("docker","stats","--no-stream","--format","{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",*created)
            check(len(stats.splitlines())==len(created),"resource-snapshot")
            print("OBS_P4_STATS="+stats.replace("\n",";"),flush=True)
            check(request(graf,f"/api/serviceaccounts/{account}/tokens/{token['id']}","DELETE",headers=admin)[0] in (200,204),"fixture-token-revoked")
            eventually(lambda:request(graf,"/api/user",headers=viewer_header)[0] in (401,403),"grafana-revoke")
            check(failed(client.call("node_memory_MemAvailable_bytes")),"mcp-existing-session-revoked")
            logs=run("docker","logs",names["mcp"]) # Docker stderr separately captured below
            p=subprocess.run(["docker","logs",names["mcp"]],capture_output=True,text=True,timeout=15)
            logs=p.stdout+p.stderr
            check(p.returncode==0 and "Tool call" in logs and "query_prometheus" in logs and "p41-viewer" in logs,"native-audit")
            check(all(s not in logs for s in (password,caller,viewer,"node_memory_MemAvailable_bytes")),"audit-no-token-or-arguments")
            check(run("docker","network","inspect","--format","{{.Internal}}",prefix)=="true","isolated-network")
            print("OBS_P4_PRODUCT_PROBE=PASS; STRICT_FIXED_QUERY_AND_OWNER_BOUNDARY=NOT_ESTABLISHED",flush=True)
        finally:
            for name in reversed(created):
                subprocess.run(["docker","rm","-f","-v",name],capture_output=True,timeout=30)
            if network:
                subprocess.run(["docker","network","rm",prefix],capture_output=True,timeout=30)

if __name__=="__main__":
    import urllib.parse
    main()
