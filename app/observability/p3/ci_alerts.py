"""Real isolated Prometheus and Alertmanager lifecycle; synthetic data only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import uuid

from unit_cases import tests

HERE=Path(__file__).resolve().parent
PROM="quay.io/prometheus/prometheus@sha256:aafa9d694e6a883c02db516d9f6e5b84e14195f49a2a6456a4cca815edda72b9"
PYTHON="python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89"
AM="quay.io/prometheus/alertmanager:v0.28.1"
JOBS=("node","http_health","https_health","p2-app","p2-cgroup","p2-mysql","p2-nginx","p2-keycloak","p2-ci")
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd(*args, timeout=120, check=True):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    if p.returncode and check:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {(p.stdout+p.stderr)[-2000:]}")
    return p.stdout.strip() if check else p


def check(ok,label):
    if not ok:
        raise AssertionError(label)
    print("OBS_P3_CASE="+label+":PASS",flush=True)


def eventually(fn,label,timeout=100):
    end=time.monotonic()+timeout
    last=""
    while time.monotonic()<end:
        try:
            v=fn()
            if v:
                return v
        except (OSError,RuntimeError,ValueError,KeyError,AssertionError) as exc:
            last=str(exc)[:180]
        time.sleep(.5)
    raise AssertionError(label+" timeout "+last)


def get(url):
    with OPENER.open(url,timeout=5) as response:
        return json.loads(response.read())


def inspect(name):
    return json.loads(cmd("docker","inspect",name))[0]


def main():
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("RUNNER_ENVIRONMENT")!="github-hosted":
        raise SystemExit("disposable hosted CI required")
    rules=json.loads((HERE/"rules.yml").read_text())
    config=json.loads((HERE/"alertmanager.yml").read_text())
    check(len(rules["groups"][0]["rules"])==13,"13-rule-scope")
    check(all('environment="synthetic"' in x["expr"] for x in rules["groups"][0]["rules"]),"synthetic-selector")
    check(config["receivers"]==[{"name":"discard"},{"name":"synthetic-webhook","webhook_configs":[{
        "url":"http://webhook:8080/receive","send_resolved":True,"max_alerts":20,
        "http_config":{"follow_redirects":False}}]}],"exact-local-receiver")
    token=uuid.uuid4().hex[:12]
    names={k:"p3-"+k+"-"+token for k in ("fixture","webhook","prom","alertmanager")}
    nets={k:"p3-"+k+"-"+token for k in ("internal","foreign")}
    created=[]; networks=[]
    try:
        refs={}
        for kind,image in (("prom",PROM),("python",PYTHON),("am",AM)):
            cmd("docker","pull","--platform","linux/amd64",image,timeout=300)
            img=json.loads(cmd("docker","image","inspect",image))[0]
            repo=image.split("@")[0] if "@" in image else image.rsplit(":",1)[0]
            digests=[v for v in img["RepoDigests"] if v.split("@")[0]==repo]
            check(img["Os"]=="linux" and img["Architecture"]=="amd64" and bool(digests),"image-"+kind)
            refs[kind]=digests[0]
            print("OBS_P3_IMAGE="+kind+"|"+refs[kind],flush=True)
        for net in nets.values():
            cmd("docker","network","create","--internal",net)
            networks.append(net)
            check(inspect(net)["Internal"],"network-"+net.split("-")[1])

        def mount(path,dest):
            return ["--mount",f"type=bind,src={path},dst={dest},readonly"]

        def validate_tool(kind,entry,args,folder):
            return cmd("docker","run","--rm","--pull","never","--network","none",
                "--cap-drop","ALL","--security-opt","no-new-privileges","--memory","256m","--memory-swap","256m",
                "--cpus","0.5","--entrypoint",entry,*mount(folder,"/fixture"),refs[kind],*args)

        with tempfile.TemporaryDirectory(prefix="p3-ci-") as td:
            folder=Path(td);folder.chmod(0o755)
            def write(name,value):
                tmp=folder/(name+".tmp")
                tmp.write_text(json.dumps(value,indent=2)+"\n")
                tmp.chmod(0o644)
                tmp.replace(folder/name)
            write("rules.yml",rules)
            write("tests.yml",tests(rules))
            write("alertmanager.yml",config)
            print(validate_tool("prom","/bin/promtool",["check","rules","/fixture/rules.yml"],folder),flush=True)
            check(True,"promtool-rule-syntax")
            print(validate_tool("prom","/bin/promtool",["test","rules","/fixture/tests.yml"],folder),flush=True)
            check(True,"promtool-78-rule-assertions")
            print(validate_tool("am","/bin/amtool",["check-config","/fixture/alertmanager.yml"],folder),flush=True)
            check(True,"amtool-config")
            fast=copy.deepcopy(rules)
            fast["groups"][0]["interval"]="2s"
            for row in fast["groups"][0]["rules"]:
                row["for"]="4s"
            check([x["expr"] for x in fast["groups"][0]["rules"]]==
                  [x["expr"] for x in rules["groups"][0]["rules"]],"runtime-expressions-unchanged")
            write("fast-rules.yml",fast)
            write("state.json",{})
            promconf={"global":{"scrape_interval":"2s","scrape_timeout":"1s","evaluation_interval":"2s"},
                      "rule_files":["/fixture/fast-rules.yml"],
                      "alerting":{"alertmanagers":[{"static_configs":[{"targets":["alertmanager:9093"]}]}]},
                      "scrape_configs":[{"job_name":job,"metrics_path":"/metrics/"+job,
                         "sample_limit":100,"label_limit":12,"static_configs":[{
                             "targets":["metrics:8080"],"labels":{"environment":"synthetic",
                             "instance":"fixture-ci" if job=="p2-ci" else "fixture-"+job}}]}
                         for job in JOBS]}
            write("prometheus.yml",promconf)
            print(validate_tool("prom","/bin/promtool",["check","config","/fixture/prometheus.yml"],folder),flush=True)
            check(True,"promtool-config")
            def run(kind,image,alias,flags,args,mem,cpu):
                name=names[kind]
                cmd("docker","run","-d","--pull","never","--name",name,
                    "--network",nets["internal"],"--network-alias",alias,
                    "--cap-drop","ALL","--security-opt","no-new-privileges",
                    "--memory",mem,"--memory-swap",mem,"--cpus",cpu,"--pids-limit","128",
                    *flags,refs[image],*args)
                created.append(name)
                return inspect(name)["NetworkSettings"]["Networks"][nets["internal"]]["IPAddress"]
            common=["--user","65534:65534","--read-only",*mount(folder,"/control"),
                    *mount(HERE/"fixture.py","/fixture.py")]
            m=run("fixture","python","metrics",common,["python","/fixture.py","metrics"],"64m","0.25")
            w=run("webhook","python","webhook",common,["python","/fixture.py","webhook"],"64m","0.25")
            a=run("alertmanager","am","alertmanager",[*mount(folder/"alertmanager.yml","/etc/alertmanager/alertmanager.yml")],
                  ["--config.file=/etc/alertmanager/alertmanager.yml","--storage.path=/alertmanager",
                   "--cluster.listen-address="],"128m","0.5")
            p=run("prom","prom","prom",[*mount(folder,"/fixture")],
                  ["--config.file=/fixture/prometheus.yml","--storage.tsdb.path=/prometheus",
                   "--storage.tsdb.retention.time=1h","--storage.tsdb.retention.size=128MB",
                   "--query.max-concurrency=4","--query.timeout=10s"],"256m","0.5")
            prom="http://"+p+":9090"
            am="http://"+a+":9093"
            webhook="http://"+w+":8080"
            def query(expr):
                import urllib.parse
                data=get(prom+"/api/v1/query?"+urllib.parse.urlencode({"query":expr}))
                assert data["status"]=="success"
                return data["data"]["result"]
            def alerts():
                return get(prom+"/api/v1/alerts")["data"]["alerts"]
            def firing():
                return {x["labels"]["alertname"] for x in alerts() if x["state"]=="firing"}
            def events():
                return get(webhook+"/events")
            def rows(status,code=200):
                return {x["name"] for e in events() if e["code"]==code
                        for x in e["alerts"] if x["status"]==status}
            def all_up(except_job=None):
                rr=query("up")
                return (len(rr)==len(JOBS) and all(float(x["value"][1])==
                        (0 if x["metric"]["job"]==except_job else 1) for x in rr))
            eventually(all_up,"all-nine-jobs")
            time.sleep(8)
            check(not firing() and not events(),"healthy-no-notification")
            write("state.json",{"node":True,"probe":True,"mysql":True,"stale":True,"ci_failure":True})
            want={"HostMemoryCritical","HostMemoryLow","HostRootDiskLow","ProbeTargetDown",
                  "MySQLTargetDown","CIEvidenceUnavailable"}
            eventually(lambda: want <= firing(),"real-rule-firing")
            check("CIExecutionFailed" not in firing(),"stale-ci-failure-suppressed")
            notify=want-{"HostMemoryLow"}
            eventually(lambda: notify<=rows("firing"),"local-notification")
            check("HostMemoryLow" not in rows("firing"),"warning-inhibited-by-critical")
            check(any({"HostMemoryCritical","HostRootDiskLow"} <=
                      {x["name"] for x in e["alerts"]} and e["code"]==200 for e in events()),
                  "grouped-node-notification")
            check(all(e["truncated"]==0 and e["group"].get("environment")=="synthetic"
                      for e in events()),"bounded-synthetic-delivery")
            time.sleep(7)
            before=len(events())
            time.sleep(12)
            check(len(events())==before,"dedup-no-repeat-within-window")
            write("state.json",{})
            eventually(lambda: not firing(),"all-rules-recovered")
            eventually(lambda: notify<=rows("resolved"),"resolved-webhook")
            check(True,"trigger-to-resolve")
            # Failure of an individual scrape should not be mistaken for DB target down.
            write("state.json",{"scrape_down":"p2-mysql","mysql":True})
            eventually(lambda: all_up("p2-mysql") and "TargetScrapeDown" in firing(),
                       "scrape-down-isolated")
            check("MySQLTargetDown" not in firing(),"scrape-not-db-down")
            eventually(lambda: "TargetScrapeDown" in rows("firing"),"scrape-notification")
            write("state.json",{})
            eventually(lambda: all_up() and not firing(),"scrape-recovered")
            eventually(lambda: "TargetScrapeDown" in rows("resolved"),"scrape-resolved")
            # Receiver fails locally, then receives the same active alert after recovery.
            write("state.json",{"nginx":True,"receiver_fail":True})
            eventually(lambda: "NginxTargetDown" in rows("firing",503),"receiver-failure-observed")
            check(all_up(),"receiver-failure-does-not-stop-scrape")
            write("state.json",{"nginx":True})
            eventually(lambda: "NginxTargetDown" in rows("firing"),"receiver-recovery",120)
            write("state.json",{})
            eventually(lambda: "NginxTargetDown" in rows("resolved"),"receiver-resolve")
            check(True,"receiver-failure-and-recovery")
            # Exercise Alertmanager discard routing without a real or external target.
            payload=[{"labels":{"alertname":"SyntheticDiscardProbe","environment":"unapproved",
                               "job":"discard","instance":"fixture-discard","severity":"warning"},
                      "annotations":{},"startsAt":"2020-01-01T00:00:00Z",
                      "endsAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(time.time()+60))}]
            request=urllib.request.Request(am+"/api/v2/alerts",data=json.dumps(payload).encode(),
                                           headers={"Content-Type":"application/json"},method="POST")
            with OPENER.open(request,timeout=5) as response:
                check(response.status==200,"discard-fixture-accepted")
            time.sleep(7)
            check("SyntheticDiscardProbe" not in rows("firing"),"non-synthetic-not-delivered")
            # Explicitly prove same-target inhibition on Alertmanager even with inconsistent caller assertions.
            def direct(alert,job,instance,severity):
                return {"labels":{"alertname":alert,"environment":"synthetic","job":job,
                                  "instance":instance,"severity":severity},"annotations":{},
                        "startsAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(time.time()-1)),
                        "endsAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(time.time()+90))}
            direct_payload=[direct("TargetScrapeDown","p2-mysql","fixture-inhibit","critical"),
                            direct("MySQLTargetDown","p2-mysql","fixture-inhibit","critical"),
                            direct("MySQLTargetDown","p2-mysql","fixture-independent","critical")]
            req=urllib.request.Request(am+"/api/v2/alerts",data=json.dumps(direct_payload).encode(),
                                       headers={"Content-Type":"application/json"},method="POST")
            with OPENER.open(req,timeout=5) as response:
                check(response.status==200,"inhibit-fixture-accepted")
            def delivered(name,instance):
                return any(x["name"]==name and x["instance"]==instance and x["status"]=="firing"
                           for e in events() if e["code"]==200 for x in e["alerts"])
            eventually(lambda: delivered("TargetScrapeDown","fixture-inhibit") and
                       delivered("MySQLTargetDown","fixture-independent"),"inhibit-scope-positive")
            check(not delivered("MySQLTargetDown","fixture-inhibit"),"inhibit-exact-target-only")
            for kind,name in names.items():
                info=inspect(name);h=info["HostConfig"]
                check(not h["Privileged"] and not h.get("PortBindings") and
                      "ALL" in h.get("CapDrop",[]) and set(info["NetworkSettings"]["Networks"])=={nets["internal"]} and
                      not any("docker.sock" in mount["Source"] or "docker.sock" in mount["Destination"]
                              for mount in info["Mounts"]),"isolated-"+kind)
            script="""import socket,sys
