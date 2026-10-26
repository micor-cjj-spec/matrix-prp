#!/usr/bin/env bash
# 13-client restored Realm SPI compatibility. Clone ONLY; never live Realm PUT.
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
command -v mvn >/dev/null
command -v java >/dev/null
command -v python3 >/dev/null
echo '=== IDENTIFY EXISTING JDK 21 COMPILER (NO SYSTEM CHANGES) ==='
PRP_PID=$(systemctl show -p MainPID --value matrix-prp.service)
PRP_EXEC=''
if [[ "$PRP_PID" =~ ^[0-9]+$ ]] && (( PRP_PID > 1 )); then
  PRP_EXEC=$(readlink -f "/proc/$PRP_PID/exe" 2>/dev/null || true)
fi
JDK21_HOME=''
JDK21_SOURCE=''
JDK_CANDIDATES=()
if [[ "$PRP_EXEC" = */bin/java ]]; then JDK_CANDIDATES+=("${PRP_EXEC%/bin/java}"); fi
if [[ -n "${JAVA_HOME:-}" ]]; then JDK_CANDIDATES+=("$JAVA_HOME"); fi
JDK_CANDIDATES+=(
  /usr/lib/jvm/java-21-openjdk-amd64 /usr/lib/jvm/*21*
  /opt/java21 /opt/jdk21 /opt/java-21 /opt/jdk-21 /opt/java-21* /opt/jdk-21*
  /usr/local/lib/jvm/*21* /usr/local/java-21* /usr/local/jdk-21*
  /root/.sdkman/candidates/java/*21*
)
for candidate in "${JDK_CANDIDATES[@]}"; do
  [[ -x "$candidate/bin/javac" && -x "$candidate/bin/java" ]] || continue
  javac_version=$("$candidate/bin/javac" -version 2>&1 || true)
  if [[ "$javac_version" =~ ^javac[[:space:]]21([.]|$) ]]; then
    JDK21_HOME=$(cd "$candidate" && pwd -P)
    JDK21_SOURCE=EXISTING_JDK_INSTALLATION
    if [[ "$PRP_EXEC" = "$JDK21_HOME/bin/java" ]]; then JDK21_SOURCE=RUNNING_PRP_JVM; fi
    break
  fi
done
ARTIFACT=/root/prp-mcp-backups/prp-refresh-resource-guard-26.8.0-CI-ONLY.zip
ARTIFACT_SHA256=38cb779442eafb7034855aa0c806105a096803f0569b7792362c32d282eac844
EXPECTED_JAR_SHA256=ab2481fd8efeb5a763d3552493b3c6b5d8549d548951d7cfe42f290393ff9818
SOURCE_REPO=/root/matrix-prp-mcp-v2-staging
SOURCE_PIN=00c9de9568f8dc93548b7884c8ff3561524ff1a4
PREFIX=app/deploy/mcp-oauth/keycloak-resource-guard
BUILD="$TEMP/build"
JAR="$BUILD/target/prp-refresh-resource-guard.jar"
mkdir -p "$BUILD/target"
test "$(docker exec "$LIVE_KC" /opt/keycloak/bin/kc.sh --version 2>&1 | grep -Eo 'Keycloak [0-9.]+')" = 'Keycloak 26.8.0'
if [[ -n "$JDK21_HOME" ]]; then
  command -v mvn >/dev/null
  echo 'HOST_JDK21_COMPILER=PASS'
  echo "HOST_JDK21_SELECTION=$JDK21_SOURCE"
  git -C "$SOURCE_REPO" cat-file -e "$SOURCE_PIN^{commit}"
  echo '=== BUILD EXACT PINNED 26.8.0 SPI SOURCE; NO LIVE INSTALL ==='
  for PART in \
    pom.xml \
    src/main/java/io/micor/prp/ci/ExactRefreshResourceExecutorFactory.java \
    src/main/resources/META-INF/services/org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory \
    src/test/java/io/micor/prp/ci/ExactRefreshResourceExecutorFactoryTest.java
  do
    mkdir -p "$BUILD/$(dirname "$PART")"
    git -C "$SOURCE_REPO" show "$SOURCE_PIN:$PREFIX/$PART" > "$BUILD/$PART"
  done
  if ! JAVA_HOME="$JDK21_HOME" PATH="$JDK21_HOME/bin:$PATH" \
       MAVEN_OPTS='-Xmx512m -XX:MaxMetaspaceSize=256m' \
       mvn -B -ntp -q -f "$BUILD/pom.xml" -Dkeycloak.version=26.8.0 verify \
         > "$TEMP/maven-build.log" 2>&1; then
    echo 'CANDIDATE_MAVEN_BUILD=FAILED'
    grep -E '^\[ERROR\]|Tests run:' "$TEMP/maven-build.log" | tail -n 15 || true
    exit 1
  fi
  test -s "$JAR"
  python3 - "$BUILD" "$JAR" <<'PY'
import pathlib, sys, xml.etree.ElementTree as et, zipfile
build, archive = map(pathlib.Path, sys.argv[1:])
report=build/'target/surefire-reports/TEST-io.micor.prp.ci.ExactRefreshResourceExecutorFactoryTest.xml'
r=et.parse(report).getroot()
assert int(r.attrib['tests'])>=7
assert int(r.attrib['failures'])==0 and int(r.attrib['errors'])==0
with zipfile.ZipFile(archive) as z:
    service='META-INF/services/org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory'
    assert z.read(service).decode().strip()=='io.micor.prp.ci.ExactRefreshResourceExecutorFactory'
    assert 'io/micor/prp/ci/ExactRefreshResourceExecutorFactory.class' in z.namelist()
print('CANDIDATE_JUNIT_SECURITY_TESTS=PASS')
print('CANDIDATE_SPI_JAR_STRUCTURE=PASS')
PY
  echo 'CANDIDATE_BUILD_METHOD=HOST_JDK21_MAVEN'
else
  echo 'HOST_JDK21_COMPILER=NOT_FOUND'
  if [[ ! -f "$ARTIFACT" ]]; then
    echo 'CI_ONLY_ARTIFACT=NOT_UPLOADED'
    echo 'NO_CLONE_CONTAINERS_STARTED=YES'
    echo 'No Java 21 compiler or verified CI ZIP; no installation or default Java changes made.'
    exit 3
  fi
  test "$(sha256sum "$ARTIFACT" | awk '{print $1}')" = "$ARTIFACT_SHA256" || { echo 'CI_ONLY_ARTIFACT_ZIP_SHA256=MISMATCH'; exit 1; }
  python3 - "$ARTIFACT" "$JAR" "$EXPECTED_JAR_SHA256" <<'PY'
import hashlib, io, pathlib, sys, zipfile
source, target = map(pathlib.Path, sys.argv[1:3])
expected = sys.argv[3]
with zipfile.ZipFile(source) as bundle:
    assert set(bundle.namelist()) == {'prp-refresh-resource-guard.jar', 'SHA256SUMS'}
    jar_bytes = bundle.read('prp-refresh-resource-guard.jar')
    manifest = bundle.read('SHA256SUMS').decode('ascii').strip()
    assert manifest == expected + '  prp-refresh-resource-guard.jar'
assert hashlib.sha256(jar_bytes).hexdigest() == expected
with zipfile.ZipFile(io.BytesIO(jar_bytes)) as candidate:
    svc = 'META-INF/services/org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory'
    assert candidate.read(svc).decode('utf-8').strip() == 'io.micor.prp.ci.ExactRefreshResourceExecutorFactory'
    assert 'io/micor/prp/ci/ExactRefreshResourceExecutorFactory.class' in candidate.namelist()
target.write_bytes(jar_bytes)
print('CI_ONLY_ARTIFACT_ZIP_SHA256=PASS')
print('CANDIDATE_SPI_JAR_STRUCTURE=PASS')
print('CANDIDATE_JUNIT_SECURITY_TESTS=PASS_PREVERIFIED_IN_CI')
PY
  echo 'CANDIDATE_BUILD_METHOD=PINNED_VERIFIED_26_8_0_CI_JAR'
fi
test -s "$JAR"
echo "CANDIDATE_JAR_SHA256=$(sha256sum "$JAR" | awk '{print $1}')"
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
docker run --pull never -d --name "$KC" --network "$NET" --memory 1100m --memory-swap 1200m --pids-limit 256 --security-opt no-new-privileges:true -e KC_DB=postgres -e KC_DB_URL=jdbc:postgresql://pg-restore:5432/keycloak_stage -e KC_DB_USERNAME=keycloak_stage -e KC_DB_PASSWORD="$PW" -e KC_HTTP_ENABLED=true -e KC_CACHE=local -e JAVA_OPTS_KC_HEAP='-Xms128m -Xmx512m' -v "$JAR:/opt/keycloak/providers/prp-refresh-resource-guard.jar:ro" "$KC_IMAGE" start-dev --features=cimd,resource-indicators --hostname=http://127.0.0.1:8080 >/dev/null; AUTH=1
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
        if response.status not in (200, 201, 204):
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

    print("=== RESTORED CLONE-ONLY CLIENT POLICY SPI COMPATIBILITY ===")
    # The 13 existing clients remain unchanged. Add one synthetic, disabled-
    # for-login CI client only in the restored PRIVATE Realm; remove it after.
    probe = "ci-prp-restored-refresh-guard"
    existing_ids = {x.get("clientId") for x in clients_before}
    assert probe not in existing_ids, "Synthetic ID collision"
    created_probe = None
    profile_name = "ci-restored-refresh-resource"
    policy_name = "ci-restored-refresh-only"
    wanted_config = {
        "target-client-id": probe,
        "allowed-resource": resource,
    }
    rule = {
        "name": profile_name,
        "executors": [{"executor": "prp-ci-refresh-resource-guard",
                       "configuration": wanted_config}],
    }
    condition = {
        "condition": "client-attributes",
        "configuration": {"attributes": json.dumps(
            [{"key": "prp.ci.refresh-resource-guard", "value": "enabled"}],
            separators=(",", ":"))},
    }
    policy = {
        "name": policy_name,
        "enabled": True,
        "conditions": [condition],
        "profiles": [profile_name],
    }
    try:
        api(root + "/clients", token=token, method="POST", payload={
            "clientId": probe,
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": True,
            "standardFlowEnabled": False,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
            "redirectUris": [],
            "webOrigins": [],
            "attributes": {"prp.ci.refresh-resource-guard": "enabled"},
        })
        candidates=api(root + "/clients?clientId=" + probe, token=token)
        exact_probe=[x for x in candidates if x.get("clientId")==probe]
        assert len(exact_probe)==1
        created_probe=exact_probe[0]["id"]
        api(root + "/client-policies/profiles", token=token,
            method="PUT", payload={"profiles": profiles["profiles"] + [rule]})
        api(root + "/client-policies/policies", token=token,
            method="PUT", payload={"policies": policies["policies"] + [policy]})
        active_profiles=api(root + "/client-policies/profiles", token=token)
        active_policies=api(root + "/client-policies/policies", token=token)
        matching=[x for x in active_profiles.get("profiles", [])
                  if x.get("name")==profile_name]
        bound=[x for x in active_policies.get("policies", [])
               if x.get("name")==policy_name and x.get("enabled") is True]
        assert len(matching)==1 and len(bound)==1
        executors=[x for x in matching[0].get("executors", [])
                   if x.get("executor")=="prp-ci-refresh-resource-guard"]
        assert len(executors)==1 and executors[0].get("configuration")==wanted_config
        assert bound[0].get("conditions")==[condition]
        inventory_now=api(root + "/clients?max=100", token=token)
        assert {(x.get("id"),x.get("clientId")) for x in inventory_now}==inventory | {(created_probe,probe)}
        print("CLONE_RESTORED_SPI_PROVIDER_LOADED=YES")
        print("CLONE_RESTORED_CLIENT_POLICY_CONFIG=PASS")
        print("CLONE_ORIGINAL_13_CLIENTS_UNMODIFIED=YES")
    finally:
        # Delete the temporary policy before its referenced profile, then
        # the isolated probe. Never send these PUTs to the live Realm.
        api(root + "/client-policies/policies", token=token,
            method="PUT", payload=policies)
        api(root + "/client-policies/profiles", token=token,
            method="PUT", payload=profiles)
        if created_probe is not None:
            api(root + "/clients/" + created_probe, token=token,
                method="DELETE")
        assert api(root + "/client-policies/profiles", token=token)==profiles
        assert api(root + "/client-policies/policies", token=token)==policies
        after=api(root + "/clients?max=100", token=token)
        assert {(x.get("id"),x.get("clientId")) for x in after}==inventory
        print("CLONE_RESTORED_POLICY_ROLLBACK=PASS")
        print("CLONE_RESTORED_13_CLIENT_INVENTORY_PRESERVED=YES")
    print("CLONE_RESTORED_SPI_STATIC_COMPATIBILITY=PASS")

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
echo 'CLONE_RESTORED_SPI_REFRESH_GRANT=NOT_EXECUTED'
echo 'B2_RECOVERY_GATE=NOT_COMPLETED'
