"""P1.2 bounded multi-target capacity experiment; disposable hosted CI only."""
import base64
import concurrent.futures
import json
import math
import os
import re
import secrets
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ci_smoke import IMAGES, api, cmd, eventually, internal_url, query, require, require_no_published_ports, sample

TARGETS = 4
SERIES = 2500
INTERVAL = 10
DURATION = 240

def scalar(base, expr, auth=None, prefix=""):
    rows = query(base, expr, auth=auth, prefix=prefix)
    return float(rows[0]["value"][1]) if len(rows) == 1 else None

def fixture_count(base):
    return scalar(base, 'count(prp_ci_fixture_value)')

def healthy(base):
    return scalar(base, 'sum(up{job="fixture"})')

def write_fixture(directory, tick):
    path = directory / "fixture.next"
    with path.open("w", encoding="ascii") as f:
        f.write("# TYPE prp_ci_fixture_value gauge\n")
        for i in range(SERIES):
            f.write('prp_ci_fixture_value{slot="%04d"} %d\n' %
                    (i, (i * 17 + tick * (1 + i % 19)) % 100003))
    path.chmod(0o644)
    path.replace(directory / "fixture.prom")

def disk_size(name):
    return int(cmd("docker", "exec", name, "du", "-sk", "/prometheus").split()[0])

def blocks(name):
    paths = cmd("docker", "exec", name, "find", "/prometheus",
                "-mindepth", "2", "-maxdepth", "2", "-name", "meta.json").splitlines()
    result = []
    for path in paths:
        if not re.fullmatch(r"/prometheus/[0-9A-Z]{26}/meta\.json", path):
            raise AssertionError("unexpected TSDB metadata path")
        meta = json.loads(cmd("docker", "exec", name, "cat", path))
        if meta["stats"]["numSamples"] > 0:
            result.append(meta)
    return result

def timed_query(base, graf, auth, task):
    start = time.monotonic()
    proxy = "/api/datasources/proxy/uid/obs450-cap"
    if task == 0:
        assert scalar(base, 'count(prp_ci_fixture_value)') == TARGETS * SERIES
    elif task == 1:
        assert scalar(graf, 'sum(up{job="fixture"})', auth=auth, prefix=proxy) == TARGETS
    else:
        now = int(time.time())
        params = urllib.parse.urlencode({
            "query": 'sum by (instance) (prp_ci_fixture_value)',
            "start": str(now - 60), "end": str(now), "step": "10",
        })
        target = base if task == 2 else graf
        route = "" if task == 2 else proxy
        result = api(target, route + "/api/v1/query_range?" + params,
                     auth=None if task == 2 else auth)
        assert result["status"] == "success" and len(result["data"]["result"]) == TARGETS
        assert all(row["values"] for row in result["data"]["result"])
    return (time.monotonic() - start) * 1000

