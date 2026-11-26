"""CI-only representative metric replay; not a real runtime collector."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import sys
import time

OBS = Path(__file__).resolve().parents[1]
START = time.monotonic()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(name, value, labels=""):
    return f"{name}{labels} {value}"


def body(kind):
    n = int(time.monotonic() - START)
    if kind == "app":
        return "\n".join([
            sample("jvm_memory_used_bytes", 150000000, '{area="heap",id="G1 Old Gen"}'),
            sample("jvm_threads_live_threads", 34),
            sample("process_uptime_seconds", 100+n),
            sample("http_server_requests_seconds_count", 200+n*2, '{method="GET",status="200",uri="/api/health"}'),
            sample("http_server_requests_seconds_sum", 20+n*.1, '{method="GET",status="200",uri="/api/health"}'),
            sample("hikaricp_connections_active", 1, '{pool="p2_fixture_pool"}'),
            sample("hikaricp_connections_pending", 0, '{pool="p2_fixture_pool"}'),
        ])+"\n"
    if kind == "cgroup":
        lines = [
            sample("container_cpu_usage_seconds_total", 100+n*.2, '{cpu="total"}'),
            sample("container_memory_usage_bytes", 32*1024*1024),
            sample("container_spec_memory_limit_bytes", 96*1024*1024),
            sample("container_spec_cpu_quota", 50000),
            sample("container_spec_cpu_period", 100000),
            sample("container_memory_events_max_total", 1+n),
        ]
        source = load("cgroup_contract", OBS/"p2-3"/"ci_cgroups.py")
        assert all(line.split()[0].split("{")[0] in source.FAMILIES for line in lines)
        return "\n".join(lines)+"\n"
    if kind == "mysql":
        vals = {"mysql_up":1, "mysql_global_status_threads_connected":2,
                "mysql_global_variables_max_connections":40, "mysql_global_status_queries":300+n*3,
                "mysql_global_status_innodb_buffer_pool_read_requests":100+n*4,
                "mysql_global_status_innodb_buffer_pool_reads":10+n,
                "mysql_global_status_innodb_data_read":4096+n*512,
                "mysql_global_status_innodb_data_written":8192+n*1024,
                "mysql_global_status_innodb_row_lock_waits":2+n}
        source = load("mysql_contract", OBS/"p2-4"/"ci_mysql.py")
        assert set(vals) <= set(source.METRICS)
        return "\n".join(sample(k,v) for k,v in vals.items())+"\n"
    if kind in ("nginx","keycloak"):
        source = load("gateway_contract", OBS/"p2-5"/"fixed_proxy.py")
        if kind == "nginx":
            lines = [sample("nginx_up",1), sample("nginx_connections_active",3),
                     sample("nginx_connections_waiting",2), sample("nginx_http_requests_total",100+n*2)]
        else:
            labels = '{method="GET",status="200",outcome="SUCCESS",uri="/realms/master/.well-known/openid-configuration"}'
            lines = [sample("jvm_memory_used_bytes",220000000,'{area="heap",id="G1 Old Gen"}'),
                     sample("jvm_threads_live_threads",70), sample("http_server_requests_seconds_count",100+n,labels),
                     sample("http_server_requests_seconds_sum",10+n*.1,labels),
                     sample("agroal_active_count",1,'{datasource="default"}'),
                     sample("agroal_available_count",3,'{datasource="default"}'),
                     sample("agroal_awaiting_count",0,'{datasource="default"}'),
                     sample("jvm_memory_used_bytes",99,'{area="heap",id="private-marker"}')]
        return source.project("\n".join(lines), "/"+kind+"/metrics").decode()
    if kind == "ci":
        sys.path.insert(0,str(OBS/"p2-6"))
        from projection import prometheus
        from test_projection import fixture, dump, NOW
        return prometheus(dump(fixture()), NOW+120 if Path("/tmp/stale").exists() else NOW)
    raise ValueError("unknown synthetic kind")


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):
        pass

    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        try:
            payload = body(self.server.kind).encode()
            self.send_response(200)
            self.send_header("Content-Type","text/plain; version=0.0.4")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("app","cgroup","mysql","nginx","keycloak","ci"):
        raise SystemExit("only fixed offline fixture kinds")
    server = ThreadingHTTPServer(("0.0.0.0",8080),Handler)
    server.kind = sys.argv[1]
    server.serve_forever()
