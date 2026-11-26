"""Disposable GitHub-hosted observability experiment; never run on a PRP host."""
import base64
import json
import ipaddress
import os
import re
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGES = {
    "node": "quay.io/prometheus/node-exporter:v1.13.1",
    "prom": "quay.io/prometheus/prometheus:v3.13.5",
    "grafana": "grafana/grafana:13.3.2",
}

def cmd(*args, allow_failure=False):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=180)
    if result.returncode and not allow_failure:
        # Never print command arguments or raw container output (may include credentials).
        raise RuntimeError("command failed: " + args[0] + " " + args[1])
    return result.stdout.strip()

def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print("OBS_CASE=" + label + ":PASS", flush=True)

def eventually(fn, label, timeout=110):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if fn():
                return
        except (OSError, ValueError, KeyError, urllib.error.HTTPError):
            pass
        time.sleep(2)
    raise AssertionError("timeout: " + label)

def api(base, path, auth=None, payload=None):
    headers = {"Accept": "application/json"}
    data = None
    if auth:
        headers["Authorization"] = auth
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as result:
        return json.load(result)

def query(base, expression, timestamp=None, auth=None, prefix=""):
    params = {"query": expression}
    if timestamp is not None:
        params["time"] = str(timestamp)
    value = api(base, prefix + "/api/v1/query?" + urllib.parse.urlencode(params), auth)
    if value.get("status") != "success":
        raise ValueError("query not successful")
    return value["data"]["result"]

def up(base):
    rows = query(base, 'up{job="node"}')
    return float(rows[0]["value"][1]) if len(rows) == 1 else None

def internal_url(name, network, container_port):
    networks = json.loads(cmd("docker", "inspect", "--format",
                              "{{json .NetworkSettings.Networks}}", name))
    if set(networks) != {network}:
        raise AssertionError("unexpected container network")
    address = ipaddress.IPv4Address(networks[network]["IPAddress"])
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise AssertionError("unexpected internal bridge address")
    return "http://" + str(address) + ":" + str(container_port)

def require_no_published_ports(names):
    for name in names:
        bindings = json.loads(cmd("docker", "inspect", "--format",
                                  "{{json .HostConfig.PortBindings}}", name))
        if bindings:
            raise AssertionError("unexpected host port bindings")
    require(True, "all-containers-no-published-ports")

def sample(names, stage):
    raw = cmd("docker", "stats", "--no-stream", "--format",
              "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", *names)
    lines = raw.splitlines()
    require(len(lines) == len(names), "resource-sample-" + stage)
    for line in lines:
        print("OBS_DOCKER_STATS=" + stage + "|" + line, flush=True)

