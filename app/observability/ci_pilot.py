"""Exercise the exact P1.3 compose candidate on a disposable Linux hosted runner."""
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from ci_smoke import IMAGES, api, cmd, eventually, internal_url, query, require, require_no_published_ports

def digest(key):
    tag = IMAGES[key]
    cmd("docker", "pull", tag)
    refs = json.loads(cmd("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag))
    repo = tag.rsplit(":", 1)[0]
    for ref in refs:
        if ref.split("@")[0] in (repo, "docker.io/" + repo) and re.search(r"@sha256:[0-9a-f]{64}$", ref):
            print("OBS_PILOT_DIGEST=" + key + "|" + ref, flush=True)
            return ref
    raise AssertionError("missing repository digest")

def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("CI only")
    require(os.geteuid() != 0, "pilot-collector-nonroot")
    project = "obspilot450" + secrets.token_hex(5)
    network, extract = project + "-net", project + "-extract"
    password = secrets.token_urlsafe(32)
    auth = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    compose_file = str(Path(__file__).resolve().parent / "pilot" / "compose.yml")
    compose = ("docker", "compose", "-p", project, "-f", compose_file)
    proc = None
    with tempfile.TemporaryDirectory(prefix=project) as tmp:
        try:
            node, prom_image, graf_image = (digest(key) for key in ("node", "prom", "grafana"))
            cmd("docker", "network", "create", "--internal", network)
            require(cmd("docker", "network", "inspect", "--format", "{{.Internal}}", network) == "true", "pilot-network-internal")
            gateway = cmd("docker", "network", "inspect", "--format", "{{(index .IPAM.Config 0).Gateway}}", network)
            require(ipaddress.IPv4Address(gateway).is_private, "pilot-private-gateway")
            os.environ.update(PRP_MON_PROM_IMAGE=prom_image, PRP_MON_GRAF_IMAGE=graf_image,
                              PRP_MON_GATEWAY=gateway, PRP_MON_NETWORK=network,
                              PRP_MON_GRAFANA_PASSWORD=password)
            cmd("docker", "create", "--name", extract, "--network", "none", node)
            binary = Path(tmp) / "node_exporter"
            cmd("docker", "cp", extract + ":/bin/node_exporter", str(binary))
            cmd("docker", "rm", extract)
            print("OBS_PILOT_NODE_BINARY_SHA256=" + hashlib.sha256(binary.read_bytes()).hexdigest(), flush=True)
            binary.chmod(0o700)
            proc = subprocess.Popen([str(binary), "--web.listen-address=" + gateway + ":9100",
                "--collector.disable-defaults", "--collector.cpu", "--collector.meminfo",
                "--collector.filesystem", "--collector.filesystem.mount-points-include=^/$",
                "--collector.netdev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            def native_ready():
                if proc.poll() is not None:
                    raise AssertionError("native exporter exited")
                with urllib.request.urlopen("http://" + gateway + ":9100/metrics", timeout=3) as response:
                    return response.status == 200
            eventually(native_ready, "native collector on bridge")
            require(True, "pilot-native-collector")
            listeners = cmd("ss", "-H", "-ltn", "sport", "=", ":9100").splitlines()
            require(len(listeners) == 1 and listeners[0].split()[3] == gateway + ":9100",
                    "pilot-collector-only-bridge-listener")
            cmd(*compose, "config", "--quiet")
            cmd(*compose, "up", "-d", "--no-build")
            names = [cmd(*compose, "ps", "-q", k) for k in ("prometheus", "grafana")]
            require(all(names), "pilot-compose-start")
            require_no_published_ports(names)
            prom = internal_url(names[0], network, 9090)
            graf = internal_url(names[1], network, 3000)
            eventually(lambda: len(query(prom, 'up{job="node"} == 1')) == 1, "native target scraped")
            require(True, "pilot-native-scrape")
            require(bool(query(prom, 'node_exporter_build_info{version="1.13.1"}')), "pilot-node-version")
            require(api(prom, "/api/v1/status/buildinfo")["data"]["version"] == "3.13.5", "pilot-prom-version")
            memory = int(re.search(r"^MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)[1]) * 1024
            actual = query(prom, "node_memory_MemTotal_bytes")
            require(len(actual) == 1 and float(actual[0]["value"][1]) == memory, "pilot-host-memory")
            cpus = {x[3:] for x in re.findall(r"^cpu\d+", Path("/proc/stat").read_text(), re.M)}
            observed = {x["metric"]["cpu"] for x in query(prom, 'node_cpu_seconds_total{mode="idle"}')}
            require(cpus == observed and bool(cpus), "pilot-host-cpu")
            fs = os.statvfs("/")
            actual = query(prom, 'node_filesystem_size_bytes{mountpoint="/"}')
            require(len(actual) == 1 and float(actual[0]["value"][1]) == fs.f_blocks * fs.f_frsize,
                    "pilot-host-root-filesystem")
            default_devices = {row.split()[0] for row in Path("/proc/net/route").read_text().splitlines()[1:]
                               if row.split()[1] == "00000000"}
            observed = {x["metric"]["device"] for x in query(prom, "node_network_receive_bytes_total")}
            require(bool(default_devices) and default_devices.issubset(observed) and "lo" in observed,
                    "pilot-host-network")
            eventually(lambda: api(graf, "/api/health").get("database") == "ok", "grafana health")
            require(api(graf, "/api/health").get("version") == "13.3.2", "pilot-graf-version")
            try:
                api(graf, "/api/search")
            except urllib.error.HTTPError as e:
                require(e.code in (401, 403), "pilot-anonymous-denied")
            else:
                raise AssertionError("anonymous access")
            api(graf, "/api/datasources", auth, {"name":"Pilot Prometheus","uid":"obs450-pilot",
                "type":"prometheus","url":"http://prometheus:9090","access":"proxy"})
            require(bool(query(graf, "node_memory_MemTotal_bytes", auth=auth,
                               prefix="/api/datasources/proxy/uid/obs450-pilot")), "pilot-graf-query")
            for name, limit in zip(names, (512, 384)):
                config = json.loads(cmd("docker", "inspect", "--format", "{{json .HostConfig}}", name))
                require(config["Memory"] == config["MemorySwap"] == limit * 1024 * 1024
                        and config["NanoCpus"] == 750000000 and config["PidsLimit"] == 128
                        and not config["Privileged"] and "ALL" in config["CapDrop"],
                        "pilot-runtime-limits-" + str(limit))
            cmd(*compose, "down")
            require(not cmd(*compose, "ps", "-aq"), "pilot-down-containers")
            require(len(cmd("docker", "volume", "ls", "-q", "--filter",
                            "label=com.docker.compose.project=" + project).splitlines()) == 2,
                    "pilot-down-preserves-data")
            print("OBS_P1_PILOT=PASS", flush=True)
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            cmd(*compose, "down", "-v", allow_failure=True)
            cmd("docker", "rm", "-f", extract, allow_failure=True)
            cmd("docker", "network", "rm", network, allow_failure=True)

if __name__ == "__main__":
    main()
