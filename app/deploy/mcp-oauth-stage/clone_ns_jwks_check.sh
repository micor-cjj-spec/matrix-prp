#!/usr/bin/env bash
# Operator-only isolated restore/JWKS rehearsal. No active Realm mutation.
set -Eeuo pipefail
umask 077
DUMP=/root/prp-mcp-backups/snapshot-4G42atvf/keycloak-stage.dump
EXPECTED=0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17
LIVE_DB=prp-mcp-oauth-stage-auth-db-1
LIVE_KC=prp-mcp-oauth-stage-keycloak-1
TAG="prp-kc-ns-$(date -u +%Y%m%d%H%M%S)-$$"
NET="$TAG-net"; VOL="$TAG-vol"; PG="$TAG-pg"; KC="$TAG-kc"
TEMP=$(mktemp -d /tmp/prp-kc-ns-XXXXXXXX)
NETWORK=0; VOLUME=0; DB=0; AUTH=0
cleanup() {
  rc=$?
  trap - EXIT
  if [ "$AUTH" = 1 ]; then docker rm -f "$KC" >/dev/null 2>&1 || rc=1; fi
  if [ "$DB" = 1 ]; then docker rm -f "$PG" >/dev/null 2>&1 || rc=1; fi
  if [ "$NETWORK" = 1 ]; then docker network rm "$NET" >/dev/null 2>&1 || rc=1; fi
  if [ "$VOLUME" = 1 ]; then docker volume rm "$VOL" >/dev/null 2>&1 || rc=1; fi
  rm -rf "$TEMP"
  echo "CLONE_CLEANUP_FINAL_STATUS=$rc"
  exit "$rc"
}
trap cleanup EXIT
echo '=== SAFETY ==='
test "$(id -u)" = 0
test "$(systemctl is-active matrix-prp.service)" = active
test "$(docker inspect "$LIVE_KC" -f '{{.State.Status}}')" = running
test "$(docker inspect "$LIVE_DB" -f '{{.State.Status}}')" = running
test "$(sha256sum "$DUMP" | awk '{print $1}')" = "$EXPECTED"
test "$(head -c 5 "$DUMP")" = PGDMP
test "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -gt 2000000
test "$(df -Pk / | awk 'END {print $4}')" -gt 15000000
command -v nsenter >/dev/null
PG_IMAGE=$(docker inspect "$LIVE_DB" -f '{{.Image}}')
KC_IMAGE=$(docker inspect "$LIVE_KC" -f '{{.Image}}')
PW=$(openssl rand -hex 32)
echo '=== RESTORE PRIVATE POSTGRES ==='
docker network create --internal "$NET" >/dev/null; NETWORK=1
docker volume create "$VOL" >/dev/null; VOLUME=1
docker run --pull never -d --name "$PG" --network "$NET" --network-alias pg-restore --memory 320m --memory-swap 384m --pids-limit 150 --security-opt no-new-privileges:true -e POSTGRES_USER=keycloak_stage -e POSTGRES_DB=keycloak_stage -e POSTGRES_PASSWORD="$PW" -v "$VOL:/var/lib/postgresql/data" "$PG_IMAGE" >/dev/null; DB=1
READY=0
for _ in $(seq 1 60); do
  if docker exec "$PG" pg_isready -U keycloak_stage -d keycloak_stage >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
test "$READY" = 1
docker exec -i "$PG" pg_restore -U keycloak_stage -d keycloak_stage --no-owner --no-acl --exit-on-error < "$DUMP" >/dev/null
COUNT=$(docker exec "$PG" psql -U keycloak_stage -d keycloak_stage -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
test "$COUNT" = 101
echo "RESTORED_TABLES=$COUNT"
echo '=== BOOT PRIVATE KEYCLOAK ==='
docker run --pull never -d --name "$KC" --network "$NET" --memory 1100m --memory-swap 1200m --pids-limit 256 --security-opt no-new-privileges:true -e KC_DB=postgres -e KC_DB_URL=jdbc:postgresql://pg-restore:5432/keycloak_stage -e KC_DB_USERNAME=keycloak_stage -e KC_DB_PASSWORD="$PW" -e KC_HTTP_ENABLED=true -e KC_CACHE=local -e JAVA_OPTS_KC_HEAP='-Xms128m -Xmx512m' "$KC_IMAGE" start-dev --features=cimd,resource-indicators --hostname=http://127.0.0.1:8080 >/dev/null; AUTH=1
unset PW
READY=0
for _ in $(seq 1 90); do
  PID=$(docker inspect "$KC" -f '{{.State.Pid}}')
  if [ "$PID" -gt 1 ] && nsenter -t "$PID" -n -- curl --noproxy '*' -fsS --max-time 4 http://127.0.0.1:8080/realms/prp-mcp/.well-known/openid-configuration -o "$TEMP/metadata.json" 2>/dev/null; then READY=1; break; fi
  test "$(docker inspect "$KC" -f '{{.State.Status}}')" = running
  sleep 2
done
test "$READY" = 1
PID=$(docker inspect "$KC" -f '{{.State.Pid}}')
nsenter -t "$PID" -n -- curl --noproxy '*' -fsS --max-time 10 http://127.0.0.1:8080/realms/prp-mcp/protocol/openid-connect/certs -o "$TEMP/clone-jwks.json"
curl --noproxy '*' -fsS --max-time 10 https://auth-test.micor.top/realms/prp-mcp/protocol/openid-connect/certs -o "$TEMP/live-jwks.json"
python3 - "$TEMP" <<'PY'
import json,sys,pathlib
p=pathlib.Path(sys.argv[1])
meta=json.loads((p/'metadata.json').read_text())
assert meta.get('issuer')=='http://127.0.0.1:8080/realms/prp-mcp'
def signing(name):
    d=json.loads((p/name).read_text())
    return {(k.get('kid'),k.get('alg'),k.get('n'),k.get('e')) for k in d.get('keys',[]) if k.get('kty')=='RSA' and k.get('use','sig')=='sig'}
assert signing('live-jwks.json') and signing('live-jwks.json')==signing('clone-jwks.json')
print('RESTORED_OIDC_HTTP=200')
print('RESTORED_SIGNING_PUBLIC_JWKS_MATCH_LIVE=YES')
PY
test "$(systemctl is-active matrix-prp.service)" = active
test "$(docker inspect "$LIVE_KC" -f '{{.State.Status}}')" = running
echo 'ACTIVE_REALM_CHANGED=NO'
echo 'CLONE_RESTORE_AND_SIGNING_JWKS=PASS'
echo 'CLONE_AUDIENCE_MAPPER_REPAIR=NOT_EXECUTED'
echo 'B2_RECOVERY_GATE=NOT_COMPLETED'
