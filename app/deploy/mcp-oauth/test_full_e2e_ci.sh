#!/usr/bin/env bash
# GitHub runner ONLY. Live Keycloak + MySQL + PRP Java + TLS Nginx. No production access.
set -euo pipefail
if [[ "$GITHUB_ACTIONS" != "true" || -z "$RUNNER_TEMP" ]]; then
  echo "A disposable GitHub Actions runner is required" >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"
tmp="$RUNNER_TEMP/prp-mcp-real-pkce"
mkdir -p "$tmp/nginx" "$tmp/certs"
export MCP_E2E_KC_ADMIN_PASSWORD MCP_E2E_KC_USER_PASSWORD MCP_E2E_PRP_PASSWORD MCP_E2E_CA_CERT
MCP_E2E_CA_CERT="$tmp/certs/ca.pem"
MCP_E2E_KC_ADMIN_PASSWORD="$(openssl rand -hex 24)"
MCP_E2E_KC_USER_PASSWORD="$(openssl rand -hex 24)"
MCP_E2E_PRP_PASSWORD="$(openssl rand -hex 24)"
database_root="$(openssl rand -hex 24)"
database_user="$(openssl rand -hex 24)"
prp_jwt_secret="$(openssl rand -hex 32)"
for secret in "$MCP_E2E_KC_ADMIN_PASSWORD" "$MCP_E2E_KC_USER_PASSWORD" "$MCP_E2E_PRP_PASSWORD" "$database_root" "$database_user" "$prp_jwt_secret"; do
  echo "::add-mask::$secret"
done
backend_pid=""
cleanup() {
  docker rm -f prp-ci-real-keycloak prp-ci-real-nginx prp-ci-real-mysql >/dev/null 2>&1 || true
  if [[ -n "$backend_pid" ]]; then kill "$backend_pid" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

# Disposable runner hosts file only; no external DNS changes.
echo '127.0.0.1 auth-e2e.localhost prp-e2e.localhost' | sudo tee -a /etc/hosts >/dev/null

openssl req -x509 -new -newkey rsa:2048 -nodes -days 1 \
  -keyout "$tmp/certs/ca.key" -out "$tmp/certs/ca.pem" \
  -subj '/CN=PRP-E2E-Disposable-CA' >/dev/null 2>&1
openssl req -new -newkey rsa:2048 -nodes -keyout "$tmp/certs/leaf.key" \
  -out "$tmp/certs/leaf.csr" -subj '/CN=auth-e2e.localhost' >/dev/null 2>&1
printf '%s\n' 'subjectAltName=DNS:auth-e2e.localhost,DNS:prp-e2e.localhost' \
  'extendedKeyUsage=serverAuth' > "$tmp/certs/leaf.ext"
openssl x509 -req -in "$tmp/certs/leaf.csr" \
  -CA "$tmp/certs/ca.pem" -CAkey "$tmp/certs/ca.key" -CAcreateserial \
  -out "$tmp/certs/leaf.pem" -days 1 -extfile "$tmp/certs/leaf.ext" >/dev/null 2>&1

cat > "$tmp/nginx/default.conf" <<'NGINX'
server {
    listen 127.0.0.1:443 ssl;
    server_name auth-e2e.localhost;
    ssl_certificate /etc/nginx/certs/leaf.pem;
    ssl_certificate_key /etc/nginx/certs/leaf.key;
    if ($host != auth-e2e.localhost) { return 421; }
    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host auth-e2e.localhost;
        proxy_set_header X-Forwarded-Host auth-e2e.localhost;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
    }
}
server {
    listen 127.0.0.1:443 ssl;
    server_name prp-e2e.localhost;
    ssl_certificate /etc/nginx/certs/leaf.pem;
    ssl_certificate_key /etc/nginx/certs/leaf.key;
    if ($host != prp-e2e.localhost) { return 421; }
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host prp-e2e.localhost;
        proxy_set_header X-Forwarded-Host prp-e2e.localhost;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 45s;
        proxy_buffering off;
    }
}
NGINX

docker run --rm -d --name prp-ci-real-mysql \
  -p 127.0.0.1:13306:3306 \
  -e MYSQL_ROOT_PASSWORD="$database_root" \
  -e MYSQL_DATABASE=matrix_prp_mcp_e2e \
  -e MYSQL_USER=prp_e2e \
  -e MYSQL_PASSWORD="$database_user" mysql:8.4 >/dev/null