for addr,port in ((sys.argv[1],9090),(sys.argv[2],9093),(sys.argv[3],8080)):
    try:
        with socket.create_connection((addr,port),timeout=2):
            raise SystemExit(1)
    except OSError:
        pass
"""
            cmd("docker","run","--rm","--pull","never","--network",nets["foreign"],
                "--cap-drop","ALL","--security-opt","no-new-privileges",refs["python"],
                "python","-c",script,p,a,w)
            check(True,"foreign-network-denied")
            stats=cmd("docker","stats","--no-stream","--format","{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}",*created)
            print("OBS_P3_STATS="+stats.replace("\n",";"),flush=True)
            print("OBS_P3_WEBHOOK_COUNTS="+json.dumps({"received":len(events()),
                 "failed":sum(e["code"]!=200 for e in events()),"resolved":sum(e["status"]=="resolved" for e in events())}),flush=True)
            print("OBS_P3_ALERT_LIFECYCLE=PASS",flush=True)
    except Exception:
        print("OBS_P3_ALERT_LIFECYCLE=NO_GO",flush=True)
        for name in created:
            out=cmd("docker","logs","--tail","20",name,check=False)
            print(name+" LOG TAIL "+(out.stdout+out.stderr)[-2200:],flush=True)
        raise
    finally:
        for name in reversed(created):
            cmd("docker","rm","-fv",name,check=False)
        for net in reversed(networks):
            cmd("docker","network","rm",net,check=False)


if __name__=="__main__":
    main()
