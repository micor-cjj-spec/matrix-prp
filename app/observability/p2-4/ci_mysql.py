"""Disposable GitHub-hosted MySQL monitoring acceptance; never run on a PRP host."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
IMAGES = {
    "mysql": "mysql:8.4",
    "exporter": "quay.io/prometheus/mysqld-exporter:v0.18.0",
    "prom": "quay.io/prometheus/prometheus:v3.13.5",
    "proxy": "python:3.12-alpine",
}
METRICS = (
    "mysql_up", "mysql_exporter_collector_success",
    "mysql_global_status_uptime", "mysql_global_status_threads_connected",
    "mysql_global_status_connections", "mysql_global_status_aborted_connects",
    "mysql_global_status_queries", "mysql_global_status_questions",
    "mysql_global_status_commands_total",
    "mysql_global_variables_max_connections",
    "mysql_global_status_innodb_buffer_pool_read_requests",
    "mysql_global_status_innodb_buffer_pool_reads",
    "mysql_global_status_buffer_pool_pages",
    "mysql_global_status_innodb_data_read", "mysql_global_status_innodb_data_written",
    "mysql_global_status_innodb_row_lock_waits", "mysql_global_status_innodb_row_lock_time",
    "mysql_global_status_innodb_deadlocks",
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SECRET_VALUES = []


def safe(value):
    for secret in SECRET_VALUES:
        value = value.replace(secret, "[REDACTED]")
    return value


def cmd(*args, timeout=120, check=True):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if p.returncode and check:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {safe(p.stderr[-1800:])}")
    return p.stdout.strip() if check else p


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("OBS_P24_CASE=" + name + ":PASS", flush=True)


def eventually(fn, name, timeout=100):
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                return result
        except (OSError, RuntimeError, AssertionError, ValueError, KeyError) as exc:
            last = safe(str(exc))[:180]
        time.sleep(1)
    raise AssertionError(name + " timed out: " + last)


def inspect(name):
    return json.loads(cmd("docker", "inspect", name))[0]


def get(url):
    with OPENER.open(url, timeout=8) as response:
        return response.read().decode()


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("disposable GitHub-hosted runner required")
    token = uuid.uuid4().hex[:12]
    dbnet, monnet = "p24-db-" + token, "p24-monitor-" + token
    names = {key: "p24-" + key + "-" + token for key in IMAGES}
    refs, created, networks = {}, [], []
    rootpass, monitorpass = secrets.token_hex(24), secrets.token_hex(24)
    SECRET_VALUES.extend((rootpass, monitorpass))
    schema, table = "p24_fixture", "private_marker_" + token
    try:
        for key, image in IMAGES.items():
            cmd("docker", "pull", "--platform", "linux/amd64", image, timeout=300)
            data = json.loads(cmd("docker", "image", "inspect", image))[0]
            check(data["Os"] == "linux" and data["Architecture"] == "amd64", "image-" + key)
            repo = image.rsplit(":", 1)[0]
            matches = [d for d in data.get("RepoDigests", []) if d.split("@", 1)[0]
                       in (repo, "library/" + repo, "docker.io/library/" + repo)]
            check(bool(matches), "digest-" + key)
            refs[key] = matches[0]
            print("OBS_P24_IMAGE=" + key + "|" + refs[key], flush=True)
        for net in (dbnet, monnet):
            cmd("docker", "network", "create", "--internal", net)
            networks.append(net)
            check(inspect(net)["Internal"], "private-" + net.split("-")[1])

        def mount(source, dest):
            return ["--mount", f"type=bind,src={source},dst={dest},readonly"]

        def run(key, net, flags, args, restricted=True):
            name = names[key]
            base = ["docker", "run", "-d", "--pull", "never", "--name", name,
                    "--network", net, "--security-opt", "no-new-privileges", "--pids-limit", "192"]
            if restricted:
                base += ["--cap-drop", "ALL"]
            cmd(*base, *flags, refs[key], *args)
            created.append(name)
            return inspect(name)["NetworkSettings"]["Networks"][net]["IPAddress"]

        dbip = run("mysql", dbnet, ["--network-alias", "mysql", "--memory", "768m",
                   "--memory-swap", "768m", "--cpus", "1.0", "-e", "MYSQL_ROOT_PASSWORD=" + rootpass],
                   ["--skip-name-resolve", "--max-connections=40", "--innodb-buffer-pool-size=64M",
                    "--performance-schema=ON"], restricted=False)
        def root(sql, check_rc=True):
            return cmd("docker", "exec", "-e", "MYSQL_PWD=" + rootpass, names["mysql"],
                       "mysql", "--protocol=socket", "-uroot", "-N", "-B", "-e", sql,
                       timeout=15, check=check_rc)

        eventually(lambda: root("SELECT 1") == "1", "mysql ready", 150)
        version = root("SELECT VERSION()")
        check(version.startswith("8.4."), "mysql-8.4")
        subnet = ipaddress.ip_network(inspect(dbnet)["IPAM"]["Config"][0]["Subnet"])
        exporter_ip = str(subnet.broadcast_address - 2)
        check(exporter_ip != dbip, "dedicated-exporter-address")
        # Only a new, empty, synthetic denial-test table; never read a business record.
        root(f"CREATE DATABASE {schema}; CREATE TABLE {schema}.{table} (id INT PRIMARY KEY); "
             f"CREATE USER 'p24_monitor'@'{exporter_ip}' IDENTIFIED BY '{monitorpass}' "
             "WITH MAX_USER_CONNECTIONS 2;")
        grants = root(f"SHOW GRANTS FOR 'p24_monitor'@'{exporter_ip}'").splitlines()
        check(len(grants) == 1 and grants[0].startswith("GRANT USAGE ON *.* TO ")
              and "MAX_USER_CONNECTIONS 2" in grants[0] and "GRANT OPTION" not in grants[0],
              "usage-only-grant")
        with tempfile.TemporaryDirectory(prefix="p24-config-") as td:
            config = Path(td) / "client.cnf"
            config.write_text("[client]\nuser=p24_monitor\npassword=" + monitorpass +
                              "\nhost=mysql\nport=3306\n")
            # Parent directory is private; container-mounted file must be readable by nobody.
            config.chmod(0o444)
            exip = run("exporter", dbnet, ["--ip", exporter_ip, "--network-alias", "exporter",
                        "--user", "65534:65534", "--read-only", "--memory", "128m",
                        "--memory-swap", "128m", "--cpus", "0.5", *mount(config, "/client.cnf")],
                        ["--config.my-cnf=/client.cnf", "--mysqld.address=mysql:3306",
                         "--collect.global_status", "--collect.global_variables",
                         "--no-collect.slave_status", "--no-collect.info_schema.innodb_cmp",
                         "--no-collect.info_schema.innodb_cmpmem",
                         "--no-collect.info_schema.query_response_time",
                         "--web.listen-address=:9104", "--exporter.lock_wait_timeout=2"])
            check(exip == exporter_ip, "exporter-exact-ip")

            # Disposable client shares only the exporter's network namespace for same account-host test.
            def monitor_args(sql):
                return ["docker", "run", "--rm", "--pull", "never", "--network",
                        "container:" + names["exporter"], "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges", "--memory", "128m",
                        "--memory-swap", "128m", "--cpus", "0.25", "--entrypoint", "mysql",
                        "-e", "MYSQL_PWD=" + monitorpass, refs["mysql"], "-h", dbip,
                        "-up24_monitor", "--connect-timeout=3", "-N", "-B", "-e", sql]

            check(cmd(*monitor_args("SELECT CURRENT_USER()")) ==
                  "p24_monitor@" + exporter_ip, "exact-account-host")
            check("Threads_connected" in cmd(*monitor_args("SHOW GLOBAL STATUS LIKE 'Threads_connected'")),
                  "usage-global-status")
            check("max_connections" in cmd(*monitor_args("SHOW GLOBAL VARIABLES LIKE 'max_connections'")),
                  "usage-global-variables")
            for label, sql in (
                ("table-select", f"SELECT * FROM {schema}.{table}"),
                ("table-insert", f"INSERT INTO {schema}.{table} VALUES (1)"),
                ("table-update", f"UPDATE {schema}.{table} SET id=2"),
                ("table-delete", f"DELETE FROM {schema}.{table}"),
                ("system-user-select", "SELECT User FROM mysql.user"),
                ("schema-create", "CREATE DATABASE p24_denied"),
            ):
                result = cmd(*monitor_args(sql), check=False)
                check(result.returncode != 0 and ("denied" in result.stderr.lower()
                      or "ERROR 1044" in result.stderr or "ERROR 1142" in result.stderr),
                      "denied-" + label)
            check(root(f"SELECT COUNT(*) FROM {schema}.{table}") == "0", "empty-synthetic-table")

            holders = []
            try:
                for _ in range(2):
                    holders.append(subprocess.Popen(monitor_args("SELECT SLEEP(20)"),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                eventually(lambda: root("SELECT COUNT(*) FROM information_schema.PROCESSLIST "
                                        "WHERE USER='p24_monitor'") == "2",
                           "two fixture monitor connections", 12)
                third = cmd(*monitor_args("SELECT 1"), check=False)
                check(third.returncode != 0 and ("1226" in third.stderr or
                      "max_user_connections" in third.stderr.lower()), "connection-limit-enforced")
            finally:
                for proc in holders:
                    try:
                        proc.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
            eventually(lambda: root("SELECT COUNT(*) FROM information_schema.PROCESSLIST "
                                    "WHERE USER='p24_monitor'") == "0", "fixture connections closed")

            px = run("proxy", dbnet, ["--user", "65534:65534", "--read-only", "--memory", "64m",
                     "--memory-swap", "64m", "--cpus", "0.25",
                     *mount(HERE / "fixed_proxy.py", "/fixed_proxy.py")], ["python", "/fixed_proxy.py"])
            cmd("docker", "network", "connect", "--alias", "fixed-metrics", monnet, names["proxy"])
            proxyip = inspect(names["proxy"])["NetworkSettings"]["Networks"][monnet]["IPAddress"]
            url = "http://" + proxyip + ":9105"
            raw = eventually(lambda: get(url + "/metrics"), "fixed proxy scrape")
            check("mysql_up 1" in raw, "usage-only-mysql-up")
            check(all(secret not in raw for secret in SECRET_VALUES) and table not in raw
                  and schema not in raw and "p24_monitor" not in raw, "no-raw-sensitive-markers")
            for path in ("/probe", "/probe?target=mysql:3306", "/metrics?target=mysql:3306",
                         "/metrics?collect[]=global_status", "/metrics/", "/"):
                try:
                    get(url + path)
                    raise AssertionError("unexpected proxy path accepted")
                except urllib.error.HTTPError as exc:
                    check(exc.code == 404, "deny-proxy-path-" + str(len(path)) + "-" + str(path.count("?")))
            try:
                req = urllib.request.Request(url + "/metrics", method="POST", data=b"")
                OPENER.open(req, timeout=5)
                raise AssertionError("POST accepted")
            except urllib.error.HTTPError as exc:
                check(exc.code in (405, 501), "deny-proxy-post")

            conf = Path(td) / "prom.yml"
            conf.write_text(json.dumps({
                "global": {"scrape_interval": "5s", "scrape_timeout": "4s"},
                "scrape_configs": [{"job_name": "p2-mysql", "sample_limit": 200,
                    "label_limit": 10, "static_configs": [{"targets": ["fixed-metrics:9105"],
                        "labels": {"environment": "synthetic", "instance": "fixture-mysql"}}],
                    "metric_relabel_configs": [
                        {"source_labels": ["__name__"], "regex": "|".join(METRICS), "action": "keep"},
                        {"regex": "__name__|job|instance|environment|command|collector|state",
                         "action": "labelkeep"},
                    ]}]}))
            conf.chmod(0o644)
            prom = run("prom", monnet, ["--memory", "256m", "--memory-swap", "256m",
                       "--cpus", "0.5", *mount(conf, "/etc/prometheus/prometheus.yml")],
                       ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                        "--storage.tsdb.retention.time=1h"])
            base = "http://" + prom + ":9090"
            def query(expr):
                result = json.loads(get(base + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})))
                assert result["status"] == "success"
                return result["data"]["result"]

            def scalar(expr):
                rows = query(expr)
                assert len(rows) == 1, "expected one series: " + expr
                return float(rows[0]["value"][1])

            eventually(lambda: scalar("up") == 1 and scalar("mysql_up") == 1, "projected mysql up")
            collectors = query("mysql_exporter_collector_success")
            check({row["metric"].get("collector") for row in collectors} ==
                  {"collect.global_status", "collect.global_variables"} and
                  all(float(row["value"][1]) == 1 for row in collectors),
                  "only-intended-collectors-success")
            check(scalar("mysql_global_variables_max_connections") == 40, "max-connections-parity")
            check(1 <= scalar("mysql_global_status_threads_connected") <= 3, "threads-connected-range")
            actual_uptime = int(root("SHOW GLOBAL STATUS LIKE 'Uptime'").split("\t")[1])
            check(abs(actual_uptime - scalar("mysql_global_status_uptime")) <= 15, "uptime-parity")
            select = 'mysql_global_status_commands_total{command="select"}'
            before = scalar(select)
            root("SELECT 1;" * 12)
            eventually(lambda: scalar(select) >= before + 12, "select-command-counter-delta")
            check(True, "select-command-delta")
            for status in ("Innodb_buffer_pool_read_requests", "Innodb_buffer_pool_reads",
                           "Innodb_data_read", "Innodb_data_written", "Innodb_row_lock_waits"):
                value = int(root(f"SHOW GLOBAL STATUS LIKE '{status}'").split("\t")[1])
                observed = scalar("mysql_global_status_" + status.lower())
                check(0 <= observed <= value, "innodb-" + status.lower())
            all_rows = query('{job="p2-mysql"}')
            check(0 < len(all_rows) <= 205 and all(
                set(row["metric"]) <= {"__name__", "job", "instance", "environment", "command",
                                      "collector", "state"} for row in all_rows), "bounded-projected-labels")
            projected = json.dumps(all_rows)
            check(not any(marker in projected for marker in (schema, table, "p24_monitor", dbip,
                      exporter_ip, *SECRET_VALUES)), "no-sensitive-tsdb-labels")
            print("OBS_P24_SERIES=" + str(len(all_rows)), flush=True)

            # Test an actual peer on the scrape network cannot connect to DB or exporter.
            denied = """import socket,sys
