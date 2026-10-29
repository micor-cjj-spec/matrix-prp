#!/usr/bin/env bash
# Disposable GitHub Actions ONLY. Build and inspect the actual PR #113 OCI
# gateway/backend images; never push, deploy, or touch a persistent PRP stack.
set -Eeuo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" || -z "${RUNNER_TEMP:-}" ]]; then
  echo "DISPOSABLE_GITHUB_RUNNER_REQUIRED" >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"
umask 077
revision="$(git rev-parse HEAD)"
tag="${revision:0:12}"
web_img="prp-mcp-review-web-ci-only:${tag}"
api_img="prp-mcp-review-api-ci-only:${tag}"
prefix="prp-review-ci-${GITHUB_RUN_ID:-local}"
stub="${prefix}-backend-stub"
web="${prefix}-web"
api="${prefix}-api-unstarted"
net="${prefix}-net"
tmp="$(mktemp -d "${RUNNER_TEMP}/prp-image-review.XXXXXX")"
cleanup() {
  docker rm -f "$web" "$stub" "$api" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

# Build with no credentials or .env; the existing .dockerignore prevents
# private files and historical build outputs from entering Docker context.
docker build --pull=false \
  -f app/deploy/mcp-staging/Dockerfile.web \
  --build-arg VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT=https://auth-test.micor.top/realms/prp-mcp/protocol/openid-connect/auth \
  --label "org.opencontainers.image.revision=$revision" \
  --label "prp.release-authorized=false" \
  --tag "$web_img" .
docker build --pull=false \
  -f app/deploy/mcp-staging/Dockerfile.backend \
  --label "org.opencontainers.image.revision=$revision" \
  --label "prp.release-authorized=false" \
  --tag "$api_img" .

for image in "$web_img" "$api_img"; do
  test "$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")" = "$revision"
  test "$(docker image inspect -f '{{ index .Config.Labels "prp.release-authorized" }}' "$image")" = false
done

# Never start the new Java app or connect it to any existing MySQL. Merely
# create an UNSTARTED container so the final runtime JAR can be inspected
# exactly as packaged in the published-image candidate.
docker create --name "$api" --network none "$api_img" >/dev/null
docker cp "$api:/opt/prp/app.jar" "$tmp/runtime-app.jar"
python3 - "$tmp/runtime-app.jar" <<'PY'
from pathlib import Path
from zipfile import ZipFile
import sys
jar = Path(sys.argv[1])
if not jar.is_file() or jar.stat().st_size <= 0:
    raise SystemExit("REVIEW_BACKEND_IMAGE_JAR_MISSING")
with ZipFile(jar) as archive:
    entries = set(archive.namelist())
    config = archive.read("BOOT-INF/classes/application.yml")
required = {
    "BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkController.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkService.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpIdentityLinkService.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpClientGrantService.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpVerifiedJwtCaptureFilter.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpOAuthResourceServerConfig.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpOAuthMetadataController.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpActivationGuard.class",
    "BOOT-INF/classes/com/matrix/prp/mcp/PrpMcpTools.class",
    "BOOT-INF/classes/db/migration/V28__mcp_first_party_oidc_link_flows.sql",
    "BOOT-INF/classes/application.yml",
}
if required - entries:
    raise SystemExit("REVIEW_BACKEND_IMAGE_OIDC_ENTRIES_MISSING")
# These defaults are mandatory for the built artifact; a Java class
# existing inside an image does not imply the feature was enabled.
for expected in (
    b"enabled: ${MATRIX_PRP_MCP_ENABLED:false}",
    b"enabled: ${MATRIX_PRP_MCP_OAUTH_ENABLED:false}",
    b"write-enabled: ${MATRIX_PRP_MCP_WRITE_ENABLED:false}",
    b"enabled: ${MATRIX_PRP_FLYWAY_ENABLED:false}",
    b"advertised-scopes: ${MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES:prp.tasks.read}",
):
    if expected not in config:
        raise SystemExit("REVIEW_BACKEND_IMAGE_UNSAFE_DEFAULT_OR_MISSING_SCOPE")
print("PASS OCI BACKEND: full OAuth identity/permissions/task tool classes, V28 and fail-closed defaults")
PY
# Check the assembled JAR INSIDE THE FINAL UNSTARTED OCI IMAGE, not
# Maven's build directory: all 28 original/additive SQL resources must
# be byte-for-byte identical to the reviewed Git source. Exit 4 means
# source/JAR parity only; this is still NOT release permission.
set +e
python3 app/deploy/mcp-staging/verify_oci_migration_jar.py \
  --jar "$tmp/runtime-app.jar" \
  --source app/backend/src/main/resources/db/migration \
  > "$tmp/migration-jar-verdict.json"
