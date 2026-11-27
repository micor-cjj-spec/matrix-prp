"""CI-only fixed-target, bounded metric projection; not a production auth gateway."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import re
import urllib.request

TARGETS = {
    "/nginx/metrics": "http://nginx-exporter:9113/metrics",
    "/keycloak/metrics": "http://keycloak:9000/metrics",
}
NGINX = {
    "nginx_up", "nginx_connections_active", "nginx_connections_accepted",
    "nginx_connections_handled", "nginx_connections_reading",
    "nginx_connections_writing", "nginx_connections_waiting", "nginx_http_requests_total",
}
KC = {
    "jvm_memory_used_bytes", "jvm_memory_committed_bytes", "jvm_threads_live_threads",
    "agroal_active_count", "agroal_available_count", "agroal_awaiting_count",
    "http_server_requests_seconds_count", "http_server_requests_seconds_sum",
}
# Exact fixture discovery route or framework route template; no arbitrary paths.
URI = re.compile(r"/?realms/(?:master|\{[A-Za-z][A-Za-z0-9_]*\})/\.well-known/(?:openid-configuration|\{[A-Za-z][A-Za-z0-9_]*\})")
LABEL = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"')
LINE = re.compile(r'([A-Za-z_:][A-Za-z0-9_:]*)(?:\{(.*)\})?\s+([-+0-9.eE]+|NaN|[+-]?Inf)(?:\s+[-+0-9.eE]+)?')
POOLS = {"G1 Eden Space", "G1 Survivor Space", "G1 Old Gen", "Metaspace",
         "Compressed Class Space", "Code Cache", "CodeHeap 'non-nmethods'",
         "CodeHeap 'profiled nmethods'", "CodeHeap 'non-profiled nmethods'",
         "Eden Space", "Survivor Space", "Tenured Gen", "PS Eden Space",
         "PS Survivor Space", "PS Old Gen"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def safe_labels(family, labels):
    if family in NGINX or family == "jvm_threads_live_threads":
        return not labels
    if family.startswith("jvm_memory_"):
        return set(labels) == {"area", "id"} and labels["area"] in {"heap", "nonheap", "non-heap"} and labels["id"] in POOLS
    if family.startswith("agroal_"):
        return labels == {"datasource": "default"}
    if family.startswith("http_"):
        return (set(labels) == {"method", "status", "outcome", "uri"}
                and labels["method"] in {"GET", "POST", "HEAD", "OPTIONS"}
                and labels["outcome"] in {"INFORMATIONAL", "SUCCESS", "REDIRECTION", "CLIENT_ERROR", "SERVER_ERROR", "UNKNOWN"}
                and re.fullmatch(r"[1-5][0-9][0-9]", labels["status"])
                and URI.fullmatch(labels["uri"]))
    return False


def project(body, target):
    families = NGINX if target == "/nginx/metrics" else KC
    output = []
    for line in body.splitlines():
        m = LINE.fullmatch(line)
        if not m or m[1] not in families:
            continue
        labels = dict(LABEL.findall(m[2] or ""))
        # Require exact grammar for any labels; do not silently strip unsupported tags.
        if m[2] and ",".join(k + '="' + v + '"' for k, v in labels.items()) != m[2].rstrip(","):
            continue
        if not safe_labels(m[1], labels):
            continue
        output.append(line)
    if not output or len(output) > 200:
        raise ValueError("projection empty or exceeds limit")
    return ("\n".join(output) + "\n").encode()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(8)
        super().setup()

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path not in TARGETS:
            self.send_error(404)
            return
        try:
            with OPENER.open(TARGETS[self.path], timeout=4) as response:
                if response.status != 200 or response.geturl() != TARGETS[self.path]:
                    raise OSError("unexpected upstream response")
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise OSError("response too large")
                body = project(raw.decode(), self.path)
        except (OSError, ValueError):
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9105), Handler).serve_forever()