def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("CI-only; never run on PRP host")
    prefix = "obscap450-" + secrets.token_hex(5)
    network = prefix
    names = {key: prefix + "-" + key for key in ("prom", "grafana", "node", "fixture1", "fixture2", "fixture3", "fixture4")}
    prom_data, graf_data = prefix + "-prom", prefix + "-graf"
    password = secrets.token_urlsafe(32)
    auth = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    with tempfile.TemporaryDirectory(prefix="obscap450-") as tmp:
        root = Path(tmp)
        fixtures = root / "fixtures"
        fixtures.mkdir(mode=0o755)
        write_fixture(fixtures, 0)
        config = root / "prometheus.yml"
        targets = ", ".join("'fixture%d:9100'" % i for i in range(1, TARGETS+1))
        config.write_text("global:\n  scrape_interval: 10s\n  scrape_timeout: 5s\n"
                          "scrape_configs:\n  - job_name: node\n"
                          "    static_configs:\n      - targets: ['node:9100']\n"
                          "  - job_name: fixture\n    sample_limit: 3000\n"
                          "    static_configs:\n      - targets: [" + targets + "]\n")
        config.chmod(0o644)
        try:
            images = {}
            for key, tag in IMAGES.items():
                cmd("docker", "pull", tag)
                images[key] = cmd("docker", "image", "inspect", "--format", "{{.Id}}", tag)
                require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", images[key])), "cap-image-" + key)
                print("OBS_CAP_IMAGE=" + key + "|" + images[key], flush=True)
            cmd("docker", "network", "create", "--internal", network)
            cmd("docker", "volume", "create", prom_data)
            cmd("docker", "volume", "create", graf_data)
            def start(key, image, memory, *args, tail=()):
                cmd("docker", "run", "-d", "--name", names[key], "--network", network,
                    "--network-alias", key, "--memory", memory, "--memory-swap", memory,
                    "--cpus", "0.75", "--pids-limit", "128", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", *args, images[image], *tail)
            def start_fixture(i):
                start("fixture%d" % i, "node", "64m",
                      "--mount", "type=bind,src=" + str(fixtures) + ",dst=/fixtures,readonly",
                      tail=("--collector.disable-defaults", "--collector.textfile",
                            "--collector.textfile.directory=/fixtures"))
            start("node", "node", "128m", tail=("--collector.disable-defaults", "--collector.cpu",
                  "--collector.meminfo", "--collector.filesystem", "--collector.netdev"))
            start_fixture(1)
            start("prom", "prom", "512m",
                  "--mount", "type=bind,src=" + str(config) + ",dst=/etc/prometheus/prometheus.yml,readonly",
                  "--mount", "type=volume,src=" + prom_data + ",dst=/prometheus",
                  tail=("--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                        "--storage.tsdb.retention.time=7d", "--storage.tsdb.retention.size=512MB",
                        "--storage.tsdb.min-block-duration=1m", "--storage.tsdb.max-block-duration=3m",
                        "--query.max-concurrency=4", "--query.timeout=5s"))
            start("grafana", "grafana", "384m",
                  "--mount", "type=volume,src=" + graf_data + ",dst=/var/lib/grafana",
                  "-e", "GF_SECURITY_ADMIN_PASSWORD=" + password,
                  "-e", "GF_AUTH_ANONYMOUS_ENABLED=false",
                  "-e", "GF_ANALYTICS_REPORTING_ENABLED=false",
                  "-e", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
                  "-e", "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false")
            prom = internal_url(names["prom"], network, 9090)
            graf = internal_url(names["grafana"], network, 3000)
            eventually(lambda: healthy(prom) == 1 and fixture_count(prom) == SERIES
                       and scalar(prom, 'sum(up{job="node"})') == 1,
                       "one fixture and ordinary node ready")
            require(True, "cap-one-target-2500-series")
            sample([names[k] for k in ("prom", "grafana", "node", "fixture1")], "cap-one")
            for i in range(2, TARGETS+1):
                start_fixture(i)
            require_no_published_ports(names.values())
            require(cmd("docker", "network", "inspect", "--format", "{{.Internal}}", network) == "true",
                    "cap-internal-network")
            eventually(lambda: healthy(prom) == TARGETS and fixture_count(prom) == TARGETS * SERIES
                       and scalar(prom, 'sum(up{job="node"})') == 1,
                       "all fixture targets and ordinary node ready")
            require(True, "cap-four-targets-10000-series")
            require(True, "cap-node-up")
            eventually(lambda: api(graf, "/api/health").get("database") == "ok", "grafana health")
            api(graf, "/api/datasources", auth, {"name": "CI capacity", "uid": "obs450-cap",
                "type": "prometheus", "url": "http://prom:9090", "access": "proxy"})
            require(scalar(graf, 'count(prp_ci_fixture_value)', auth=auth,
                           prefix="/api/datasources/proxy/uid/obs450-cap") == TARGETS * SERIES,
                    "cap-grafana-query")
            started = time.monotonic()
            t_history = time.time()
            latencies, sizes, head_series = [], [], []
            tick = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                while time.monotonic() - started < DURATION:
                    write_fixture(fixtures, tick)
                    latencies.extend(pool.map(lambda task: timed_query(prom, graf, auth, task), range(4)))
                    if scalar(prom, 'sum(up{job="node"})') != 1:
                        raise AssertionError("ordinary node lost during sustained load")
                    sizes.append(disk_size(names["prom"]))
                    head = api(prom, "/api/v1/status/tsdb")["data"]["headStats"]["numSeries"]
                    head_series.append(int(head))
                    if tick % 2 == 0:
                        sample(list(names.values()), "cap-load-%02d" % tick)
                        print("OBS_CAP_TSDB_KIB=" + str(sizes[-1]), flush=True)
                        print("OBS_CAP_HEAD_SERIES=" + str(head), flush=True)
                    tick += 1
                    time.sleep(5)
            require(len(latencies) >= 80, "cap-concurrent-query-count")
            ordered = sorted(latencies)
            print("OBS_CAP_QUERY_COUNT=" + str(len(ordered)), flush=True)
            print("OBS_CAP_QUERY_P95_MS=%.2f" % ordered[math.ceil(len(ordered)*0.95)-1], flush=True)
            print("OBS_CAP_QUERY_MAX_MS=%.2f" % max(ordered), flush=True)
            print("OBS_CAP_MAX_TSDB_KIB=" + str(max(sizes)), flush=True)
            print("OBS_CAP_MAX_HEAD_SERIES=" + str(max(head_series)), flush=True)
            eventually(lambda: bool(blocks(names["prom"])), "test-duration persisted blocks", timeout=90)
            persisted = blocks(names["prom"])
            require(bool(persisted), "cap-persisted-block")
            print("OBS_CAP_BLOCKS=" + str(len(persisted)), flush=True)
            print("OBS_CAP_MAX_COMPACTION_LEVEL=" + str(max(x["compaction"]["level"] for x in persisted)), flush=True)
            print("OBS_CAP_BLOCK_SAMPLES=" + str(sum(x["stats"]["numSamples"] for x in persisted)), flush=True)
            require(float(query(prom, 'count(prp_ci_fixture_value)', timestamp=t_history)[0]["value"][1])
                    == TARGETS * SERIES, "cap-historical-query")
            cmd("docker", "stop", names["fixture4"])
            eventually(lambda: healthy(prom) == 3 and fixture_count(prom) == 3 * SERIES,
                       "isolated target failure")
            require(scalar(prom, 'sum(up{job="node"})') == 1, "cap-node-unaffected")
            require(True, "cap-three-targets-still-healthy")
            cmd("docker", "start", names["fixture4"])
            eventually(lambda: healthy(prom) == TARGETS and fixture_count(prom) == TARGETS * SERIES,
                       "target recovery")
            require(True, "cap-target-recovery")
            for key, name in names.items():
                state = cmd("docker", "inspect", "--format", "{{.State.Running}}|{{.State.OOMKilled}}", name)
                require(state == "true|false", "cap-no-oom-" + key)
            print("OBS_P1_CAPACITY=PASS", flush=True)
        except Exception:
            for key, name in names.items():
                state = cmd("docker", "inspect", "--format",
                            "{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}",
                            name, allow_failure=True)
                if re.fullmatch(r"[a-z]+\|\d+\|(true|false)", state):
                    print("OBS_CAP_CONTAINER_STATE=" + key + "|" + state, flush=True)
            raise
        finally:
            for name in names.values():
                cmd("docker", "rm", "-f", name, allow_failure=True)
            for volume in (prom_data, graf_data):
                cmd("docker", "volume", "rm", volume, allow_failure=True)
            cmd("docker", "network", "rm", network, allow_failure=True)

if __name__ == "__main__":
    main()
