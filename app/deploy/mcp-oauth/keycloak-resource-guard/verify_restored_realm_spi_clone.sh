#!/usr/bin/env bash
# 13-client restored Realm SPI compatibility. Clone ONLY; never live Realm PUT.
set -Eeuo pipefail
umask 077
# Original historical backup remains the default, for repeatability.
# The opt-in, exact current-snapshot mode is immutable: no arbitrary path,
# hash, database, or container argument can be supplied from the CLI.
if [[ $# -eq 0 ]]; then
  DUMP=/root/prp-mcp-backups/snapshot-4G42atvf/keycloak-stage.dump
  EXPECTED=0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17
  CLONE_SNAPSHOT_KIND=HISTORICAL_PINNED
elif [[ $# -eq 1 && "$1" == --current-snapshot ]]; then
  DUMP=/root/prp-mcp-backups/keycloak-current-review-ET1EMnba/keycloak-current.dump
  EXPECTED=52b67c64a8e37679cd5b3999057cd035b2c198ce6e57cf4a7dcbcc494a45e8bd
  CLONE_SNAPSHOT_KIND=CURRENT_PINNED_AT_2026_10_28
else
  echo 'EXACT_SNAPSHOT_MODE_REQUIRED'
  exit 2
fi
# Treat the snapshot as sensitive, root-owned material; do not allow a
# symlink to redirect the restoration to an unrelated object.
if [[ -L "$DUMP" || ! -f "$DUMP" ]]; then
  echo 'PINNED_SNAPSHOT_UNSAFE_OR_MISSING'
  exit 2
fi
echo "CLONE_SNAPSHOT_KIND=$CLONE_SNAPSHOT_KIND"
LIVE_DB=prp-mcp-oauth-stage-auth-db-1
LIVE_KC=prp-mcp-oauth-stage-keycloak-1
TAG="prp-kc-ns-$(date -u +%Y%m%d%H%M%S)-$$"
NET="$TAG-net"; VOL="$TAG-vol"; PG="$TAG-pg"; KC="$TAG-kc"
TEMP=$(mktemp -d /tmp/prp-kc-ns-XXXXXXXX)
NETWORK=0; VOLUME=0; DB=0; AUTH=0
cleanup() {
  rc=$?
  trap - EXIT
  cleanup_rc=0
  if [ "$AUTH" = 1 ]; then docker rm -f "$KC" >/dev/null 2>&1 || cleanup_rc=1; fi
  if [ "$DB" = 1 ]; then docker rm -f "$PG" >/dev/null 2>&1 || cleanup_rc=1; fi
  if [ "$NETWORK" = 1 ]; then docker network rm "$NET" >/dev/null 2>&1 || cleanup_rc=1; fi
  if [ "$VOLUME" = 1 ]; then docker volume rm "$VOL" >/dev/null 2>&1 || cleanup_rc=1; fi
  rm -rf "$TEMP" || cleanup_rc=1
  echo "CLONE_CLEANUP_RESOURCE_STATUS=$cleanup_rc"
  if [ "$cleanup_rc" -ne 0 ]; then rc=1; fi
  # This status reports the overall rehearsal, NOT the resource cleanup.
  # Never print container logs, credentials or private auth data.
  echo "CLONE_SCRIPT_EXIT_STATUS=$rc"
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
# Maven inherits the root-only umask 077 in this operator's shell. CI's
# default umask differs; the clone's Keycloak UID is non-root and must be
# able to read its own mounted provider. Only the bytecode JAR becomes
# world-readable. Root's mktemp workspace stays mode 0700 and the container
# mount remains :ro. No credential, DB dump, or token permissions change.
chmod 0444 "$JAR"
test "$(stat -c '%a' "$JAR")" = 444
echo 'CLONE_PROVIDER_JAR_MOUNT_READABLE=PASS'
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
  if [[ "$(docker inspect "$KC" -f '{{.State.Status}}')" != running ]]; then
    break
  fi
  sleep 2
done
if [[ "$READY" != 1 ]]; then
  # Raw Keycloak logs may include OAuth and config data. Keep them root-only
  # inside the auto-removed temp dir, never print any log line or environment.
  docker logs "$KC" > "$TEMP/clone-keycloak-private.log" 2>&1 || true
  echo 'CLONE_KEYCLOAK_READY=NO'
  echo "CLONE_KEYCLOAK_CONTAINER_STATUS=$(docker inspect "$KC" -f '{{.State.Status}}')"
  echo "CLONE_KEYCLOAK_EXIT_CODE=$(docker inspect "$KC" -f '{{.State.ExitCode}}')"
  echo "CLONE_KEYCLOAK_OOM_KILLED=$(docker inspect "$KC" -f '{{.State.OOMKilled}}')"
  if grep -Eqi 'permission denied|accessdeniedexception|read-only file system|unable to read.*provider' "$TEMP/clone-keycloak-private.log"; then
    echo 'CLONE_BOOT_DIAGNOSTIC=FILE_OR_PROVIDER_PERMISSION'
  elif grep -Eqi 'failed to start.*quarkus|failed to augment|provider.*(exception|error)|classnotfoundexception|noclassdeffounderror' "$TEMP/clone-keycloak-private.log"; then
    echo 'CLONE_BOOT_DIAGNOSTIC=PROVIDER_OR_QUARKUS_BUILD'
  elif grep -Eqi 'unable to acquire jdbc|connection refused|connection.*timed out|liquibase|relation.*does not exist' "$TEMP/clone-keycloak-private.log"; then
    echo 'CLONE_BOOT_DIAGNOSTIC=DATABASE_OR_MIGRATION'
  elif grep -Eqi 'outofmemoryerror|oom-kill|killed process' "$TEMP/clone-keycloak-private.log"; then
    echo 'CLONE_BOOT_DIAGNOSTIC=MEMORY'
  elif grep -Eqi 'ERROR|Exception|Caused by:' "$TEMP/clone-keycloak-private.log"; then
    echo 'CLONE_BOOT_DIAGNOSTIC=OTHER_KEYCLOAK_ERROR_REDACTED'
  else
    echo 'CLONE_BOOT_DIAGNOSTIC=NO_CLASSIFIABLE_ERROR'
  fi
  echo 'CLONE_BOOT_RAW_LOGS=NOT_EXPORTED'
  exit 1
fi
echo 'CLONE_KEYCLOAK_READY=YES'
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
# Import only the pinned stdlib RS256/JWKS verifier, never a dependency
# from the active system or an unreviewed current branch.
TOKEN_VERIFIER="$TEMP/oauth_token_check.py"
git -C "$SOURCE_REPO" show "$SOURCE_PIN:app/deploy/mcp-oauth/oauth_token_check.py" > "$TOKEN_VERIFIER"
chmod 0400 "$TOKEN_VERIFIER"
# A separate immutable source commit supplies the exact two create-only
# client proposals for this PRIVATE restored Realm rehearsal. No active
# Keycloak realm or host configuration may be modified by this check.
EXACT_CLIENT_REVIEW_PIN=602e2e6a91a2b072fc9f025272081c2f5c04376c
EXACT_CLIENT_REVIEW_PATH=app/deploy/mcp-oauth/review_exact_client_registrations.py
git -C "$SOURCE_REPO" cat-file -e "$EXACT_CLIENT_REVIEW_PIN:$EXACT_CLIENT_REVIEW_PATH"
git -C "$SOURCE_REPO" show "$EXACT_CLIENT_REVIEW_PIN:$EXACT_CLIENT_REVIEW_PATH" > "$TEMP/review_exact_client_registrations.py"
chmod 0400 "$TEMP/review_exact_client_registrations.py"
# nsenter changes only network namespace. Python runs on the host FS, but HTTP
# is restricted to the disposable Keycloak's own 127.0.0.1:8080.
nsenter -t "$PID" -n -- python3 - "$REVIEW" "$LIVE_KC" "$TOKEN_VERIFIER" <<'PY'
import copy
import json
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

review, live_kc, verifier_file = sys.argv[1:]
sys.path.insert(0, str(Path(verifier_file).parent))
from oauth_token_check import check_token, _b64url
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

    # The ORIGINAL 13-client snapshot is exercised here, unlike the separate
    # CI job's 13 disabled synthetic fixtures. The restored copy alone is
    # writable: api() targets its private 127.0.0.1:8080 network namespace.
    # A passed rehearsal is NEVER a fresh independent B2 restore receipt.
    import importlib.util
    from urllib.parse import quote
    review_module_file = Path(verifier_file).with_name("review_exact_client_registrations.py")
    module_spec = importlib.util.spec_from_file_location(
        "restored_clone_exact_client_candidates", review_module_file)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("CLONE_PINNED_EXACT_CLIENT_REVIEW_UNAVAILABLE")
    review_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(review_module)
    exact_clients = review_module.client_proposals()
    assert review_module.validate_proposals(exact_clients)
    assert len(inventory) == 13, "Historical 13-client restoration drift"
    original_details = {
        key: api(root + "/clients/" + quote(key, safe=""), token=token)
        for key, _ in inventory
    }
    before_scopes = api(root + "/client-scopes", token=token)
    assert {"basic", "offline_access", "prp.tasks.read"}.issubset(
        {s.get("name") for s in before_scopes})
    target_ids = {p["clientId"] for p in exact_clients}
    assert target_ids == {
        "https://chatgpt.com/oauth/client.json", "prp-first-party-link"}
    assert not (target_ids & {c.get("clientId") for c in clients_before}), (
        "Restored clone exact-client creation collision")
    attempted_names = []
    try:
        for proposal in exact_clients:
            client_name = proposal["clientId"]
            candidates = api(root + "/clients?clientId=" + quote(client_name, safe=""),
                             token=token)
            assert not any(c.get("clientId") == client_name for c in candidates)
            attempted_names.append(client_name)
            api(root + "/clients", token=token, method="POST", payload=proposal)
        with_added = api(root + "/clients?max=100", token=token)
        assert len(with_added) == len(clients_before) + 2
        new_map = {c.get("clientId"): c for c in with_added}
        assert len(new_map) == len(with_added)
        assert {(c.get("id"), c.get("clientId")) for c in with_added} == (
            inventory | {(new_map[name]["id"], name) for name in target_ids})
        for item in exact_clients:
            name = item["clientId"]
            key = new_map[name]["id"]
            doc = api(root + "/clients/" + quote(key, safe=""), token=token)
            assert doc.get("clientId") == name
            for prop in ("publicClient", "standardFlowEnabled",
                         "implicitFlowEnabled", "directAccessGrantsEnabled",
                         "serviceAccountsEnabled", "fullScopeAllowed",
                         "consentRequired", "redirectUris", "clientAuthenticatorType"):
                if prop in item:
                    assert doc.get(prop) == item[prop], "Clone client shape drift"
            assert doc.get("attributes", {}).get(
                "pkce.code.challenge.method") == "S256"
            for attribute in ("use.jwks.url", "jwks.url"):
                if attribute in item.get("attributes", {}):
                    assert doc.get("attributes", {}).get(attribute) == (
                        item["attributes"][attribute])
            path = root + "/clients/" + quote(key, safe="")
            scopes = api(path + "/optional-client-scopes", token=token)
            defaults = api(path + "/default-client-scopes", token=token)
            assert {s.get("name") for s in scopes} == set(item["optionalClientScopes"])
            assert "basic" in {s.get("name") for s in defaults}
            if name == "https://chatgpt.com/oauth/client.json":
                mappers = api(path + "/protocol-mappers/models", token=token)
                found = [m for m in mappers if
                         m.get("protocolMapper") == "oidc-audience-mapper" and
                         m.get("config", {}).get("included.custom.audience") == resource and
                         m.get("config", {}).get("access.token.claim") == "true"]
                assert len(found) == 1, "Clone exact resource mapper missing"
        assert all(api(root + "/clients/" + quote(key, safe=""), token=token) == doc
                   for key, doc in original_details.items())
        assert api(root + "/client-scopes", token=token) == before_scopes
        assert api(root + "/client-policies/profiles", token=token) == profiles
        assert api(root + "/client-policies/policies", token=token) == policies
        print("RESTORED_13_CLIENT_EXACT_TWO_CREATES=PASS_PRIVATE_CLONE_ONLY")
    finally:
        # Attempt list is recorded BEFORE every POST. If a POST commits but
        # its response is lost, the exact name is still recovered for cleanup.
        # Never delete a preexisting client, and never target the live Realm.
        for name in reversed(attempted_names):
            found = api(root + "/clients?clientId=" + quote(name, safe=""),
                        token=token)
            matches = [c for c in found if c.get("clientId") == name]
            assert len(matches) <= 1, "Clone exact-client identity collision"
            if matches:
                key = matches[0].get("id")
                assert isinstance(key, str) and key
                api(root + "/clients/" + quote(key, safe=""), token=token,
                    method="DELETE")
        after_exact = api(root + "/clients?max=100", token=token)
        assert {(c.get("id"), c.get("clientId")) for c in after_exact} == inventory
        assert all(api(root + "/clients/" + quote(key, safe=""), token=token) == doc
                   for key, doc in original_details.items())
        assert api(root + "/client-scopes", token=token) == before_scopes
        assert api(root + "/client-policies/profiles", token=token) == profiles
        assert api(root + "/client-policies/policies", token=token) == policies
        print("RESTORED_13_CLIENT_EXACT_TWO_ROLLBACK=PASS_PRIVATE_CLONE_ONLY")
    print("RESTORED_EXACT_CLIENT_B2_RECEIPT=NOT_ISSUED")

    print("=== RESTORED CLONE-ONLY CLIENT POLICY SPI COMPATIBILITY ===")
    # The 13 existing clients remain unchanged. Add one synthetic, disabled-
    # for-login CI client only in the restored PRIVATE Realm; remove it after.
    probe = "ci-prp-restored-refresh-guard"
    existing_ids = {x.get("clientId") for x in clients_before}
    assert probe not in existing_ids, "Synthetic ID collision"
    created_probe = None
    created_user = None
    old_realm = None
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
            "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": False,
            "fullScopeAllowed": False,
            "redirectUris": [],
            "webOrigins": [],
            "defaultClientScopes": ["basic"],
            "optionalClientScopes": ["prp.tasks.read"],
            "attributes": {"prp.ci.refresh-resource-guard": "enabled"},
            "protocolMappers": [{
                "name": "CI restored-only exact MCP audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {"included.custom.audience": resource,
                           "id.token.claim": "false", "access.token.claim": "true"},
            }],
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

        print("=== CLONE-ONLY ACTUAL REFRESH GRANT NEGATIVE/POSITIVE TEST ===")
        # Restore clone's original refresh behavior at the end; never
        # enable direct access grants or rotate sessions on the live Realm.
        old_realm = api(root, token=token)
        for key in ("revokeRefreshToken", "refreshTokenMaxReuse"):
            assert key in old_realm, "Refresh rotation field absent in restored Realm"
        rotated_realm = copy.deepcopy(old_realm)
        rotated_realm["revokeRefreshToken"] = True
        rotated_realm["refreshTokenMaxReuse"] = 0
        api(root, token=token, method="PUT", payload=rotated_realm)
        active_realm = api(root, token=token)
        assert active_realm.get("revokeRefreshToken") is True
        assert active_realm.get("refreshTokenMaxReuse") == 0
        print("CLONE_RESTORED_REFRESH_ROTATION_CONFIG=PASS")

        scope_defs = api(root + "/client-scopes", token=token)
        assert "prp.tasks.read" in {x.get("name") for x in scope_defs}
        synthetic_user = "ci-restored-rfr-" + secrets.token_hex(8)
        synthetic_password = secrets.token_urlsafe(36)
        api(root + "/users", token=token, method="POST", payload={
            "username": synthetic_user, "enabled": True,
            "emailVerified": True,
            "email": synthetic_user + "@example.invalid",
            "firstName": "Disposable", "lastName": "Refresh Clone",
            "requiredActions": [],
            "credentials": [{"type": "password", "value": synthetic_password,
                             "temporary": False}],
        })
        users = api(root + "/users?username=" + synthetic_user + "&exact=true", token=token)
        found = [u for u in users if u.get("username") == synthetic_user]
        assert len(found) == 1
        created_user = found[0]["id"]

        # ROPC is used ONLY to obtain a temporary initial grant in the
        # restored, internal-network clone. It is not a recommended PRP
        # user login flow. AuthCode+PKCE/private_key_jwt are tested in CI.
        client_path = root + "/clients/" + created_probe
        reread_client = api(client_path, token=token)
        assert reread_client.get("clientId") == probe
        assert reread_client.get("directAccessGrantsEnabled") is True
        assert reread_client.get("fullScopeAllowed") is False
        assert reread_client.get("attributes", {}).get("prp.ci.refresh-resource-guard") == "enabled"
        restored_mappers = api(client_path + "/protocol-mappers/models", token=token)
        exact_mappers = [m for m in restored_mappers
                         if m.get("name") == "CI restored-only exact MCP audience"]
        assert len(exact_mappers) == 1
        assert exact_mappers[0].get("config", {}).get("included.custom.audience") == resource
        print("CLONE_RESTORED_SYNTHETIC_AUDIENCE_MAPPER=PASS")

        endpoint = "/realms/prp-mcp/protocol/openid-connect/token"
        jwks = api("/realms/prp-mcp/protocol/openid-connect/certs")
        issuer = base + "/realms/prp-mcp"

        def request_grant(values):
            form_data = urlencode(values, doseq=True).encode()
            try:
                result = api(endpoint, method="POST", payload=form_data)
                return 200, result
            except HTTPError as err:
                # Only status codes are used for negative tests: no error
                # body, token, claims or secret is ever printed.
                return err.code, None

        def verify_signed_access(values):
            assert isinstance(values, dict)
            bearer = values.get("access_token")
            assert isinstance(bearer, str) and bearer
            check_token(bearer, jwks, issuer=issuer, resource=resource,
                        client_id=probe, required_scope="prp.tasks.read")
            claims = json.loads(_b64url(bearer.split(".")[1]))
            assert "prp.finance.read" not in claims.get("scope", "").split()
            audience = claims.get("aud")
            audiences = [audience] if isinstance(audience, str) else audience
            assert isinstance(audiences, list)
            assert "https://unrelated.example.test/api/mcp" not in audiences
            return claims["sub"]

        initial_status, initial = request_grant({
            "grant_type": "password", "client_id": probe,
            "username": synthetic_user, "password": synthetic_password,
            "scope": "openid prp.tasks.read", "resource": resource,
        })
        if initial_status != 200:
            raise RuntimeError("RESTORED_PASSWORD_TEST_GRANT_HTTP_" + str(initial_status))
        subject = verify_signed_access(initial)
        assert subject == created_user, "Issued access token belongs to another user"
        assert isinstance(initial.get("refresh_token"), str)
        first_refresh = initial["refresh_token"]
        print("CLONE_RESTORED_INITIAL_SIGNED_RESOURCE_JWT=PASS")

        def refreshed(refresh_token, *, resource_value=resource, scope="openid prp.tasks.read"):
            value = {
                "grant_type": "refresh_token", "client_id": probe,
                "refresh_token": refresh_token, "scope": scope,
            }
            if resource_value is not None:
                value["resource"] = resource_value
            return request_grant(value)

        # First validate the legitimate refresh lifecycle on its own token.
        # Negative grant attempts may revoke their submitted token depending
        # on Keycloak's grant processing order; do not share that token.
        good_status, renewed = refreshed(first_refresh)
        if good_status != 200:
            raise RuntimeError("RESTORED_CORRECT_REFRESH_HTTP_" + str(good_status))
        assert verify_signed_access(renewed) == subject
        second_refresh = renewed.get("refresh_token")
        assert isinstance(second_refresh, str) and second_refresh != first_refresh
        replay_status, _ = refreshed(first_refresh)
        if replay_status not in (400, 401):
            raise RuntimeError("RESTORED_ROTATED_REFRESH_REPLAY_ACCEPTED")
        print("CLONE_RESTORED_REFRESH_SIGNATURE_AND_ROTATION=PASS")

        revoke_path = "/realms/prp-mcp/protocol/openid-connect/revoke"
        api(revoke_path, method="POST", payload=urlencode({
            "client_id": probe, "token": second_refresh,
            "token_type_hint": "refresh_token",
        }).encode())
        revoked_status, _ = refreshed(second_refresh)
        if revoked_status not in (400, 401):
            raise RuntimeError("RESTORED_REVOKED_REFRESH_ACCEPTED")
        print("CLONE_RESTORED_REFRESH_REVOCATION=PASS")

        def fresh_synthetic_refresh_token():
            status, issued = request_grant({
                "grant_type": "password", "client_id": probe,
                "username": synthetic_user, "password": synthetic_password,
                "scope": "openid prp.tasks.read", "resource": resource,
            })
            if status != 200:
                raise RuntimeError("RESTORED_NEGATIVE_FIXTURE_GRANT_HTTP_" + str(status))
            assert verify_signed_access(issued) == subject
            fresh = issued.get("refresh_token")
            assert isinstance(fresh, str) and fresh
            return fresh

        for category, request_resource, request_scope in (
            ("WRONG_RESOURCE", "https://unrelated.example.test/api/mcp", "openid prp.tasks.read"),
            ("DUPLICATE_RESOURCE", [resource, resource], "openid prp.tasks.read"),
            ("BLANK_RESOURCE", "", "openid prp.tasks.read"),
            ("FINANCE_SCOPE", resource, "openid prp.finance.read"),
        ):
            fresh_token = fresh_synthetic_refresh_token()
            denied, _ = refreshed(
                fresh_token, resource_value=request_resource, scope=request_scope)
            if denied not in (400, 401):
                raise RuntimeError("RESTORED_" + category + "_REFRESH_ACCEPTED")
        print("CLONE_RESTORED_REFRESH_UNAUTHORIZED_RESOURCE_AND_SCOPE_DENIAL=PASS")

        # Keycloak may infer the original grant's canonical resource when
        # the optional RFC 8707 resource is omitted by a public client.
        # This is *not* proof of explicit missing-resource rejection.
        omitted_token = fresh_synthetic_refresh_token()
        omitted_status, omitted = refreshed(omitted_token, resource_value=None)
        if omitted_status == 200:
            assert verify_signed_access(omitted) == subject
            rotated = omitted.get("refresh_token")
            assert isinstance(rotated, str) and rotated != omitted_token
            old_status, _ = refreshed(omitted_token)
            assert old_status in (400, 401)
            api(revoke_path, method="POST", payload=urlencode({
                "client_id": probe, "token": rotated,
                "token_type_hint": "refresh_token",
            }).encode())
            final_status, _ = refreshed(rotated)
            if final_status not in (400, 401):
                raise RuntimeError("RESTORED_OMITTED_RESOURCE_REVOKE_BYPASS")
            print("CLONE_RESTORED_OMITTED_RESOURCE=SIGNED_CANONICAL_AUDIENCE_ONLY")
        elif omitted_status in (400, 401):
            print("CLONE_RESTORED_OMITTED_RESOURCE=REJECTED")
        else:
            raise RuntimeError("RESTORED_OMITTED_RESOURCE_HTTP_" + str(omitted_status))
        print("CLONE_RESTORED_SPI_REFRESH_GRANT=PASS_SYNTHETIC_PASSWORD_GRANT")
    finally:
        # This is only the private restored clone. Undo the user's
        # synthetic credential and the clone-only refresh rotation change
        # before removing the policy, profile and temporary client.
        if created_user is not None:
            api(root + "/users/" + created_user, token=token, method="DELETE")
            remaining_users = api(root + "/users?username=" + synthetic_user + "&exact=true", token=token)
            assert not any(u.get("username") == synthetic_user for u in remaining_users)
            print("CLONE_RESTORED_SYNTHETIC_USER_REMOVED=YES")
        if old_realm is not None:
            api(root, token=token, method="PUT", payload=old_realm)
            current = api(root, token=token)
            for name in ("revokeRefreshToken", "refreshTokenMaxReuse"):
                assert current.get(name) == old_realm.get(name)
            print("CLONE_RESTORED_REFRESH_REALM_SETTINGS_ROLLBACK=PASS")
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
        ValueError, KeyError, TypeError, IndexError) as exc:
    # A fixed diagnostic category is safe; arbitrary exception strings and
    # HTTP bodies can include authorization or realm configuration details.
    safe_messages = {
        "RESTORED_WRONG_RESOURCE_REFRESH_ACCEPTED",
        "RESTORED_DUPLICATE_RESOURCE_REFRESH_ACCEPTED",
        "RESTORED_MISSING_RESOURCE_REFRESH_ACCEPTED",
        "RESTORED_FINANCE_SCOPE_ESCALATION_ACCEPTED",
        "RESTORED_ROTATED_REFRESH_REPLAY_ACCEPTED",
        "RESTORED_REVOKED_REFRESH_ACCEPTED",
    }
    cause = str(exc) if isinstance(exc, RuntimeError) else ""
    if cause in safe_messages:
        category = cause
    elif cause.startswith("RESTORED_PASSWORD_TEST_GRANT_HTTP_") and cause.rsplit("_", 1)[-1].isdigit():
        category = "SYNTHETIC_PASSWORD_GRANT_HTTP_" + cause.rsplit("_", 1)[-1]
    elif cause.startswith("RESTORED_CORRECT_REFRESH_HTTP_") and cause.rsplit("_", 1)[-1].isdigit():
        category = "CANONICAL_REFRESH_HTTP_" + cause.rsplit("_", 1)[-1]
    elif isinstance(exc, HTTPError):
        category = "CLONE_KEYCLOAK_ADMIN_OR_TOKEN_HTTP_" + str(exc.code)
    else:
        category = "CLONE_ASSERTION_OR_API_FAILURE"
    print("CLONE_REHEARSAL=FAILED")
    print("CLONE_REHEARSAL_DIAGNOSTIC=" + category)
    print("No credentials, OAuth tokens or response bodies printed.")
    sys.exit(1)
PY
test "$(systemctl is-active matrix-prp.service)" = active
test "$(docker inspect "$LIVE_KC" -f '{{.State.Status}}')" = running
echo 'ACTIVE_REALM_CHANGED=NO'
echo 'CLONE_RESTORE_AND_SIGNING_JWKS=PASS'
echo 'CLONE_RESTORED_OAUTH_AUTHCODE_PKCE=CI_DISPOSABLE_ONLY'
echo 'B2_RECOVERY_GATE=NOT_COMPLETED'
