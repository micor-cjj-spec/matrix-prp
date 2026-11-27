"""Hosted CI only: exercise real Blackbox Exporter and Prometheus with synthetic targets."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid


HERE = Path(__file__).resolve().parent
IMAGES = {
    "blackbox": "quay.io/prometheus/blackbox-exporter:v0.29.1",
    "prom": "quay.io/prometheus/prometheus:v3.13.5",
    "fixture": "python:3.12-alpine",
}
EXPECTED = {
    "healthy": (1, 200),
    "misdirected": (0, 421),
    "unavailable": (0, 503),
    "timeout": (0, 0),
    "redirect": (0, 302),
    "recovery": (0, 503),
    "http_only": (1, 200),
    "no_content": (0, 204),
    "tls_valid": (1, 200),
    "tls_wrong_name": (0, 0),
    "tls_untrusted": (0, 0),
}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def cmd(*args, timeout=120):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} exited {result.returncode}: {result.stderr[-1200:]}")
    return result.stdout.strip()


def get(url):
    with OPENER.open(url, timeout=5) as response:
        return response.read()


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print("OBS_P2_CASE=" + label + ":PASS", flush=True)


def eventually(test, label, seconds=65):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            if test():
                return
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            last = type(exc).__name__
        time.sleep(1)
    raise AssertionError(f"{label}: timed out; last={last}")


def inspect(name):
    return json.loads(cmd("docker", "inspect", name))[0]


def certs(directory):
    # Synthetic keys are generated per run, never taken from PRP.
    ca, cakey = directory / "ca.crt", directory / "ca.key"
    leaf, key, csr = directory / "leaf.crt", directory / "leaf.key", directory / "leaf.csr"
    ext = directory / "leaf.ext"
    ext.write_text("subjectAltName=DNS:health-fixture\nextendedKeyUsage=serverAuth\n")
    cmd("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3",
        "-subj", "/CN=P2 synthetic CA", "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", str(cakey), "-out", str(ca))
    cmd("openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
        "-subj", "/CN=health-fixture", "-keyout", str(key), "-out", str(csr))
    cmd("openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca), "-CAkey", str(cakey),
        "-CAcreateserial", "-days", "2", "-extfile", str(ext), "-out", str(leaf))
    for path in (ca, leaf, key):
        path.chmod(0o644)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("disposable GitHub-hosted runner required")
    suffix = uuid.uuid4().hex[:12]
    network = "p2-probe-" + suffix
    foreign = "p2-foreign-" + suffix
    names = {k: "p2-" + k + "-" + suffix for k in IMAGES}
    created, networks = [], []
    refs = {}
    try:
        for key, image in IMAGES.items():
            cmd("docker", "pull", "--platform", "linux/amd64", image, timeout=300)
            info = json.loads(cmd("docker", "image", "inspect", image))[0]
            require(info["Os"] == "linux" and info["Architecture"] == "amd64", "image-" + key)
            repo = image.rsplit(":", 1)[0]
            # Docker Hub official image may have an implicit library/ prefix.
            matching = [x for x in info.get("RepoDigests", []) if
                        x.split("@", 1)[0] in (repo, "library/" + repo, "docker.io/library/" + repo)]
            require(bool(matching), "image-digest-" + key)
            refs[key] = matching[0]
            print("OBS_P2_IMAGE=" + key + "|" + refs[key], flush=True)
        for net in (network, foreign):
            cmd("docker", "network", "create", "--internal", net)
            networks.append(net)
            require(inspect(net)["Internal"], "internal-" + ("probe" if net == network else "foreign"))
        with tempfile.TemporaryDirectory(prefix="p2-cert-") as temp:
            directory = Path(temp)
            directory.chmod(0o755)
            certs(directory)
            def mount(source, target):
                return ["--mount", f"type=bind,src={source},dst={target},readonly"]

            def run(key, flags, tail=()):
                name = names[key]
                cmd("docker", "run", "-d", "--pull", "never", "--name", name,
                    "--network", network, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--cpus", "0.75", "--pids-limit", "128", *flags, refs[key], *tail)
                created.append(name)
                return inspect(name)["NetworkSettings"]["Networks"][network]["IPAddress"]

            fixture_ip = run("fixture", [
                "--network-alias", "health-fixture", "--network-alias", "wrong-fixture",
                "--user", "65534:65534", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=8m,mode=1777",
                "--memory", "96m", "--memory-swap", "96m",
                *mount(HERE / "fixture.py", "/fixture.py"),
                *mount(directory / "leaf.crt", "/fixture-tls/leaf.crt"),
                *mount(directory / "leaf.key", "/fixture-tls/leaf.key"),
            ], ["python", "/fixture.py"])
            eventually(lambda: b"UP" in get("http://" + fixture_ip + ":8080/api/health"), "fixture ready")
            bb_ip = run("blackbox", [
                "--network-alias", "blackbox", "--read-only", "--memory", "128m", "--memory-swap", "128m",
                *mount(HERE / "blackbox.yml", "/etc/blackbox/config.yml"),
                *mount(directory / "ca.crt", "/etc/blackbox/fixture-ca.crt"),
            ], ["--config.file=/etc/blackbox/config.yml"])
            eventually(lambda: bool(get("http://" + bb_ip + ":9115/metrics")), "blackbox ready")
            prom_ip = run("prom", [
                "--memory", "512m", "--memory-swap", "512m",
                *mount(HERE / "prometheus.yml", "/etc/prometheus/prometheus.yml"),
            ], ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                "--storage.tsdb.retention.time=1h"])
            base = "http://" + prom_ip + ":9090"
            eventually(lambda: bool(get(base + "/-/ready")), "prometheus ready")

            def query(expression):
                raw = get(base + "/api/v1/query?" + urllib.parse.urlencode({"query": expression}))
                payload = json.loads(raw)
                assert payload["status"] == "success"
                return payload["data"]["result"]

            def values(metric):
                rows = query(metric)
                assert all(row["metric"].get("environment") == "synthetic" for row in rows)
                return {row["metric"]["instance"]: float(row["value"][1]) for row in rows}

            expected_success = {k: v[0] for k, v in EXPECTED.items()}
            expected_status = {k: v[1] for k, v in EXPECTED.items()}
            eventually(lambda: values("probe_success") == expected_success and
                       values("probe_http_status_code") == expected_status and
                       values("up") == {k: 1 for k in EXPECTED}, "all fixed probe cases")
            for key in EXPECTED:
                require(True, key)
            require(len(values("probe_success")) == len(EXPECTED), "fixed-instance-set")
            require(all(v == 1 for v in values("up").values()), "exporter-up-despite-target-failure")
            duration = values("probe_duration_seconds")
            require(1.5 <= duration["timeout"] <= 3.5, "bounded-timeout")
            require(0 <= duration["healthy"] < 2, "response-latency")
            expiry = values("probe_ssl_earliest_cert_expiry")
            remaining = expiry["tls_valid"] - time.time()
            require(0 < remaining < 3 * 86400, "verified-cert-expiry")
            print("OBS_P2_TLS_REMAINING_SECONDS=" + str(round(remaining)), flush=True)
            stamp = values("timestamp(probe_success)")["recovery"]
            cmd("docker", "exec", names["fixture"], "touch", "/tmp/recovered")
            eventually(lambda: values("probe_success").get("recovery") == 1 and
                       values("probe_http_status_code").get("recovery") == 200 and
                       values("timestamp(probe_success)").get("recovery", 0) > stamp, "recovery")
            require(True, "failure-to-recovery-new-sample")

            for name in created:
                info = inspect(name)
                require(not info["HostConfig"].get("Privileged") and
                        not info["HostConfig"].get("PortBindings") and
                        set(info["NetworkSettings"]["Networks"]) == {network},
                        "private-no-published-port-" + name.split("-")[1])
                require(not any(m.get("Source", "").endswith("docker.sock") for m in info["Mounts"]),
                        "no-docker-socket-" + name.split("-")[1])
                require(info["State"]["Running"] and not info["State"]["OOMKilled"],
                        "running-" + name.split("-")[1])
            # An unrelated disposable bridge cannot access the raw exporter.
            # A static Prometheus target list does NOT make /probe an allowlist.
            # This is an isolated network test, not a real host security claim.
            negative = """import sys, urllib.request, urllib.error
