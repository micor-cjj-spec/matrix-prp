"""Disposable CI fixed-target HTTP adapter; not an authorization or TLS product."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.error

UPSTREAM = "http://exporter:9104/metrics"
MAX_BYTES = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(6)
        super().setup()

    def log_message(self, *_):
        pass

    def do_GET(self):
        # Exact path, no query, no redirects, no caller-controlled target or forwarded headers.
        if self.path != "/metrics":
            self.send_error(404)
            return
        try:
            request = urllib.request.Request(UPSTREAM, headers={"X-Prometheus-Scrape-Timeout-Seconds": "4"})
            with OPENER.open(request, timeout=5) as response:
                if response.status != 200:
                    raise OSError("upstream status")
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise OSError("upstream response limit")
                content_type = response.headers.get("Content-Type", "text/plain")
        except (OSError, ValueError):
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9105), Handler).serve_forever()
