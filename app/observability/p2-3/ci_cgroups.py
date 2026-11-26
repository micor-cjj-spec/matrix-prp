"""CI-only: test restricted raw cgroup v2 collection without privilege fallback."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
CG = Path("/sys/fs/cgroup")
IMAGES = {
    "cadvisor": "ghcr.io/google/cadvisor:v0.60.1",
    "prom": "quay.io/prometheus/prometheus:v3.13.5",
    "fixture": "python:3.12-alpine",
}
FAMILIES = (
    "container_cpu_usage_seconds_total", "container_memory_usage_bytes",
    "container_spec_memory_limit_bytes", "container_spec_cpu_quota",
    "container_spec_cpu_period", "container_memory_events_max_total",
    "container_blkio_device_usage_total", "container_last_seen",
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd(*args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {p.stderr[-1800:]}")
    return p.stdout.strip()


def check(value, name):
    if not value:
        raise AssertionError(name)
    print("OBS_P23_CASE=" + name + ":PASS", flush=True)


def eventually(fn, name, timeout=70):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            result = fn()
            if result:
                return result
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            last = str(exc)[:160]
        time.sleep(1)
    raise AssertionError(name + " timed out: " + str(last))


def inspect(name):
    return json.loads(cmd("docker", "inspect", name))[0]


def get(url):
    with OPENER.open(url, timeout=5) as r:
        return r.read().decode()


def kernel_int(path):
    return int(path.read_text().strip())


def cpu_seconds(path):
    values = dict(line.split() for line in (path / "cpu.stat").read_text().splitlines())
    return int(values["usage_usec"]) / 1e6


def io_bytes(path):
    total = 0
    for line in (path / "io.stat").read_text().splitlines():
        fields = dict(item.split("=") for item in line.split()[1:])
        total += int(fields.get("wbytes", "0"))
    return total


def cgroup(name):
    info = inspect(name)
    pid = info["State"]["Pid"]
    if pid <= 0:
        raise AssertionError("fixture not running")
    text = Path(f"/proc/{pid}/cgroup").read_text()
    relative = next(line.split(":", 2)[2] for line in text.splitlines() if line.startswith("0::"))
    path = (CG / relative.lstrip("/")).resolve()
    # Use only the exact runner-created container identity, not an arbitrary cgroup.
    assert path.is_relative_to(CG) and info["Id"] in path.name and path != CG
    assert (path / "memory.current").is_file() and (path / "cpu.stat").is_file()
    return relative, path


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("disposable GitHub-hosted runner required")
    check((CG / "cgroup.controllers").is_file(), "cgroup-v2")
    suffix = uuid.uuid4().hex[:12]
    network, foreign = "p23-" + suffix, "p23-foreign-" + suffix
    names = {k: "p23-" + k + "-" + suffix for k in IMAGES}
    refs, created, networks = {}, [], []
    try:
        for key, image in IMAGES.items():
            cmd("docker", "pull", "--platform", "linux/amd64", image, timeout=300)
            data = json.loads(cmd("docker", "image", "inspect", image))[0]
            check(data["Os"] == "linux" and data["Architecture"] == "amd64", "image-" + key)
            repo = image.rsplit(":", 1)[0]
            digest = [d for d in data.get("RepoDigests", []) if
                      d.split("@", 1)[0] in (repo, "library/" + repo, "docker.io/library/" + repo)]
            check(bool(digest), "digest-" + key)
            refs[key] = digest[0]
            print("OBS_P23_IMAGE=" + key + "|" + refs[key], flush=True)
        for net in (network, foreign):
            cmd("docker", "network", "create", "--internal", net)
            networks.append(net)
            check(inspect(net)["Internal"], "private-" + net.split("-")[1])

        def mount(source, destination):
            return ["--mount", f"type=bind,src={source},dst={destination},readonly"]

        def run(key, flags, args):
            name = names[key]
            cmd("docker", "run", "-d", "--pull", "never", "--name", name,
                "--network", network, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--cpus", "0.5", "--pids-limit", "128", *flags, refs[key], *args)
            created.append(name)
            return inspect(name)["NetworkSettings"]["Networks"][network]["IPAddress"]

        marker = "p23-private-marker-" + suffix
        run("fixture", ["--memory", "96m", "--memory-swap", "96m", "--user", "65534:65534",
                        "--label", "p23.private=" + marker, "-e", "P23_PRIVATE=" + marker,
                        *mount(HERE / "fixture.py", "/fixture.py")], ["python", "/fixture.py"])
        eventually(lambda: cmd("docker", "exec", names["fixture"], "test", "-f", "/tmp/ready") == "",
                   "fixture ready")
        ident, path = cgroup(names["fixture"])
        check(kernel_int(path / "memory.max") == 96 * 1024 * 1024, "kernel-memory-limit")
        quota, period = map(int, (path / "cpu.max").read_text().split())
        check(quota / period == 0.5, "kernel-cpu-limit")

        ca = run("cadvisor", [
            "--network-alias", "cadvisor", "--user", "65534:65534", "--read-only",
            "--cgroupns", "host", "--memory", "192m", "--memory-swap", "192m",
            *mount(CG, "/sys/fs/cgroup"),
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=8m,mode=1777",
        ], [
            "--port=8080", "--docker_only=true", "--raw_cgroup_prefix_whitelist=" + ident,
            "--disable_root_cgroup_stats=true", "--store_container_labels=false",
            "--enable_metrics=cpu,memory,diskIO", "--housekeeping_interval=2s",
            "--max_housekeeping_interval=2s", "--allow_dynamic_housekeeping=false",
            "--global_housekeeping_interval=5s", "--storage_duration=1m",
        ])
        ci = inspect(names["cadvisor"])
        hc = ci["HostConfig"]
        check(not hc["Privileged"] and hc["ReadonlyRootfs"] and ci["Config"]["User"] == "65534:65534",
              "nonroot-nonprivileged-readonly")
        check(hc["CgroupnsMode"] == "host" and hc["PidMode"] != "host" and hc["NetworkMode"] != "host",
              "cgroup-only-host-namespace")
        check(set(hc["CapDrop"]) == {"ALL"} and not hc.get("CapAdd") and not hc.get("Devices"),
              "no-extra-capabilities-devices")
        check(len(ci["Mounts"]) == 1 and ci["Mounts"][0]["Source"] == str(CG)
              and ci["Mounts"][0]["Destination"] == str(CG) and not ci["Mounts"][0]["RW"],
              "only-readonly-cgroup-bind")

        raw_url = "http://" + ca + ":8080/metrics"
        def raw():
            data = get(raw_url)
            assert marker not in data and "container_label_p23" not in data
            return data
        def raw_values(family):
            rows = []
            for line in raw().splitlines():
                if line.startswith(family + "{") and ('id="' + ident + '"') in line:
                    rows.append(float(line.split("}", 1)[1].split()[0]))
            return rows
        eventually(lambda: raw_values("container_memory_usage_bytes"), "raw fixture memory")
        check(True, "raw-discovery-without-docker-api")
        check(marker not in raw(), "no-fixture-label-or-env-marker")

        with tempfile.TemporaryDirectory(prefix="p23-prom-") as td:
            config = Path(td) / "prometheus.yml"
            # JSON is valid YAML; exact raw identity is used only for relabeling.
            config.write_text(json.dumps({
                "global": {"scrape_interval": "3s", "scrape_timeout": "2s"},
                "scrape_configs": [{
                    "job_name": "p2-cgroup", "sample_limit": 500, "label_limit": 12,
                    "static_configs": [{"targets": ["cadvisor:8080"],
                        "labels": {"environment": "synthetic", "instance": "fixture"}}],
                    "metric_relabel_configs": [
                        {"source_labels": ["id"], "regex": re.escape(ident), "action": "keep"},
                        {"source_labels": ["__name__"], "regex": "|".join(FAMILIES), "action": "keep"},
                        {"regex": "__name__|job|instance|environment|cpu|device|operation", "action": "labelkeep"},
                    ],
                }],
            }))
            config.chmod(0o644)
            prom = run("prom", ["--memory", "256m", "--memory-swap", "256m",
                        *mount(config, "/etc/prometheus/prometheus.yml")], [
                "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                "--storage.tsdb.retention.time=1h",
            ])
            base = "http://" + prom + ":9090"
            def query(expr):
                data = json.loads(get(base + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})))
                assert data["status"] == "success"
                return data["data"]["result"]
            def scalar(metric):
                rows = query(metric)
                assert len(rows) == 1, "expected one series: " + metric
                tags = rows[0]["metric"]
                assert tags.get("instance") == "fixture" and tags.get("environment") == "synthetic"
                assert "id" not in tags and "name" not in tags and "image" not in tags
                return float(rows[0]["value"][1])
            # CPU total can carry a cpu="total" dimension; select only that series.
            cpu = 'container_cpu_usage_seconds_total{cpu="total"}'
            eventually(lambda: scalar("up") == 1 and scalar("container_memory_usage_bytes") > 0,
                       "projected scrape")
            check(scalar("container_spec_memory_limit_bytes") == kernel_int(path / "memory.max"),
                  "memory-limit-parity")
            check(scalar("container_spec_cpu_quota") == quota and scalar("container_spec_cpu_period") == period,
                  "cpu-limit-parity")
            observed = scalar("container_memory_usage_bytes")
            actual = kernel_int(path / "memory.current")
            check(observed >= 24 * 1024 * 1024 and abs(actual - observed) <= 12 * 1024 * 1024,
                  "memory-current-parity")
            before_cpu = scalar(cpu)
            kernel_before = cpu_seconds(path)
            io_before = io_bytes(path)
            cmd("docker", "exec", names["fixture"], "touch", "/tmp/work")
            eventually(lambda: scalar(cpu) > before_cpu + 0.4, "cpu workload delta")
            after_cpu = scalar(cpu)
            kernel_after = cpu_seconds(path)
            check(kernel_after > kernel_before and 0 < after_cpu <= kernel_after + 0.2
                  and kernel_after - after_cpu <= 2.0, "cpu-counter-parity")
            check(scalar("up") == 1, "collector-up")
            io_after = io_bytes(path)
            io_rows = query("container_blkio_device_usage_total")
            print("OBS_P23_IO_KERNEL_WRITE_DELTA=" + str(io_after - io_before), flush=True)
            print("OBS_P23_IO_SERIES=" + str(len(io_rows)), flush=True)
            # Strictly distinguish missing/unproven IO from a zero counter. No privilege fallback.
            writes = [float(row["value"][1]) for row in io_rows
                      if row["metric"].get("operation", "").lower() == "write"]
            if io_after > io_before and writes and sum(writes) > 0:
                print("OBS_P23_BLOCK_IO=OBSERVED_NOT_FULL_PARITY", flush=True)
            else:
                print("OBS_P23_BLOCK_IO=UNSUPPORTED_OR_UNPROVEN", flush=True)
            events = query("container_memory_events_max_total")
            print("OBS_P23_MEMORY_MAX_EVENTS=" + ("PRESENT" if events else "UNAVAILABLE"), flush=True)
            print("OBS_P23_OOM_KILLS=NOT_COLLECTED", flush=True)
            print("OBS_P23_NETWORK_FILESYSTEM=NOT_COLLECTED", flush=True)
            all_rows = query('{job="p2-cgroup"}')
            check(0 < len(all_rows) <= 505 and all(
                set(row["metric"]) <= {"__name__", "job", "instance", "environment", "cpu", "device", "operation"}
                for row in all_rows), "bounded-projected-labels")
            check(not any(ident in json.dumps(row) or marker in json.dumps(row) for row in all_rows),
                  "no-raw-identity-in-tsdb")
            print("OBS_P23_SERIES=" + str(len(all_rows)), flush=True)

            for name in created:
                info = inspect(name)
                host = info["HostConfig"]
                check(not host["Privileged"] and not host.get("PortBindings")
                      and set(info["NetworkSettings"]["Networks"]) == {network}
                      and host["PidMode"] != "host" and host["NetworkMode"] != "host"
                      and not any(m["Destination"].endswith("docker.sock") or m["Source"].endswith("docker.sock")
                                  for m in info["Mounts"]), "isolation-" + name.split("-")[1])
            negative = """import sys,urllib.request,urllib.error
