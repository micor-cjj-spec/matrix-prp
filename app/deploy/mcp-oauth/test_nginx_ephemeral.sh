#!/usr/bin/env bash
# Disposable GitHub runner only; validates *real* Nginx HTTPS/MCP routing.
set -euo pipefail
test_dir="$RUNNER_TEMP/mcp-nginx"
mkdir -p "$test_dir/routes" "$test_dir/tls"
python3 app/deploy/mcp-oauth/render_nginx.py --host mcp.staging.example.org --output "$test_dir/routes/routes.conf"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 -keyout "$test_dir/tls/key.pem" -out "$test_dir/tls/cert.pem" -subj "/CN=mcp.staging.example.org" >/dev/null 2>&1
cat > "$test_dir/nginx.conf" <<'NGINX'
events { worker_connections 128; }
http {
    access_log off;
    server {
        listen 127.0.0.1:18443 ssl;
        server_name mcp.staging.example.org;
        ssl_certificate /etc/nginx/tls/cert.pem;
        ssl_certificate_key /etc/nginx/tls/key.pem;
        include /etc/nginx/routes/*.conf;
    }
}
NGINX
python3 app/deploy/mcp-oauth/nginx_fake_upstream.py &
fake_backend_pid="$!"
cleanup() {
  docker rm -f prp-mcp-nginx-ci >/dev/null 2>&1 || true
  kill "$fake_backend_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT
mount_flags=(-v "$test_dir/nginx.conf:/etc/nginx/nginx.conf:ro" -v "$test_dir/routes:/etc/nginx/routes:ro" -v "$test_dir/tls:/etc/nginx/tls:ro")
docker run --rm --network host "${mount_flags[@]}" nginx:1.29-alpine nginx -t
docker run --rm -d --network host --name prp-mcp-nginx-ci "${mount_flags[@]}" nginx:1.29-alpine
uri="https://mcp.staging.example.org:18443"
resolve="mcp.staging.example.org:18443:127.0.0.1"
for path in /api/mcp /.well-known/oauth-protected-resource/api/mcp /api/mcp/link; do
  method=POST
  if [[ "$path" == /.well-known/* ]]; then method=GET; fi
  body=$(curl --fail -sSk --retry 6 --retry-connrefused --retry-delay 2 --noproxy '*' --resolve "$resolve" -X "$method" "$uri$path")
  python3 -c 'import json,sys; p=sys.argv[1]; d=json.loads(sys.argv[2]); assert d["path"] == p; assert d["host"] == "mcp.staging.example.org"; assert d["forwarded_host"] == "mcp.staging.example.org"; assert d["forwarded_proto"] == "https"' "$path" "$body"
done
denied=$(curl -sSk -o /dev/null -w '%{http_code}' --noproxy '*' --resolve "$resolve" -H 'Host: attacker.example.org' "$uri/api/mcp")
test "$denied" = 421
wrong_path=$(curl -sSk -o /dev/null -w '%{http_code}' --noproxy '*' --resolve "$resolve" "$uri/prp/api/mcp")
test "$wrong_path" = 404
echo "PASS: real Nginx TLS proxy preserves /api/mcp and discovery paths; wrong Host/path denied."
