#!/usr/bin/env bash
# Disposable GitHub Actions Runner ONLY.
# Start an isolated brand-new MySQL/Vue/Java PRP stack from the review Compose.
# Not intended or permitted on the user's persistent host.
set -Eeuo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" ||
      "${RUNNER_OS:-}" != "Linux" ||
      -z "${RUNNER_TEMP:-}" ||
      ! "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]]; then
  echo "GITHUB_DISPOSABLE_RUNNER_REQUIRED" >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"
umask 077
project="prp-mcp-newdb-ci-${GITHUB_RUN_ID}"
tmp="$(mktemp -d "${RUNNER_TEMP}/prp-newdb-smoke.XXXXXX")"
compose=(docker compose --project-name "$project" --profile newdb-review
  --env-file "$tmp/.env" -f app/deploy/mcp-staging/compose.newdb.review.yaml)
cleanup() {
  # ONLY the unique disposable CI project is deleted. No external project
  # volumes, old PRP stage or production service are in this project.
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

python3 app/deploy/mcp-staging/prepare_env.py \
  --stage-host prp-test.micor.top --auth-host auth-test.micor.top \
  --output "$tmp/.env" >/dev/null
# Never let the stack run unless the fixed review version of every service
# and the original public-stage feature flags have passed read-only validation.
python3 app/deploy/mcp-staging/check_newdb_review.py
echo 'CI NEWDB: isolated review contract passed; MCP/OAuth/writes remain OFF.'
"${compose[@]}" up -d --build

healthy=0
for _ in $(seq 1 90); do
  if curl --noproxy '*' -fsS -H 'Host: prp-test.micor.top' \
      --connect-timeout 2 --max-time 4 \
      http://127.0.0.1:18083/api/health >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  echo 'CI_NEWDB_BACKEND_HEALTH_TIMEOUT' >&2
  exit 1
fi
echo 'PASS NEWDB CI: actual isolated Java backend + nginx gateway ready'

for path in /prp/login /prp/me/mcp-clients /prp/me/mcp-link/callback; do
  status="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
    -H 'Host: prp-test.micor.top' "http://127.0.0.1:18083$path")"
  if [[ "$status" != 200 ]]; then
    echo 'CI_NEWDB_SPA_ROUTING_FAILED' >&2
    exit 1
  fi
done
wrong="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  -H 'Host: micor.top' http://127.0.0.1:18083/prp/login)"
[[ "$wrong" == 421 ]] || { echo 'CI_NEWDB_HOST_GUARD_FAILED' >&2; exit 1; }
nested="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  -H 'Host: prp-test.micor.top' http://127.0.0.1:18083/prp/api/mcp)"
[[ "$nested" == 404 ]] || { echo 'CI_NEWDB_PREFIX_GUARD_FAILED' >&2; exit 1; }
echo 'PASS NEWDB CI: three SPA routes and exact Host/API-prefix guards'

mysql_version=$("${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_mcp_newdb_review -e "SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank DESC LIMIT 1;"')
[[ "$mysql_version" == 28 ]] || {
  echo 'CI_NEWDB_FLYWAY_LATEST_NOT_V28' >&2; exit 1;
}
# Prove this is the NEW, corrected branch schema (not old MCP V24).
lineage=$("${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_mcp_newdb_review -e "SELECT CONCAT(version, CHAR(9), script) FROM flyway_schema_history WHERE version IN (24,25,26,27,28) AND success=1 ORDER BY installed_rank;"')
for entry in \
  $'24\tV24__vocal_song_library_and_assignments.sql' \
  $'25\tV25__mcp_write_drafts.sql' \
  $'26\tV26__mcp_client_grants.sql' \
  $'27\tV27__mcp_identity_links.sql' \
  $'28\tV28__mcp_first_party_oidc_link_flows.sql'
do
  grep -Fxq "$entry" <<<"$lineage" || {
    echo 'CI_NEWDB_FLYWAY_LINEAGE_DRIFT' >&2
    exit 1
  }
done
table=$("${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_mcp_newdb_review -e "SHOW TABLES LIKE '\''prp_mcp_oidc_link_flows'\'';"')
[[ "$table" == prp_mcp_oidc_link_flows ]] || {
  echo 'CI_NEWDB_OIDC_FLOW_TABLE_MISSING' >&2
  exit 1
}
echo 'PASS NEWDB CI: virgin isolated MySQL applied corrected Flyway V24-28 and created OIDC table'

# No real ChatGPT client, network publication, or live authorization is
# exercised. The ephemeral credentials never enter logs or Git history.
echo 'NO_PUBLIC_INGRESS_NO_KEYCLOAK_MUTATION_NO_EXISTING_DB_OR_V2_CHANGE=YES'
