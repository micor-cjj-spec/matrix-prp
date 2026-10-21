#!/usr/bin/env bash
# Only run on disposable GitHub Actions hosts. Does not touch production.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" || -z "${RUNNER_TEMP:-}" ]]; then
  echo "Disposable GitHub Actions runner required" >&2
  exit 2
fi
cd "$(dirname "$0")"
tmp="${RUNNER_TEMP}/prp-stage-tls"
mkdir -p "$tmp/conf.d"
python3 prepare_env.py
trap 'docker rm -f prp-mcp-stage-tls-ci >/dev/null 2>&1 || true; kill "${fake_pid:-}" >/dev/null 2>&1 || true; rm -f .env' EXIT
python3 render_tls.py --env-file .env --output "$tmp/conf.d/staging.conf"
# Self-signed 24-hour test certificates; NOT operator/production certificates.
for host in prp-test.micor.top auth-test.micor.top; do
  mkdir -p "$tmp/letsencrypt/live/$host"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$tmp/letsencrypt/live/$host/privkey.pem" \
    -out "$tmp/letsencrypt/live/$host/fullchain.pem" \
    -subj "/CN=$host" >/dev/null 2>&1
done
# Remap only the disposable local listener; production output still uses port 443.
sed -i 's/listen 443 ssl;/listen 127.0.0.1:18443 ssl;/g' "$tmp/conf.d/staging.conf"
python3 tls_fake_upstreams.py &
fake_pid=$!
mounts=(-v "$tmp/conf.d:/etc/nginx/conf.d:ro" -v "$tmp/letsencrypt:/etc/letsencrypt:ro")
docker run --rm --network host "${mounts[@]}" nginx:1.29-alpine nginx -t
docker run --rm -d --network host --name prp-mcp-stage-tls-ci \
  "${mounts[@]}" nginx:1.29-alpine >/dev/null

check_route() {
  local host="$1" path="$2" expected="$3" body
  body="$(curl --fail -ksS --retry 6 --retry-connrefused --retry-delay 2 \
    --noproxy '*' --resolve "$host:18443:127.0.0.1" "https://$host:18443$path")"
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["backend"]==sys.argv[2]; assert d["host"]==sys.argv[3]; assert d["forwarded_host"]==sys.argv[3]; assert d["forwarded_proto"]=="https"; assert d["path"]==sys.argv[4]' \
    "$body" "$expected" "$host" "$path"
}
check_route prp-test.micor.top /prp/ stage-prp
check_route prp-test.micor.top /api/mcp stage-prp
check_route prp-test.micor.top /.well-known/oauth-protected-resource/api/mcp stage-prp
check_route auth-test.micor.top /realms/prp-mcp/.well-known/openid-configuration stage-keycloak

status() {
  curl -ksS --noproxy '*' -o /dev/null -w '%{http_code}' \
    --resolve "$1:18443:127.0.0.1" -H "Host: $2" "https://$1:18443$3"
}
test "$(status auth-test.micor.top auth-test.micor.top /admin/)" = 404
test "$(status auth-test.micor.top auth-test.micor.top /realms/master/protocol/openid-connect/token)" = 404
test "$(status auth-test.micor.top micor.top /realms/prp-mcp)" = 421
test "$(status prp-test.micor.top micor.top /api/mcp)" = 421
echo "PASS: real disposable TLS Nginx isolates staging PRP/Keycloak upstreams; admin/master and forged Host are denied."
