#!/usr/bin/env bash
# Disposable GitHub-hosted PR runner ONLY. No external host, SSH or production access.
set -Eeuo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" ||
      "${RUNNER_ENVIRONMENT:-}" != "github-hosted" ||
      "${GITHUB_REPOSITORY:-}" != "micor-cjj-spec/matrix-prp" ||
      "${GITHUB_EVENT_NAME:-}" != "pull_request" ||
      "${GITHUB_BASE_REF:-}" != "dev" ||
      -z "${RUNNER_TEMP:-}" ]]; then
  echo "REFUSED: this smoke is permitted only in the repository's disposable dev PR runner" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"
umask 077
envfile="$RUNNER_TEMP/prp-unified-stage-ci-$$.env"
project="prp-unified-stage-ci"
compose=(docker compose --project-name "$project" --env-file "$envfile" \
  --profile unified-review -f app/deploy/unified-staging/compose.review.yaml)

cleanup() {
  if [[ -s "$envfile" ]]; then
    "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -f -- "$envfile"
}
trap cleanup EXIT

python3 - "$envfile" <<'PY'
from pathlib import Path
import secrets
import sys
pairs = {
    "PRP_UNIFIED_PUBLIC_HOST": "prp-unified.example.org",
    "PRP_UNIFIED_PUBLIC_URL": "https://prp-unified.example.org",
    "PRP_UNIFIED_AUTH_ISSUER": "https://auth-unified.example.org/realms/prp-unified",
    "PRP_UNIFIED_LOOPBACK_PORT": "23080",
    "PRP_UNIFIED_DB_ROOT_PASSWORD": secrets.token_hex(32),
    "PRP_UNIFIED_DB_PASSWORD": secrets.token_hex(32),
    "PRP_UNIFIED_JWT_SECRET": secrets.token_hex(32),
    "PRP_UNIFIED_BOOTSTRAP_USERNAME": "synthetic_stage_owner",
    "PRP_UNIFIED_BOOTSTRAP_PASSWORD": secrets.token_hex(32),
}
Path(sys.argv[1]).write_text("".join(f"{k}={v}\n" for k, v in pairs.items()))
PY

python3 app/deploy/unified-staging/check_env.py --env-file "$envfile" >/dev/null
"${compose[@]}" config --quiet
node app/scripts/verify-db-migrations.mjs

# Images, volumes and services exist only in this isolated GitHub-hosted runner.
"${compose[@]}" build backend gateway
"${compose[@]}" up -d

ready=0
for attempt in $(seq 1 90); do
  if curl -fsS --max-time 4 -H 'Host: prp-unified.example.org' \
      http://127.0.0.1:23080/api/health >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done
if [[ "$ready" != "1" ]]; then
  echo "FAIL: disposable PRP API health did not become ready" >&2
  # Report fixed state fields and status only. Keep response bodies and logs private.
  for service in mysql backend gateway; do
    container_id="$("${compose[@]}" ps --all --quiet "$service")"
    if [[ -n "$container_id" ]]; then
      printf '%s ' "$service"
      docker inspect --format 'state={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}}{{if .State.Health}} health={{.State.Health.Status}}{{end}}' "$container_id" || true
    else
      printf '%s missing\n' "$service"
    fi
  done
  curl -sS --max-time 4 -H 'Host: prp-unified.example.org' \
    -o /dev/null -w 'host-to-gateway HTTP %{http_code}\n' \
    http://127.0.0.1:23080/api/health || true
  for target in 127.0.0.1 backend; do
    printf 'gateway probe to %s\n' "$target"
    "${compose[@]}" exec -T gateway wget -T 4 -S -O /dev/null \
      --header 'Host: prp-unified.example.org' "http://$target:8080/api/health" 2>&1 |
      awk '/^  HTTP\// {print $1, $2} /^wget:/ {print "wget request failed"}' || true
  done
  exit 1
fi
echo "PASS: disposable PRP API health"

curl -fsS --max-time 8 -H 'Host: prp-unified.example.org' \
    http://127.0.0.1:23080/prp/ >/dev/null
echo "PASS: disposable Web/PWA /prp/"

expect_status() {
  local expected="$1" endpoint="$2" host="$3"
  local status
  status="$(curl --silent --show-error --max-time 8 --output /dev/null \
    --write-out '%{http_code}' -H "Host: $host" \
    "http://127.0.0.1:23080$endpoint")"
  if [[ "$status" != "$expected" ]]; then
    echo "FAIL: expected HTTP $expected for safe route test" >&2
    exit 1
  fi
}
expect_status 421 /api/health micor.top
expect_status 404 /api/mcp prp-unified.example.org
expect_status 404 /api/mcp/tools prp-unified.example.org
expect_status 404 /.well-known/oauth-protected-resource/api/mcp prp-unified.example.org
expect_status 404 /prp/api/health prp-unified.example.org
echo "PASS: wrong Host / OAuth / MCP / wrong prefix all rejected"

expected="$(node -e 'const p=require("./app/deploy/migration-policy.json");console.log(Math.max(...p.rules.map(x=>x.version)))')"
if [[ ! "$expected" =~ ^[0-9]+$ ]]; then
  echo "FAIL: invalid reviewed Flyway expected version" >&2
  exit 1
fi
actual="$("${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_unified_stage -e "SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank DESC LIMIT 1;"')"
if [[ "$actual" != "$expected" ]]; then
  echo "FAIL: disposable Flyway version differs from reviewed migration policy" >&2
  exit 1
fi
echo "PASS: disposable fresh DB Flyway matches reviewed migration policy"

mapfile -t running_ids < <("${compose[@]}" ps --status running --quiet)
if [[ "${#running_ids[@]}" == 3 ]]; then
  echo "Disposable resource snapshot after successful probes (not a peak measurement)"
  docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}}' "${running_ids[@]}" || true
fi

# This tests a disposable baseline source, NOT full feature candidate integration,
# a persistent staging host, iPhone Safari or production release readiness.
echo "PASS: unified Staging CI disposable boot and basic isolation only"

# Only the same-repository integration PR exports its tested runtime images.
if [[ "${PRP_EXPORT_TESTED_IMAGES:-}" == true ]]; then
  bundle="$RUNNER_TEMP/prp-unified-staging-images"
  mkdir -m 700 -- "$bundle"
  images=()
  for service in backend gateway mysql; do
    container_id="$("${compose[@]}" ps --quiet "$service")"
    image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    [[ "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]]
    image_ref="prp-unified-staging-$service:$(git rev-parse --short=12 HEAD)"
    docker tag "$image_id" "$image_ref"
    images+=("$image_ref")
    printf '%s %s %s\\n' "$service" "$image_ref" "$image_id" >> "$bundle/IMAGE-IDS"
  done
  git rev-parse HEAD HEAD^{tree} > "$bundle/SOURCE"
  docker save "${images[@]}" | gzip -1 > "$bundle/images.tar.gz"
  (cd "$bundle" && sha256sum SOURCE IMAGE-IDS images.tar.gz > SHA256SUMS)
fi