try:
    urllib.request.urlopen(sys.argv[1], timeout=3)
except urllib.error.HTTPError:
    sys.exit(2)
except (OSError,urllib.error.URLError):
    sys.exit(0)
sys.exit(3)
"""
            cmd("docker", "run", "--rm", "--pull", "never", "--network", foreign,
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "64m",
                "--memory-swap", "64m", "--cpus", "0.25", refs["fixture"],
                "python", "-c", negative, raw_url)
            check(True, "unrelated-network-denied")
            print("OBS_P23_STATS=" + cmd("docker", "stats", "--no-stream", "--format",
                  "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}", *created).replace("\n", ";"), flush=True)
            cmd("docker", "stop", names["fixture"])
            eventually(lambda: not query("container_memory_usage_bytes") and scalar("up") == 1,
                       "fixture exit disappearance", timeout=90)
            check(True, "exit-not-collector-outage")
            cmd("docker", "start", names["fixture"])
            restarted_ident, _ = cgroup(names["fixture"])
            check(restarted_ident == ident, "restart-exact-identity")
            eventually(lambda: scalar("container_memory_usage_bytes") >= 24 * 1024 * 1024,
                       "fixture restart")
            check(True, "restart-fresh-series")
            print("OBS_P23_RESTRICTED_CORE=PASS", flush=True)
    except Exception:
        if names["cadvisor"] in created:
            print("OBS_P23_RESTRICTED_CORE=NO_GO", flush=True)
            print(cmd("docker", "logs", "--tail", "60", names["cadvisor"])[:4000], flush=True)
        raise
    finally:
        for name in reversed(created):
            cmd("docker", "rm", "-fv", name)
        for net in reversed(networks):
            cmd("docker", "network", "rm", net)


if __name__ == "__main__":
    main()
