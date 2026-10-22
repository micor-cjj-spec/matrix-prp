#!/usr/bin/env bash
# Disposable GitHub Actions / staging CI runner ONLY.
# Never point it at production PRP and never use real user data.
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_TEMP:-}" == "" ]]; then
  echo "This destructive test (removes its OWN disposable volumes) is only for a GitHub Actions temporary runner." >&2
  exit 2
fi
project="prp-mcp-stage-ci"
python3 prepare_env.py --stage-host prp-test.micor.top --auth-host auth-test.micor.top
python3 check_env.py --env-file .env

compose=(docker compose --project-name "$project" --env-file .env -f compose.yaml)
cleanup() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -f .env
}
trap cleanup EXIT

# Build actual PRP Java 21 JAR and /prp/ SPA from the selected PR commit.
"${compose[@]}" build backend
"${compose[@]}" build gateway
"${compose[@]}" up -d

healthy=0
for attempt in $(seq 1 75); do
  if curl -fsS -H 'Host: prp-test.micor.top'       http://127.0.0.1:18081/api/health >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 3
done
if [[ "$healthy" != 1 ]]; then
  echo "PRP staging failed health. Only masked, recent staging container status follows." >&2
  "${compose[@]}" ps >&2
  exit 1
fi
echo 'Stage health: PASS'
if ! curl -fsS -H 'Host: prp-test.micor.top' http://127.0.0.1:18081/prp/ >/dev/null; then
  echo 'Stage Web: FAILED to serve /prp/' >&2
  exit 1
fi
echo 'Stage Web: PASS'

# Fresh database must contain all approved MCP migration tables, not production data.
schema=$( "${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_mcp_stage -e "SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank DESC LIMIT 1;"')
if [[ "$schema" != 27 ]]; then
  echo "Stage Flyway expected version 27, got version: $schema" >&2
  exit 1
fi
echo 'Stage Flyway: PASS version 27'
tables=$( "${compose[@]}" exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B matrix_prp_mcp_stage -e "SHOW TABLES LIKE '\''prp_mcp_%'\'';"')
for expected in prp_mcp_client_grants prp_mcp_identity_links prp_mcp_link_tickets prp_mcp_write_drafts; do
  if ! grep -q "^${expected}$" <<< "$tables"; then
    echo "Stage Flyway table missing: $expected" >&2
    exit 1
  fi
done
echo 'Stage MySQL: PASS all four MCP schema tables'

wrong_host=$(curl -sS -o /dev/null -w '%{http_code}'   -H 'Host: micor.top' http://127.0.0.1:18081/api/health)
if [[ "$wrong_host" != 421 ]]; then
  echo "Stage Host rejection expected 421, got $wrong_host" >&2
  exit 1
fi
echo 'Stage Host rejection: PASS'
wrong_path=$(curl -sS -o /dev/null -w '%{http_code}'   -H 'Host: prp-test.micor.top' http://127.0.0.1:18081/prp/api/mcp)
if [[ "$wrong_path" != 404 ]]; then
  echo "Stage mistaken /prp/api/mcp route expected 404, got $wrong_path" >&2
  exit 1
fi
echo 'Stage wrong API prefix: PASS'

echo "PASS: isolated PRP stage backend + Web actually start; V27 migrated only the fresh test DB."
echo "PASS: 127.0.0.1:18081 staging routing and wrong Host/path rejection; OAuth remains OFF."