migration_status=$?
set -e
test "$migration_status" -eq 4 || {
  echo "OCI_MIGRATION_JAR_SOURCE_PARITY_BLOCKED" >&2
  exit 1
}
python3 - "$tmp/migration-jar-verdict.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    result = json.load(stream)
assert result["decision"] == "CANDIDATE_JAR_SOURCE_MIGRATIONS_IDENTICAL_REVIEW_ONLY"
assert result["source_migrations"] == result["jar_migrations"] == 28
assert result["identical_raw_bytes"] is True and result["deployment_permitted"] is False
PY
echo "PASS OCI BACKEND: final image JAR V1-V28 migration bytes equal source, REVIEW_ONLY"
test "$(docker image inspect -f '{{.Config.User}}' "$api_img")" = prp
echo 'PASS OCI BACKEND: non-root runtime user; Java service never started'

# An isolated, dummy upstream is needed because the final gateway Nginx
# resolves "backend" at startup. This stub has NO PRP DB, keys, or OAuth.
docker network create "$net" >/dev/null
docker run --rm -d --name "$stub" --network "$net" \
  --network-alias backend nginx:1.29-alpine >/dev/null
docker run --rm -d --name "$web" --network "$net" \
  -e PRP_STAGE_HOST=prp-test.micor.top \
  -p 127.0.0.1::8080 "$web_img" >/dev/null
endpoint="$(docker port "$web" 8080/tcp)"
case "$endpoint" in 127.0.0.1:*) ;; *) echo "NON_LOOPBACK_REVIEW_PORT" >&2; exit 1;; esac

# Verify the real FINAL Nginx container serves HTML; this is not proof
# of SPA client-side routes, which the built-JS checks prove separately.
# A freshly launched Docker Nginx may reset an initial connection during
# configuration/DNS initialization. Poll a BOUNDED time, without retrying a
# permanently incorrect HTTP status as a success. Do not disable Host checks.
for path in /prp/login /prp/me/mcp-clients /prp/me/mcp-link/callback; do
  ready=0
  for attempt in $(seq 1 30); do
    code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
      --connect-timeout 2 --max-time 4 \
      -H 'Host: prp-test.micor.top' "http://$endpoint$path" 2>/dev/null)" || code="000"
    if [[ "$code" == 200 ]]; then
      ready=1
      break
    fi
    # Retry only startup/no-response, not a stable 4xx/5xx: the latter
    # indicates an actual wrong final image, route or backend.
    if [[ "$code" != 000 ]]; then
      echo "REVIEW_WEB_PATH_WRONG_HTTP_STATUS=$code" >&2
      exit 1
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$web")" != true ]]; then
      echo "REVIEW_WEB_GATEWAY_EXITED" >&2
      exit 1
    fi
    sleep 1
  done
  if [[ "$ready" != 1 ]]; then
    echo "REVIEW_WEB_STARTUP_TIMEOUT_WITHOUT_200" >&2
    exit 1
  fi
done
wrong="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  -H 'Host: unrelated.invalid' "http://$endpoint/prp/login")"
if [[ "$wrong" != 421 ]]; then
  echo "REVIEW_WEB_WRONG_HOST_NOT_DENIED" >&2
  exit 1
fi
nested="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  -H 'Host: prp-test.micor.top' "http://$endpoint/prp/api/mcp")"
if [[ "$nested" != 404 ]]; then
  echo "REVIEW_WEB_NESTED_API_NOT_DENIED" >&2
  exit 1
fi

# Read the final Nginx image's copied asset directory, not the source
# checkout or the Maven/Vite intermediate build directory.
docker cp "$web:/usr/share/nginx/html/assets" "$tmp/assets"
python3 - "$tmp/assets" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
js_files = list(root.rglob("*.js"))
if not js_files:
    raise SystemExit("REVIEW_WEB_ASSET_JS_MISSING")
markers = (
    b"/me/mcp-link/callback",
    b"/mcp/identity/oidc/start",
    b"/mcp/identity/oidc/finish",
)
seen = set()
for file in js_files:
    contents = file.read_bytes()
    seen.update(marker for marker in markers if marker in contents)
if seen != set(markers):
    raise SystemExit("REVIEW_WEB_FINAL_IMAGE_OIDC_JS_MISSING")
print("PASS OCI WEB: FINAL nginx image has all three OIDC callback/API markers")
PY
echo 'PASS OCI WEB: running CI-only gateway, exact Host, /prp/ routes and nested API denial'
echo "CI_ONLY_IMAGE_REVISION=$revision"
echo "CI_ONLY_BACKEND_IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$api_img")"
echo "CI_ONLY_FRONTEND_IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$web_img")"
echo 'NO_IMAGE_PUSH_NO_EXISTING_STACK_CHANGE_NO_LIVE_CLIENT_REGISTRATION=YES'
