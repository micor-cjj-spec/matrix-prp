"""Hosted-CI-only gateway/identity resource metric experiment; never target a live service."""
import json
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
IMAGES = {
    "nginx": "nginx:1.29-alpine",
    "exporter": "nginx/nginx-prometheus-exporter:1.4.2",
    "keycloak": "quay.io/keycloak/keycloak:26.8.0",
    "proxy": "python:3.12-alpine",
    "prom": "quay.io/prometheus/prometheus:v3.13.5",
}
DISCOVERY = "/realms/master/.well-known/openid-configuration"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd(*args, timeout=120, check=True):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode and check:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {p.stderr[-1800:]}")
    return p.stdout.strip() if check else p


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("OBS_P25_CASE=" + name + ":PASS", flush=True)


def eventually(fn, name, timeout=100):
    end = time.monotonic() + timeout
    last = ""
    while time.monotonic() < end:
        try:
            result = fn()
            if result:
                return result
        except (OSError, RuntimeError, AssertionError, ValueError, KeyError) as exc:
            last = str(exc)[:180]
        time.sleep(1)
    raise AssertionError(name + " timed out: " + last)


def inspect(name):
    return json.loads(cmd("docker", "inspect", name))[0]


def get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with OPENER.open(request, timeout=10) as response:
        return response.read().decode()