for i in $(seq 1 45); do
  if docker exec prp-ci-real-mysql mysqladmin ping --silent >/dev/null 2>&1; then break; fi
  sleep 2
done
docker exec prp-ci-real-mysql mysqladmin ping --silent >/dev/null
echo "E2E MySQL: isolated empty database ready."

python3 app/deploy/mcp-oauth/build_realm.py \
  --resource https://prp-e2e.localhost/api/mcp \
  --staging-client-id prp-pkce-probe \
  --staging-redirect http://127.0.0.1:8765/callback \
  --output "$tmp/keycloak-realm.json"
mkdir -p "$tmp/import"
cp "$tmp/keycloak-realm.json" "$tmp/import/prp-mcp-realm.json"
docker run --rm -d --name prp-ci-real-keycloak \
  -p 127.0.0.1:18080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=prp-ci-admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD="$MCP_E2E_KC_ADMIN_PASSWORD" \
  -v "$tmp/import:/opt/keycloak/data/import:ro" \
  quay.io/keycloak/keycloak:26.8.0 start-dev --import-realm \
  --features=cimd,resource-indicators \
  --hostname=https://auth-e2e.localhost --proxy-headers=xforwarded >/dev/null

docker run --rm --network host \
  -v "$tmp/nginx:/etc/nginx/conf.d:ro" -v "$tmp/certs:/etc/nginx/certs:ro" \
  nginx:1.29-alpine nginx -t >/dev/null
docker run --rm -d --network host --name prp-ci-real-nginx \
  -v "$tmp/nginx:/etc/nginx/conf.d:ro" -v "$tmp/certs:/etc/nginx/certs:ro" \
  nginx:1.29-alpine >/dev/null

# CI-only CA imported into a PRIVATE Java truststore (no global trust changes).
cp "$JAVA_HOME/lib/security/cacerts" "$tmp/java-truststore.jks"
keytool -importcert -noprompt -alias prp-e2e-ci-ca \
  -file "$tmp/certs/ca.pem" -keystore "$tmp/java-truststore.jks" \
  -storepass changeit >/dev/null 2>&1

(
  cd app/backend
  chmod +x mvnw
  ./mvnw -B -ntp -DskipTests package > "$tmp/java-build.log" 2>&1
)
echo "E2E PRP: Java 21 JAR built from review branch."
export MATRIX_PRP_DB_URL="jdbc:mysql://127.0.0.1:13306/matrix_prp_mcp_e2e?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
export MATRIX_PRP_DB_USER="prp_e2e"
export MATRIX_PRP_DB_PASSWORD="$database_user"
export MATRIX_PRP_JWT_SECRET="$prp_jwt_secret"
export MATRIX_PRP_BOOTSTRAP_USERNAME="stage_admin"
export MATRIX_PRP_BOOTSTRAP_PASSWORD="$MCP_E2E_PRP_PASSWORD"
export MATRIX_PRP_FLYWAY_ENABLED="true"
export MATRIX_PRP_MCP_ENABLED="true"
export MATRIX_PRP_MCP_OAUTH_ENABLED="true"
export MATRIX_PRP_MCP_WRITE_ENABLED="false"
export MATRIX_PRP_MCP_ALLOWED_ORIGINS="https://prp-e2e.localhost"
export MATRIX_PRP_MCP_OAUTH_ISSUER="https://auth-e2e.localhost/realms/prp-mcp"
export MATRIX_PRP_MCP_OAUTH_JWK_SET_URI="https://auth-e2e.localhost/realms/prp-mcp/protocol/openid-connect/certs"
export MATRIX_PRP_MCP_OAUTH_RESOURCE="https://prp-e2e.localhost/api/mcp"
export MATRIX_PRP_AI_SPRING_AI_ENABLED="false"
export MATRIX_PRP_AI_SPRING_AI_TOOLS_ENABLED="false"
java -Djavax.net.ssl.trustStore="$tmp/java-truststore.jks" \
  -Djavax.net.ssl.trustStorePassword=changeit \
  -jar app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar \
  > "$tmp/prp-backend.log" 2>&1 &
backend_pid="$!"

# Only generic PASS/failure step names are printed by the browser driver.
python3 app/deploy/mcp-oauth/ci_pkce_browser.py
echo "PASS: real Keycloak browser PKCE, owner grant, identity link and MCP protocol."