for target,port in ((sys.argv[1],3306),(sys.argv[2],9104)):
    try:
        with socket.create_connection((target,port),timeout=3):
            raise SystemExit(1)
    except OSError:
        pass
"""
            cmd("docker", "run", "--rm", "--pull", "never", "--network", monnet,
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "64m",
                "--memory-swap", "64m", "--cpus", "0.25", refs["proxy"],
                "python", "-c", denied, dbip, exporter_ip)
            check(True, "scrape-network-cannot-reach-db-exporter")
            for key in IMAGES:
                info = inspect(names[key])
                host = info["HostConfig"]
                allowed = {dbnet, monnet} if key == "proxy" else ({monnet} if key == "prom" else {dbnet})
                check(not host["Privileged"] and not host.get("PortBindings")
                      and set(info["NetworkSettings"]["Networks"]) == allowed
                      and host["PidMode"] != "host" and host["NetworkMode"] != "host"
                      and not any("docker.sock" in m["Source"] or "docker.sock" in m["Destination"]
                                  for m in info["Mounts"]), "isolation-" + key)
            print("OBS_P24_STATS=" + cmd("docker", "stats", "--no-stream", "--format",
                  "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}", *created).replace("\n", ";"), flush=True)
            cmd("docker", "stop", names["mysql"])
            eventually(lambda: scalar("up") == 1 and scalar("mysql_up") == 0, "database down")
            check(True, "database-down-vs-scrape-up")
            cmd("docker", "start", names["mysql"])
            restarted = time.time()
            eventually(lambda: root("SELECT 1") == "1", "mysql restarted", 150)
            eventually(lambda: scalar("up") == 1 and scalar("mysql_up") == 1
                       and scalar("timestamp(mysql_up)") > restarted, "database fresh recovery", 100)
            check(True, "database-fresh-recovery")
            cmd("docker", "stop", names["proxy"])
            eventually(lambda: scalar("up") == 0 and not query("mysql_up"), "scrape path down")
            check(True, "scrape-path-down-not-db-zero")
            cmd("docker", "start", names["proxy"])
            recovered = time.time()
            eventually(lambda: scalar("up") == 1 and scalar("mysql_up") == 1
                       and scalar("timestamp(mysql_up)") > recovered, "scrape fresh recovery")
            check(True, "scrape-fresh-recovery")
            print("OBS_P24_USAGE_CORE=PASS", flush=True)
    except Exception:
        print("OBS_P24_USAGE_CORE=NO_GO", flush=True)
        for key in ("mysql", "exporter", "proxy"):
            if names[key] in created:
                log = cmd("docker", "logs", "--tail", "35", names[key], check=False)
                print(safe((log.stdout + log.stderr)[-3500:]), flush=True)
        raise
    finally:
        for name in reversed(created):
            cmd("docker", "rm", "-fv", name, check=False)
        for net in reversed(networks):
            cmd("docker", "network", "rm", net, check=False)


if __name__ == "__main__":
    main()
