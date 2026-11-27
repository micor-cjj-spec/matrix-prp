"""One real Prometheus, one real Blackbox, bounded representative replays; hosted CI only."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
OBS = HERE.parent
ROOT = HERE.parents[2]
PROM = "quay.io/prometheus/prometheus@sha256:aafa9d694e6a883c02db516d9f6e5b84e14195f49a2a6456a4cca815edda72b9"
BLACKBOX = "quay.io/prometheus/blackbox-exporter@sha256:ea1c7aa3ef3f307cd03e85f34abb604478ccb90b567fc690da0cd9776da76b13"
PYTHON = "python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89"
KINDS = ("app","cgroup","mysql","nginx","keycloak","ci")
JOBS = {"http_health", *("p2-"+k for k in KINDS)}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd(*args, timeout=120, check=True):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout, cwd=ROOT)
    if check and p.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {p.stderr[-1600:]}")
    return p.stdout.strip() if check else p


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("OBS_P2I_CASE="+name+":PASS",flush=True)


def eventually(fn, name, timeout=100):
    deadline = time.monotonic()+timeout
    last = ""
    while time.monotonic()<deadline:
        try:
            value=fn()
            if value:
                return value
        except (OSError, RuntimeError, AssertionError, ValueError, KeyError) as exc:
            last=str(exc)[:160]
        time.sleep(1)
    raise AssertionError(name+" timed out: "+last)


def inspect(name):
    return json.loads(cmd("docker","inspect",name))[0]


def verify_sources():
    manifest=json.loads((HERE/"source-manifest.json").read_text())
    paths={}
    check([p["pr"] for p in manifest["source_prs"]]==[463,467,469,472,473,475],"exact-six-source-prs")
    for group in manifest["source_prs"]:
        for path, sha in group["files"].items():
            assert path not in paths
            paths[path]=sha
            entry=cmd("git","ls-tree","HEAD","--",path)
            check(entry=="100644 blob "+sha+"\t"+path,"blob-"+str(group["pr"])+"-"+Path(path).name)
            check(cmd("git","hash-object",path)==sha,"working-blob-"+str(group["pr"])+"-"+Path(path).name)
    check(len(paths)==36,"exact-36-source-blobs")
    expected=set(paths)|set(manifest["integration_paths"])
    check(len(expected)==42,"42-authorized-paths")
    check(set(cmd("git","diff","--name-only",manifest["base"],"HEAD").splitlines())==expected,
          "exact-diff-scope")
    config=json.loads((HERE/"prometheus.yml").read_text())
    check(len(config["scrape_configs"])==len(JOBS) and
          {x["job_name"] for x in config["scrape_configs"]}==JOBS,"unique-jobs")
    dashboards=[json.loads((OBS/p/"dashboard.json").read_text()) for p in ("p2-3","p2-4","p2-5","p2-6")]
    check(len({d["uid"] for d in dashboards})==4,"unique-dashboard-uids")
    exprs=[t["expr"] for d in dashboards for panel in d["panels"] for t in panel.get("targets",[])]
    check(len(exprs)==30,"all-source-dashboard-queries")
    return exprs


def main():
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("RUNNER_ENVIRONMENT")!="github-hosted":
        raise SystemExit("disposable GitHub-hosted runner required")
    exprs=verify_sources()
    token=uuid.uuid4().hex[:12]
    nets={x:"p2i-"+x+"-"+token for x in ("backend","monitor","foreign")}
    names={x:"p2i-"+x+"-"+token for x in (*KINDS,"health","blackbox","prom")}
    created,net_created=[],[]
    try:
        for image in (PROM,BLACKBOX,PYTHON):
            cmd("docker","pull","--platform","linux/amd64",image,timeout=300)
            data=json.loads(cmd("docker","image","inspect",image))[0]
            check(data["Os"]=="linux" and data["Architecture"]=="amd64" and image in data["RepoDigests"],
                  "immutable-image-"+image.split("@")[0].split("/")[-1])
        for net in nets.values():
            cmd("docker","network","create","--internal",net)
            net_created.append(net)
            check(inspect(net)["Internal"],"internal-"+net.split("-")[1])

        def mount(src,dst):
            return ["--mount",f"type=bind,src={src},dst={dst},readonly"]

        def run(kind,image,network,alias,flags,args,memory="64m",cpu="0.25"):
            name=names[kind]
            cmd("docker","run","-d","--pull","never","--name",name,
                "--network",nets[network],"--network-alias",alias,"--cap-drop","ALL",
                "--security-opt","no-new-privileges","--pids-limit","128","--memory",memory,
                "--memory-swap",memory,"--cpus",cpu,*flags,image,*args)
            created.append(name)
            return inspect(name)["NetworkSettings"]["Networks"][nets[network]]["IPAddress"]

        def ip(kind,net):
            return inspect(names[kind])["NetworkSettings"]["Networks"][nets[net]]["IPAddress"]

        with tempfile.TemporaryDirectory(prefix="p2i-") as td:
            folder=Path(td)
            ca=folder/"fixture-ca.crt"
            cmd("openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
                "-subj","/CN=synthetic-ci-only","-keyout",str(folder/"fixture.key"),"-out",str(ca))
            ca.chmod(0o644)
            common=["--user","65534:65534","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=8m,mode=1777",
                    *mount(OBS,"/repo/app/observability")]
            run("health",PYTHON,"backend","health-fixture",common,
                ["python","-c","import sys;sys.path.insert(0,'/repo/app/observability/p2-1');"
                 "from fixture import Handler,ThreadingHTTPServer;ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()"])
            run("blackbox",BLACKBOX,"backend","blackbox",["--user","65534:65534","--read-only",
                *mount(OBS/"p2-1"/"blackbox.yml","/etc/blackbox/config.yml"),
                *mount(ca,"/etc/blackbox/fixture-ca.crt")],
                ["--config.file=/etc/blackbox/config.yml"],"96m","0.5")
            cmd("docker","network","connect","--alias","blackbox",nets["monitor"],names["blackbox"])
            for kind in KINDS:
                run(kind,PYTHON,"monitor",kind,[*common,
                    *mount(ROOT/"app/scripts/release_status.py","/repo/app/scripts/release_status.py")],
                    ["python","/repo/app/observability/integration/fixture.py",kind])
            prom=run("prom",PROM,"monitor","prom",[ *mount(HERE/"prometheus.yml","/etc/prometheus/prometheus.yml")],
                ["--config.file=/etc/prometheus/prometheus.yml","--storage.tsdb.path=/prometheus",
                 "--storage.tsdb.retention.time=7d","--storage.tsdb.retention.size=2GB",
                 "--query.max-concurrency=4","--query.timeout=10s"],"512m","0.75")
            base="http://"+prom+":9090"

            def get(path):
                with OPENER.open(base+path,timeout=12) as response:
                    payload=json.loads(response.read())
                    assert payload["status"]=="success"
                    return payload["data"]

            def query(expr):
                return get("/api/v1/query?"+urllib.parse.urlencode({"query":expr}))["result"]

            def scalar(expr):
                rows=query(expr)
                assert len(rows)==1, "expected one series: "+expr
                return float(rows[0]["value"][1])

            def all_up(exclude=()):
                rows=query("up")
                return {x["metric"]["job"] for x in rows if float(x["value"][1])==1}==JOBS-set(exclude)

            eventually(all_up,"seven unified scrape jobs up")
            check(True,"seven-jobs-up")
            check(scalar("probe_success")==1,"real-blackbox-source")
            check(scalar('jvm_memory_used_bytes{job="p2-app"}')==150000000 and
                  scalar('jvm_memory_used_bytes{job="p2-keycloak"}')==220000000,
                  "shared-jvm-family-distinct-jobs")
            check(scalar("mysql_up")==1 and scalar("nginx_up")==1,"target-health-not-scrape-health")
            check(scalar('prp_ci_release_state_claim{state="HELD"}')==1,"held-not-live")
            check(scalar("prp_ci_projection_fresh")==1,"original-ci-projection-fresh")
            check(scalar('count by (__name__) (prp_ci_projection_fresh)')==1,"single-ci-projection-source")

            def nonempty(expr):
                rows=query(expr)
                return bool(rows) and all(math.isfinite(float(x["value"][1])) for x in rows)

            for i, expr in enumerate(exprs):
                eventually(lambda: nonempty(expr),"dashboard query "+str(i+1))
                check(True,"dashboard-query-"+str(i+1))
            check(scalar('sum(rate(http_server_requests_seconds_count{job="p2-app"}[2m]))')>0 and
                  scalar('sum(rate(http_server_requests_seconds_count{job="p2-keycloak"}[2m]))')>0,
                  "app-keycloak-http-rate-isolated")
            rows=query('{job=~"p2-.*|http_health"}')
            keys=[json.dumps(x["metric"],sort_keys=True) for x in rows]
            check(len(keys)==len(set(keys)) and len(keys)<1000,"bounded-unique-active-series")
            check("private-marker" not in "".join(keys) and
                  all(x["metric"].get("environment")=="synthetic" for x in rows),
                  "synthetic-labels-only")
            metadata=get("/api/v1/targets")
            check(len(metadata["activeTargets"])==7 and all(x["health"]=="up" for x in metadata["activeTargets"]),
                  "all-targets-healthy")
            tsdb=get("/api/v1/status/tsdb")["headStats"]
            head=int(tsdb["numSeries"])
            check(0<head<=2500,"bounded-tsdb-head-series")
            samples=scalar("sum(scrape_samples_post_metric_relabeling)")
            check(0<samples<2000,"bounded-samples-per-scrape")

            def timed(expr):
                start=time.monotonic()
                assert nonempty(expr), "dashboard query under load"
                return (time.monotonic()-start)*1000

            with ThreadPoolExecutor(max_workers=4) as pool:
                elapsed=sorted(pool.map(timed,exprs*4))
            p95=elapsed[math.ceil(len(elapsed)*.95)-1]
            check(p95<10000,"bounded-dashboard-query-latency")
            print("OBS_P2I_METRICS="+json.dumps({"active_series":len(keys),"head_series":head,
                "samples_per_scrape":samples,"synthetic_30s_samples_per_second":round(samples/30,3),
                "dashboard_queries":len(exprs),"load_queries":len(elapsed),"query_p95_ms":round(p95,2)}),flush=True)
            print("OBS_P2I_STATS="+cmd("docker","stats","--no-stream","--format",
                "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}",*created).replace("\n",";"),flush=True)
            print("OBS_P2I_TSDB_KIB="+cmd("docker","exec",names["prom"],"du","-sk","/prometheus").split()[0],flush=True)

            # Replay loss, actual probe target loss, and stale evidence are separate failure modes.
            cmd("docker","stop",names["mysql"])
            eventually(lambda: all_up({"p2-mysql"}) and scalar('up{job="p2-mysql"}')==0 and not query("mysql_up"),
                       "mysql replay loss isolated")
            check(True,"mysql-replay-down-other-jobs-up")
            cmd("docker","start",names["mysql"])
            restarted=time.time()
            eventually(lambda: all_up() and scalar("mysql_up")==1 and scalar("timestamp(mysql_up)")>restarted,
                       "mysql replay fresh recovery")
            check(True,"mysql-replay-fresh-recovery")
            cmd("docker","stop",names["health"])
            eventually(lambda: all_up() and scalar("probe_success")==0 and scalar('up{job="http_health"}')==1,
                       "real blackbox target down")
            check(True,"probe-target-down-not-exporter-down")
            cmd("docker","start",names["health"])
            restarted=time.time()
            eventually(lambda: all_up() and scalar("probe_success")==1 and scalar("timestamp(probe_success)")>restarted,
                       "real blackbox recovery")
            check(True,"probe-target-fresh-recovery")
            cmd("docker","exec",names["ci"],"touch","/tmp/stale")
            eventually(lambda: all_up() and scalar("prp_ci_projection_fresh")==0 and
                       scalar('prp_ci_projection_state{state="stale"}')==1 and not query("prp_ci_jobs"),
                       "stale CI evidence suppressed")
            check(True,"ci-stale-not-current")
            cmd("docker","exec",names["ci"],"rm","/tmp/stale")
            resumed=time.time()
            eventually(lambda: all_up() and scalar("prp_ci_projection_fresh")==1 and
                       scalar("timestamp(prp_ci_projection_fresh)")>resumed and bool(query("prp_ci_jobs")),
                       "CI evidence fresh recovery")
            check(True,"ci-evidence-recovered")

            for kind,name in names.items():
                info=inspect(name);h=info["HostConfig"]
                expected={nets["backend"]} if kind=="health" else ({nets["backend"],nets["monitor"]}
                    if kind=="blackbox" else {nets["monitor"]})
                check(not h["Privileged"] and not h.get("PortBindings") and "ALL" in h.get("CapDrop",[]) and
                      set(info["NetworkSettings"]["Networks"])==expected and h["PidMode"]!="host" and
                      not any("docker.sock" in m["Source"] or "docker.sock" in m["Destination"] for m in info["Mounts"]),
                      "isolation-"+kind)
            script="""import socket,sys
for address,port in ((sys.argv[1],9090),(sys.argv[2],8080)):
    try:
        with socket.create_connection((address,port),timeout=3):
            raise SystemExit(1)
    except OSError:
        pass
"""
            cmd("docker","run","--rm","--pull","never","--network",nets["foreign"],
                "--cap-drop","ALL","--security-opt","no-new-privileges","--memory","64m","--memory-swap","64m",
                PYTHON,"python","-c",script,prom,ip("health","backend"))
            check(True,"foreign-network-denied")
            print("OBS_P2I_SHARED_SCRAPE=PASS",flush=True)
    except Exception:
        print("OBS_P2I_SHARED_SCRAPE=NO_GO",flush=True)
        for kind,name in names.items():
            if name in created:
                out=cmd("docker","logs","--tail","12",name,check=False)
                print(kind+" LOG TAIL "+(out.stdout+out.stderr)[-1300:],flush=True)
        raise
    finally:
        for name in reversed(created):
            cmd("docker","rm","-fv",name,check=False)
        for net in reversed(net_created):
            cmd("docker","network","rm",net,check=False)


if __name__=="__main__":
    main()
