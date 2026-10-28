#!/usr/bin/env bash
# Non-mutating operator review: exact ChatGPT client_id + first-party client
# and three required scopes in the *existing isolated* Keycloak Postgres.
# Reads exactly the immutable Git-object SQL from an explicitly supplied SHA.
# No Keycloak Admin API, psql writes, credentials, dump or host config access.
set -Eeuo pipefail

if [[ $# -ne 1 || ! $1 =~ ^[0-9a-f]{40}$ ]]; then
  echo "REVIEW_PIN_REQUIRED_40_LOWERCASE_HEX"
  exit 2
fi
if [[ ${EUID} -ne 0 ]]; then
  echo "REVIEW_REQUIRES_AUTHORIZED_HOST_OPERATOR"
  exit 2
fi

PIN=$1
REPO=/root/matrix-prp-mcp-v2-staging
PG=prp-mcp-oauth-stage-auth-db-1
SQL=app/deploy/mcp-oauth/keycloak-resource-guard/realm_scope_readonly.sql

echo "=== EXACT CHATGPT CLIENT READ-ONLY REVIEW ==="
if [[ ! -d "$REPO/.git" && ! -f "$REPO/.git" ]]; then
  echo "ISOLATED_REVIEW_GIT=UNAVAILABLE"
  exit 2
fi
if ! git -C "$REPO" cat-file -e "$PIN:$SQL" 2>/dev/null; then
  echo "REVIEWED_SQL_PIN=UNAVAILABLE"
  exit 2
fi

# Hard-coded preflight; never accept arbitrary container, database or SQL.
state=$(docker inspect -f '{{.State.Status}}' "$PG" 2>/dev/null) || {
  echo "KEYCLOAK_PG_CONTAINER=UNAVAILABLE"
  exit 2
}
if [[ "$state" != "running" ]]; then
  echo "KEYCLOAK_PG_CONTAINER=NOT_RUNNING"
  exit 2
fi
image=$(docker inspect -f '{{.Config.Image}}' "$PG" 2>/dev/null) || {
  echo "KEYCLOAK_PG_IMAGE=UNVERIFIED"
  exit 2
}
case "$image" in
  postgres:*|*/postgres:*) ;;
  *) echo "KEYCLOAK_PG_IMAGE=UNEXPECTED"; exit 2 ;;
esac

echo "KEYCLOAK_PG_CONTAINER=RUNNING_EXPECTED_NAME"
echo "REVIEWED_SQL_PIN=FOUND"
echo "READ_ONLY_SQL_RESULTS_BEGIN"
# The pinned SQL begins BEGIN TRANSACTION READ ONLY; ends COMMIT;
# and projects only a fixed allowlist of public client/scope labels and counts.
# No secrets, client attributes, user identity rows or policy JSON are queried.
git -C "$REPO" show "$PIN:$SQL" |
  docker exec -i "$PG" psql -X -q -v ON_ERROR_STOP=1 -U keycloak -d keycloak -A -t -F '='
echo "READ_ONLY_SQL_RESULTS_END"
echo "MCP_DEPLOYMENT_PERMITTED=NO"
echo "LIVE_EXACT_CLIENT_REVIEW_COMPLETE=YES"