def rejected(url):
    try:
        get(url)
    except urllib.error.HTTPError as exc:
        return 400 <= exc.code < 500
    return False


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("disposable GitHub-hosted runner required")
    token = uuid.uuid4().hex[:12]
    backend, edge, monitor = ("p25-" + x + "-" + token for x in ("backend", "edge", "monitor"))
    names = {key: "p25-" + key + "-" + token for key in IMAGES}
    marker = "p25-private-marker-" + token
    refs, created, networks = {}, [], []
    try:
        for key, image in IMAGES.items():
            cmd("docker", "pull", "--platform", "linux/amd64", image, timeout=300)
            data = json.loads(cmd("docker", "image", "inspect", image))[0]
            check(data["Os"] == "linux" and data["Architecture"] == "amd64", "image-" + key)
            repo = image.rsplit(":", 1)[0]
            matches = [d for d in data.get("RepoDigests", []) if d.split("@", 1)[0]
                       in (repo, "library/" + repo, "docker.io/library/" + repo, "docker.io/" + repo)]
            check(bool(matches), "digest-" + key)
            refs[key] = matches[0]
            print("OBS_P25_IMAGE=" + key + "|" + refs[key], flush=True)
        for net in (backend, edge, monitor):
            cmd("docker", "network", "create", "--internal", net)
            networks.append(net)
            check(inspect(net)["Internal"], "private-" + net.split("-")[1])

        def mount(source, target):
            return ["--mount", f"type=bind,src={source},dst={target},readonly"]

        def run(key, net, flags, args):
            name = names[key]
            cmd("docker", "run", "-d", "--pull", "never", "--name", name,
                "--network", net, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "256", *flags, refs[key], *args)
            created.append(name)
            return inspect(name)["NetworkSettings"]["Networks"][net]["IPAddress"]

        def ip(key, net):
            return inspect(names[key])["NetworkSettings"]["Networks"][net]["IPAddress"]

        kc = run("keycloak", backend, ["--network-alias", "keycloak", "--memory", "1024m",
                 "--memory-swap", "1024m", "--cpus", "1.5", "-e",
                 "JAVA_OPTS_KC_HEAP=-Xms128m -Xmx384m"], [
            "start-dev", "--db=dev-file", "--cache=local", "--metrics-enabled=true",
            "--health-enabled=true", "--http-management-port=9000", "--http-management-relative-path=/",
            "--http-management-scheme=http", "--http-management-host=0.0.0.0",
            "--hostname=http://gateway:8080", "--http-enabled=true", "--http-host=0.0.0.0",
        ])
        eventually(lambda: json.loads(get("http://" + kc + ":9000/health/ready")).get("status") == "UP",
                   "keycloak management readiness", 240)
        check(True, "keycloak-management-ready")
        raw_kc = get("http://" + kc + ":9000/metrics")
        check("jvm_memory_used_bytes" in raw_kc, "keycloak-native-metrics")
        check(rejected("http://" + kc + ":8080/metrics"), "keycloak-main-metrics-denied")
        check(rejected("http://" + kc + ":8080/health"), "keycloak-main-health-denied")
        check(rejected("http://" + kc + ":8080/health/ready"), "keycloak-main-readiness-denied")

        with tempfile.TemporaryDirectory(prefix="p25-fixture-") as td:
            folder = Path(td)
            folder.chmod(0o755)
            nginx = run("nginx", backend, ["--network-alias", "nginx-internal", "--user", "101:101",
                        "--read-only", "--memory", "96m", "--memory-swap", "96m", "--cpus", "0.5",
                        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777",
                        "--entrypoint", "/bin/sh", *mount(folder, "/fixture")],
                        ["-c", "while [ ! -f /fixture/nginx.conf ]; do sleep 1; done; "
                         "exec nginx -c /fixture/nginx.conf -g 'daemon off;'"])
            cmd("docker", "network", "connect", "--alias", "gateway", edge, names["nginx"])
            public = ip("nginx", edge)
            config = (HERE / "nginx.conf.template").read_text().replace("__BACKEND_IP__", nginx)
            temporary = folder / "nginx.tmp"
            temporary.write_text(config)
            temporary.chmod(0o644)
            temporary.rename(folder / "nginx.conf")
            gateway = "http://" + public + ":8080"
            statusurl = "http://" + nginx + ":8081/stub_status"
            eventually(lambda: get(gateway + "/fixture").strip() == "synthetic", "nginx readiness")
            check(json.loads(get(gateway + DISCOVERY))["issuer"].endswith("/realms/master"),
                  "synthetic-discovery-through-gateway")
            for route in ("/metrics", "/health", "/health/ready", "/stub_status", "/admin", "/probe"):
                check(rejected(gateway + route), "gateway-deny-" + route.replace("/", "-").strip("-"))
            ex = run("exporter", backend, ["--network-alias", "nginx-exporter", "--user", "65534:65534",
                     "--read-only", "--memory", "96m", "--memory-swap", "96m", "--cpus", "0.5"], [
                "--nginx.scrape-uri=http://nginx-internal:8081/stub_status",
                "--nginx.timeout=2s", "--web.listen-address=:9113",
            ])
            eventually(lambda: "nginx_up 1" in get("http://" + ex + ":9113/metrics"), "nginx exporter ready")
            check(True, "nginx-official-exporter")
            run("proxy", backend, ["--user", "65534:65534", "--read-only", "--memory", "64m",
                "--memory-swap", "64m", "--cpus", "0.25", *mount(HERE / "fixed_proxy.py", "/fixed_proxy.py")],
                ["python", "/fixed_proxy.py"])
            cmd("docker", "network", "connect", "--alias", "fixed-metrics", monitor, names["proxy"])
            proxy = "http://" + ip("proxy", monitor) + ":9105"
            eventually(lambda: "nginx_up 1" in get(proxy + "/nginx/metrics"), "fixed nginx projection")
            eventually(lambda: "jvm_memory_used_bytes" in get(proxy + "/keycloak/metrics"),
                       "fixed keycloak projection")
            for route in ("/probe", "/metrics", "/keycloak/metrics?target=other",
                          "/nginx/metrics?target=other", "/keycloak/metrics/", "/health"):
                check(rejected(proxy + route), "fixed-target-deny-" + str(len(route)) + "-" + str(route.count("?")))
            try:
                OPENER.open(urllib.request.Request(proxy + "/keycloak/metrics", method="POST", data=b""), timeout=5)
                raise AssertionError("POST accepted")
            except urllib.error.HTTPError as exc:
                check(exc.code in (405, 501), "fixed-target-post-denied")

            # A real peer in each isolated network must not reach backend-only ports.
            probe = """import socket,sys
for pair in sys.argv[1:]:
    target,port=pair.rsplit(':',1)
    try:
        with socket.create_connection((target,int(port)),timeout=3):
            raise SystemExit(1)
    except OSError:
        pass
"""
            def deny_peer(net, targets):
                cmd("docker", "run", "--rm", "--pull", "never", "--network", net,
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--memory", "64m", "--memory-swap", "64m", refs["proxy"],
                    "python", "-c", probe, *targets)
            deny_peer(edge, [public + ":8081", kc + ":9000", ex + ":9113",
                             ip("proxy", backend) + ":9105"])
            check(True, "edge-peer-management-ports-denied")
            deny_peer(monitor, [kc + ":9000", kc + ":8080", nginx + ":8081", ex + ":9113"])
            check(True, "scrape-peer-raw-targets-denied")
            for key in IMAGES:
                if key == "prom":
                    continue
                info = inspect(names[key])
                h = info["HostConfig"]
                expected = {backend, edge} if key == "nginx" else ({backend, monitor} if key == "proxy" else {backend})
                check(not h["Privileged"] and not h.get("PortBindings")
                      and "ALL" in h.get("CapDrop", []) and set(info["NetworkSettings"]["Networks"]) == expected
                      and h["PidMode"] != "host" and h["NetworkMode"] != "host"
                      and not any("docker.sock" in m["Source"] or "docker.sock" in m["Destination"] for m in info["Mounts"]),
                      "container-isolation-" + key)

            conf = folder / "prom.yml"
            conf.write_text(json.dumps({"global": {"scrape_interval": "6s", "scrape_timeout": "5s"},
                "scrape_configs": [{"job_name": "p2-" + target, "metrics_path": "/" + target + "/metrics",
                    "sample_limit": 200, "label_limit": 12, "static_configs": [{
                        "targets": ["fixed-metrics:9105"], "labels": {"environment": "synthetic",
                        "instance": "fixture-" + target}}]} for target in ("nginx", "keycloak")]}))
            conf.chmod(0o644)
            prom = run("prom", monitor, ["--memory", "256m", "--memory-swap", "256m",
                       "--cpus", "0.5", *mount(conf, "/etc/prometheus/prometheus.yml")], [
                "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                "--storage.tsdb.retention.time=1h",
            ])
            info = inspect(names["prom"])
            check(not info["HostConfig"]["Privileged"] and not info["HostConfig"].get("PortBindings")
                  and set(info["NetworkSettings"]["Networks"]) == {monitor}, "container-isolation-prom")
            base = "http://" + prom + ":9090"

            def query(expr):
                payload = json.loads(get(base + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})))
                assert payload["status"] == "success"
                return payload["data"]["result"]

            def scalar(expr):
                rows = query(expr)
                assert len(rows) == 1, "expected one series: " + expr
                return float(rows[0]["value"][1])

            nu = 'up{job="p2-nginx"}'
            ku = 'up{job="p2-keycloak"}'
            kc_http = 'sum(http_server_requests_seconds_count{job="p2-keycloak"})'
            nc = "nginx_http_requests_total"
            eventually(lambda: scalar(nu) == 1 and scalar(ku) == 1 and scalar("nginx_up") == 1,
                       "projected scrape ready")
            def stub():
                lines = get(statusurl).strip().splitlines()
                accepted, handled, requests = map(int, lines[2].split())
                return accepted, handled, requests
            start = stub()
            eventually(lambda: scalar(nc) >= start[2], "nginx counter catches source")
            observed = (scalar("nginx_connections_accepted"), scalar("nginx_connections_handled"), scalar(nc))
            end = stub()
            check(all(a <= v <= b for a, v, b in zip(start, observed, end)), "nginx-source-counter-parity")
            check(scalar("nginx_connections_active") >= 1, "nginx-active-connections")
            n_before = scalar(nc)
            eventually(lambda: scalar(kc_http) >= 1, "keycloak discovery HTTP metric")
            k_before = scalar(kc_http)
            for _ in range(12):
                get(gateway + "/fixture", {"X-P25-Fixture": marker})
                get(gateway + DISCOVERY + "?p25=" + marker, {"X-P25-Fixture": marker})
            # A synthetic denied path challenges URI filtering directly on the fixture.
            check(rejected("http://" + kc + ":8080/" + marker), "synthetic-unknown-uri-denied")
            eventually(lambda: scalar(nc) >= n_before + 24, "nginx generated request delta")
            check(True, "nginx-request-delta")
            eventually(lambda: scalar(kc_http) >= k_before + 12, "keycloak generated request delta")
            check(True, "keycloak-http-delta")
            check(scalar('sum(jvm_memory_used_bytes{job="p2-keycloak"})') > 0,
                  "keycloak-jvm-memory")
            check(scalar('jvm_threads_live_threads{job="p2-keycloak"}') > 0, "keycloak-jvm-threads")
            for family in ("agroal_active_count", "agroal_available_count", "agroal_awaiting_count"):
                check(scalar(family + '{job="p2-keycloak"}') >= 0, "keycloak-" + family)
            rows = query('{job=~"p2-nginx|p2-keycloak"}')
            check(0 < len(rows) <= 410, "bounded-projected-series")
            projected = json.dumps(rows)
            check(marker not in projected and not any(x in projected for x in
                  (kc, nginx, ex, "access_token", "refresh_token", '"client_id"', '"user_id"')),
                  "no-sensitive-tsdb-markers")
            exposed = get(proxy + "/keycloak/metrics") + get(proxy + "/nginx/metrics")
            check(marker not in exposed and not any(x in exposed for x in
                  ("access_token", "refresh_token", "client_id=", "user_id=", "session_id=")),
                  "no-sensitive-export-projection")
            print("OBS_P25_SERIES=" + str(len(rows)), flush=True)
            print("OBS_P25_RAW_UNKNOWN_URI_MARKER=" +
                  ("PRESENT_FILTERED" if marker in get("http://" + kc + ":9000/metrics") else "ABSENT"), flush=True)
            print("OBS_P25_STATS=" + cmd("docker", "stats", "--no-stream", "--format",
                  "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}", *created).replace("\n", ";"), flush=True)
            cmd("docker", "stop", names["keycloak"])
            eventually(lambda: scalar(ku) == 0 and scalar(nu) == 1 and scalar("nginx_up") == 1,
                       "keycloak target down while gateway up")
            check(get(gateway + "/fixture").strip() == "synthetic", "gateway-available-during-kc-down")
            check(True, "keycloak-down-isolated")
            cmd("docker", "start", names["keycloak"])
            restarted = time.time()
            kc = ip("keycloak", backend)
            eventually(lambda: json.loads(get("http://" + kc + ":9000/health/ready")).get("status") == "UP",
                       "keycloak restart readiness", 240)
            eventually(lambda: scalar(ku) == 1 and scalar("timestamp(" + ku + ")") > restarted,
                       "keycloak fresh scrape recovery")
            check(True, "keycloak-fresh-recovery")
            check(json.loads(get(gateway + DISCOVERY))["issuer"].endswith("/realms/master"),
                  "gateway-discovery-recovered")
            cmd("docker", "stop", names["nginx"])
            eventually(lambda: scalar(nu) == 1 and scalar("nginx_up") == 0 and scalar(ku) == 1,
                       "nginx target down distinct from scrape path")
            check(True, "nginx-down-isolated")
            cmd("docker", "start", names["nginx"])
            restart_nginx = time.time()
            check(ip("nginx", backend) == nginx, "nginx-backend-binding-stable")
            eventually(lambda: scalar("nginx_up") == 1 and scalar("timestamp(nginx_up)") > restart_nginx,
                       "nginx fresh recovery")
            check(True, "nginx-fresh-recovery")
            cmd("docker", "stop", names["proxy"])
            eventually(lambda: scalar(nu) == 0 and scalar(ku) == 0 and not query("nginx_up"),
                       "scrape proxy down")
            check(True, "scrape-path-down-distinct")
            cmd("docker", "start", names["proxy"])
            restart_proxy = time.time()
            eventually(lambda: scalar(nu) == 1 and scalar(ku) == 1 and
                       scalar("timestamp(" + ku + ")") > restart_proxy, "scrape proxy recovery")
            check(True, "scrape-path-fresh-recovery")
            print("OBS_P25_CORE=PASS", flush=True)
    except Exception:
        print("OBS_P25_CORE=NO_GO", flush=True)
        for key in ("nginx", "exporter", "keycloak", "proxy", "prom"):
            if names[key] in created:
                log = cmd("docker", "logs", "--tail", "40", names[key], check=False)
                print(key + " LOG TAIL\n" + (log.stdout + log.stderr)[-4000:], flush=True)
        raise
    finally:
        for name in reversed(created):
            cmd("docker", "rm", "-fv", name, check=False)
        for net in reversed(networks):
            cmd("docker", "network", "rm", net, check=False)


if __name__ == "__main__":
    main()