def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("CI-only; not a deployable script")
    prefix = "obs450-" + secrets.token_hex(5)
    names = {k: prefix + "-" + k for k in IMAGES}
    network = prefix
    prom_data = prefix + "-prom-data"
    graf_data = prefix + "-graf-data"
    password = secrets.token_urlsafe(32)
    auth = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
    # Avoid external proxy environment variables for loopback requests.
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    with tempfile.TemporaryDirectory(prefix="obs450-") as tmp:
        config = Path(tmp) / "prometheus.yml"
        config.write_text("global:\n  scrape_interval: 30s\n  scrape_timeout: 10s\n"
                          "scrape_configs:\n  - job_name: node\n"
                          "    static_configs:\n      - targets: ['node:9100']\n")
        config.chmod(0o644)
        try:
            images = {}
            for key, tag in IMAGES.items():
                cmd("docker", "pull", tag)
                image = cmd("docker", "image", "inspect", "--format", "{{.Id}}", tag)
                require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", image)), "image-id-" + key)
                print("OBS_IMAGE=" + key + "|" + tag + "|" + image, flush=True)
                images[key] = image
            cmd("docker", "network", "create", "--internal", network)
            cmd("docker", "volume", "create", prom_data)
            cmd("docker", "volume", "create", graf_data)
            def start(key, memory, *args, tail=()):
                cmd("docker", "run", "-d", "--name", names[key], "--network", network,
                    "--network-alias", key, "--memory", memory, "--memory-swap", memory,
                    "--cpus", "0.75", "--pids-limit", "128", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", *args, images[key], *tail)
            start("node", "128m", tail=("--collector.disable-defaults", "--collector.cpu",
                  "--collector.meminfo", "--collector.filesystem", "--collector.netdev",
                  "--collector.filesystem.fs-types-exclude=^$"))
            start("prom", "512m",
                  "--mount", "type=bind,src=" + str(config) + ",dst=/etc/prometheus/prometheus.yml,readonly",
                  "--mount", "type=volume,src=" + prom_data + ",dst=/prometheus",
                  tail=("--config.file=/etc/prometheus/prometheus.yml",
                        "--storage.tsdb.path=/prometheus",
                        "--storage.tsdb.retention.time=7d",
                        "--storage.tsdb.retention.size=512MB"))
            start("grafana", "384m",
                  "--mount", "type=volume,src=" + graf_data + ",dst=/var/lib/grafana",
                  "-e", "GF_SECURITY_ADMIN_PASSWORD=" + password,
                  "-e", "GF_AUTH_ANONYMOUS_ENABLED=false",
                  "-e", "GF_ANALYTICS_REPORTING_ENABLED=false",
                  "-e", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
                  "-e", "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false")
            require_no_published_ports(names.values())
            require(cmd("docker", "network", "inspect", "--format", "{{.Internal}}", network) == "true",
                    "internal-network")
            prom = internal_url(names["prom"], network, 9090)
            graf = internal_url(names["grafana"], network, 3000)
            eventually(lambda: up(prom) == 1, "first scrape")
            require(api(prom, "/api/v1/status/buildinfo")["data"]["version"] == "3.13.5",
                    "prometheus-version")
            require(bool(query(prom, 'node_exporter_build_info{version="1.13.1"}')),
                    "exporter-version")
            eventually(lambda: api(graf, "/api/health").get("database") == "ok", "grafana health")
            require(api(graf, "/api/health").get("version") == "13.3.2", "grafana-version")
            expressions = {
                "cpu": "node_cpu_seconds_total",
                "memory": "node_memory_MemAvailable_bytes",
                "disk": "node_filesystem_avail_bytes",
                "network": "node_network_receive_bytes_total",
            }
            for label, expression in expressions.items():
                require(bool(query(prom, expression)), "metric-" + label)
            try:
                api(graf, "/api/search")
            except urllib.error.HTTPError as error:
                require(error.code in (401, 403), "grafana-anonymous-denied")
            else:
                raise AssertionError("anonymous Grafana search was allowed")
            api(graf, "/api/datasources", auth, {
                "name": "CI Prometheus", "uid": "obs450-prom", "type": "prometheus",
                "url": "http://prom:9090", "access": "proxy", "isDefault": True,
            })
            proxy = "/api/datasources/proxy/uid/obs450-prom"
            require(bool(query(graf, expressions["memory"], auth=auth, prefix=proxy)),
                    "grafana-datasource-query")
            panels = []
            queries = [
                ("CPU busy %", "100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[2m])))"),
                ("Memory available", expressions["memory"]),
                ("Disk available", expressions["disk"]),
                ("Network RX rate", "rate(node_network_receive_bytes_total[2m])"),
            ]
            for i, (title, expression) in enumerate(queries):
                panels.append({"id": i+1, "type": "timeseries", "title": title,
                               "gridPos": {"x": (i%2)*12, "y": (i//2)*8, "w": 12, "h": 8},
                               "datasource": {"type": "prometheus", "uid": "obs450-prom"},
                               "targets": [{"refId": "A", "expr": expression}]})
            api(graf, "/api/dashboards/db", auth, {"dashboard": {
                "uid": "obs450-ci", "title": "CI infrastructure experiment",
                "schemaVersion": 39, "panels": panels, "time": {"from": "now-15m", "to": "now"},
            }, "overwrite": False})
            require(len(api(graf, "/api/dashboards/uid/obs450-ci", auth)["dashboard"]["panels"]) == 4,
                    "grafana-dashboard")
            # 30s scrape interval: ensure enough distinct samples for rate/history.
            eventually(lambda: float(query(prom, 'count_over_time(up{job="node"}[3m])')[0]["value"][1]) >= 3,
                       "three scrapes")
            require(bool(query(prom, queries[0][1])), "cpu-rate")
            require(bool(query(prom, queries[3][1])), "network-rate")
            t_before = time.time()
            require(up(prom) == 1, "history-before-restart")
            sample(list(names.values()), "steady")
            head = api(prom, "/api/v1/status/tsdb")["data"]["headStats"]
            print("OBS_HEAD_SERIES=" + str(head["numSeries"]), flush=True)
            print("OBS_TSDB_KIB=" + cmd("docker", "exec", names["prom"], "du", "-sk", "/prometheus").split()[0],
                  flush=True)
            cmd("docker", "stop", names["node"])
            eventually(lambda: up(prom) == 0, "target down")
            require(True, "target-down")
            cmd("docker", "start", names["node"])
            eventually(lambda: up(prom) == 1, "target recovered")
            require(True, "target-recovered")
            cmd("docker", "restart", names["prom"], names["grafana"])
            prom = internal_url(names["prom"], network, 9090)
            graf = internal_url(names["grafana"], network, 3000)
            eventually(lambda: up(prom) == 1, "prom restarted")
            require(float(query(prom, 'up{job="node"}', timestamp=t_before)[0]["value"][1]) == 1,
                    "prometheus-history-after-restart")
            eventually(lambda: api(graf, "/api/health").get("database") == "ok", "grafana restarted")
            require(len(api(graf, "/api/dashboards/uid/obs450-ci", auth)["dashboard"]["panels"]) == 4,
                    "grafana-dashboard-after-restart")
            sample(list(names.values()), "restart")
            print("OBS_P1_SMOKE=PASS", flush=True)
        except Exception:
            for key, name in names.items():
                state = cmd("docker", "inspect", "--format",
                            "{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}",
                            name, allow_failure=True)
                if re.fullmatch(r"[a-z]+\|\d+\|(true|false)", state):
                    print("OBS_CONTAINER_STATE=" + key + "|" + state, flush=True)
            raise
        finally:
            for name in names.values():
                cmd("docker", "rm", "-f", name, allow_failure=True)
            for volume in (prom_data, graf_data):
                cmd("docker", "volume", "rm", volume, allow_failure=True)
            cmd("docker", "network", "rm", network, allow_failure=True)

if __name__ == "__main__":
    main()