try:
    urllib.request.urlopen(sys.argv[1], timeout=3)
except urllib.error.HTTPError:
    sys.exit(2)
except (urllib.error.URLError, OSError):
    sys.exit(0)
sys.exit(3)
"""
            cmd("docker", "run", "--rm", "--pull", "never", "--network", foreign,
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", "64m", "--memory-swap", "64m", "--cpus", "0.25",
                refs["fixture"], "python", "-c", negative, "http://" + bb_ip + ":9115/metrics")
            require(True, "unrelated-network-denied")
            print("OBS_P2_STATS=" + cmd("docker", "stats", "--no-stream", "--format",
                  "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}", *created).replace("\n", ";"), flush=True)
            # Distinguish exporter outage from probe_success=0.
            cmd("docker", "stop", names["blackbox"])
            eventually(lambda: values("up") == {k: 0 for k in EXPECTED}, "exporter outage")
            require(True, "exporter-outage-distinct")
            cmd("docker", "start", names["blackbox"])
            expected_success["recovery"] = 1
            expected_status["recovery"] = 200
            eventually(lambda: values("up") == {k: 1 for k in EXPECTED} and
                       values("probe_success") == expected_success and
                       values("probe_http_status_code") == expected_status, "exporter recovery")
            require(True, "exporter-recovery")
            print("OBS_P2_1_AVAILABILITY=PASS", flush=True)
    finally:
        for name in reversed(created):
            cmd("docker", "rm", "-fv", name)
        for net in reversed(networks):
            cmd("docker", "network", "rm", net)


if __name__ == "__main__":
    main()
