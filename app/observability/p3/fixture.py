"""Disposable synthetic metrics and bounded local Webhook only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

STATE = Path("/control/state.json")
START = time.monotonic()
LOCK = threading.Lock()
EVENTS = []
LIMIT = 128


def state():
    value = json.loads(STATE.read_text())
    if not isinstance(value, dict):
        raise ValueError("fixture state")
    return value


def metrics(kind, faults):
    n = max(0, time.monotonic()-START)
    if kind == "node":
        return [
            f'node_cpu_seconds_total{{cpu="0",mode="idle"}} {n*.9}',
            'node_memory_MemTotal_bytes 1000',
            f'node_memory_MemAvailable_bytes {50 if faults.get("node") else 500}',
            'node_filesystem_size_bytes{mountpoint="/"} 1000',
            'node_filesystem_avail_bytes{mountpoint="/"} '+str(100 if faults.get("node") else 600),
        ]
    if kind == "http_health":
        return ["probe_success "+str(0 if faults.get("probe") else 1)]
    if kind == "https_health":
        return ["probe_success 1", "probe_ssl_earliest_cert_expiry "+str(int(time.time())+30*86400)]
    if kind == "p2-mysql":
        return ["mysql_up "+str(0 if faults.get("mysql") else 1)]
    if kind == "p2-nginx":
        return ["nginx_up "+str(0 if faults.get("nginx") else 1)]
    if kind == "p2-ci":
        return ["prp_ci_projection_fresh "+str(0 if faults.get("stale") else 1),
                'prp_ci_run_state{state="failure"} '+str(1 if faults.get("ci_failure") else 0)]
    if kind == "p2-app":
        return [f'http_server_requests_seconds_count{{status="200",method="GET",uri="/api/health"}} {100+n*2}',
                f'http_server_requests_seconds_sum{{status="200",method="GET",uri="/api/health"}} {10+n*.1}']
    if kind == "p2-cgroup":
        return ["container_memory_usage_bytes 33554432"]
    if kind == "p2-keycloak":
        return ["jvm_threads_live_threads 70"]
    raise ValueError("unknown fixed kind")


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):
        pass

    def reply(self,status,body,content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.server.mode == "webhook":
            if self.path != "/events":
                self.send_error(404)
                return
            with LOCK:
                body=json.dumps(EVENTS,separators=(",",":")).encode()
            self.reply(200,body)
            return
        if not self.path.startswith("/metrics/"):
            self.send_error(404)
            return
        kind=self.path.removeprefix("/metrics/")
        try:
            faults=state()
            if faults.get("scrape_down") == kind:
                self.send_error(503)
                return
            payload=("\n".join(metrics(kind,faults))+"\n").encode()
            self.reply(200,payload,"text/plain; version=0.0.4")
        except (ValueError,OSError):
            self.send_error(503)

    def do_POST(self):
        if self.server.mode!="webhook" or self.path!="/receive":
            self.send_error(404)
            return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=65536:
                raise ValueError("body limit")
            data=json.loads(self.rfile.read(size))
            alerts=data.get("alerts")
            if not isinstance(alerts,list) or not 0<len(alerts)<=20:
                raise ValueError("alert limit")
            rows=[]
            for alert in alerts:
                labels=alert["labels"]
                if labels.get("environment")!="synthetic":
                    raise ValueError("non-synthetic")
                rows.append({"name":labels["alertname"],"job":labels["job"],
                             "instance":labels["instance"],"status":alert["status"],
                             "severity":labels["severity"]})
            code=503 if state().get("receiver_fail") else 200
            with LOCK:
                if len(EVENTS)>=LIMIT:
                    self.send_error(429)
                    return
                EVENTS.append({"code":code,"status":data["status"],"alerts":rows,
                               "group":data["groupLabels"],"truncated":data["truncatedAlerts"]})
            self.reply(code,b"{}")
        except (KeyError,TypeError,ValueError,OSError):
            self.send_error(400)


if __name__=="__main__":
    if len(sys.argv)!=2 or sys.argv[1] not in ("metrics","webhook"):
        raise SystemExit("synthetic fixture only")
    server=ThreadingHTTPServer(("0.0.0.0",8080),Handler)
    server.mode=sys.argv[1]
    server.serve_forever()
