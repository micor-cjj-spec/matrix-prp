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
echo '=== CLONE-ONLY AUDIENCE MAPPER REPAIR AND ROLLBACK ==='
REVIEW=/root/prp-mcp-backups/v2-keycloak-mapper-review-oyp642m6
test "$(sha256sum "$REVIEW/original.json" | awk '{print $1}')" = 80834a6ea75b99a504e06e6a218af7215814475bcbecd00b932973e8e6672ca6
test "$(sha256sum "$REVIEW/candidate.json" | awk '{print $1}')" = a26b7ec0f1739d2d12cd948f6134410b91a2782fdc4ea970036ef1bc1c4eb44b
# nsenter changes only network namespace. Python runs on the host FS, but HTTP
# is restricted to the disposable Keycloak's own 127.0.0.1:8080.
nsenter -t "$PID" -n -- python3 - "$REVIEW" "$LIVE_KC" <<'PY'
import copy
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

review, live_kc = sys.argv[1:]
base = "http://127.0.0.1:8080"
resource = "https://prp-test.micor.top/api/mcp"
opener = build_opener(ProxyHandler({}))

def api(path, *, token=None, method="GET", payload=None):
    if not path.startswith("/") or "//" in path:
        raise ValueError("Untrusted Keycloak path")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if isinstance(payload, dict):
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(payload, bytes):
        body = payload
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        body = None
    request = Request(base + path, data=body, headers=headers, method=method)
    with opener.open(request, timeout=12) as response:
        if response.status not in (200, 204):
            raise RuntimeError("Unexpected clone API status")
        raw = response.read(200001)
        if len(raw) > 200000:
            raise RuntimeError("Oversized clone API response")
        return json.loads(raw) if raw else None

try:
    original = json.loads((Path(review) / "original.json").read_text())
    candidate = json.loads((Path(review) / "candidate.json").read_text())
    expected = copy.deepcopy(original)
    expected["config"].pop("included.client.audience", None)
    expected["config"]["included.custom.audience"] = resource
    assert candidate == expected, "Candidate drift"

    # Only read bootstrap secret from the running staging Keycloak metadata.
    # Never print or persist its value or any OAuth access token.
    live = json.loads(subprocess.check_output(
        ["docker", "inspect", live_kc], text=True
    ))[0]
    env = dict(s.split("=", 1) for s in live["Config"]["Env"] if "=" in s)
    form = urlencode({
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": env["KC_BOOTSTRAP_ADMIN_USERNAME"],
        "password": env["KC_BOOTSTRAP_ADMIN_PASSWORD"],
    }).encode()
    token = api(
        "/realms/master/protocol/openid-connect/token",
        method="POST", payload=form
    )["access_token"]

    root = "/admin/realms/prp-mcp"
    profiles = api(root + "/client-policies/profiles", token=token)
    policies = api(root + "/client-policies/policies", token=token)
    assert profiles.get("profiles") == [], "Clone profile drift"
    assert policies.get("policies") == [], "Clone policy drift"
    clients_before = api(root + "/clients?max=100", token=token)
    inventory = {(c.get("id"), c.get("clientId")) for c in clients_before}
    assert len(inventory) == len(clients_before) >= 10
    exact = [c for c in clients_before if c.get("clientId") == "prp-pkce-probe"]
    assert len(exact) == 1
    cid = exact[0]["id"]
    client = api(root + "/clients/" + cid, token=token)
    assert client.get("publicClient") is True
    assert client.get("standardFlowEnabled") is True
    assert client.get("attributes", {}).get("pkce.code.challenge.method") == "S256"
    assert client.get("redirectUris") == ["http://127.0.0.1:8765/callback"]
    mappers_path = root + "/clients/" + cid + "/protocol-mappers/models"
    mappers = api(mappers_path, token=token)
    matching = [m for m in mappers if m.get("id") == original["id"]]
    assert matching == [original], "Restored mapper differs from pinned backup"
    url = mappers_path + "/" + original["id"]

    def reread():
        return api(url, token=token)

    def put(value):
        api(url, token=token, method="PUT", payload=value)

    print("CLONE_EXISTING_CLIENTS=" + str(len(clients_before)))
    print("CLONE_MAPPER_PRECHANGE=PASS")

    try:
        put(candidate)
        assert reread() == candidate, "Candidate not persisted"
        print("CLONE_AUDIENCE_MAPPER_REPAIR=PASS")
    finally:
        # This is strictly the disposable clone: no live Realm Admin PUT.
        if reread() != original:
            put(original)
        assert reread() == original, "Clone mapper rollback incomplete"
        print("CLONE_AUDIENCE_MAPPER_ROLLBACK=PASS")

    clients_after = api(root + "/clients?max=100", token=token)
    assert {(c.get("id"), c.get("clientId")) for c in clients_after} == inventory
    assert api(root + "/client-policies/profiles", token=token) == profiles
    assert api(root + "/client-policies/policies", token=token) == policies
    print("CLONE_CLIENT_POLICY_INVENTORY_PRESERVED=YES")
except (AssertionError, HTTPError, URLError, RuntimeError, OSError,
        ValueError, KeyError, TypeError, IndexError):
    print("CLONE_MAPPER_REHEARSAL=FAILED")
    print("No credentials, OAuth tokens or response bodies printed.")
    sys.exit(1)
PY
test "$(systemctl is-active matrix-prp.service)" = active
test "$(docker inspect "$LIVE_KC" -f '{{.State.Status}}')" = running
echo 'ACTIVE_REALM_CHANGED=NO'
echo 'CLONE_RESTORE_AND_SIGNING_JWKS=PASS'
echo 'B2_RECOVERY_GATE=NOT_COMPLETED'
