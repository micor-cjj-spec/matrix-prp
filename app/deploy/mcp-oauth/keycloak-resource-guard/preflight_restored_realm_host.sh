#!/usr/bin/env bash
# READ-ONLY host resource/version/readiness inventory. Nothing is installed.
# No docker run/exec shell, no compose, no restore, no Keycloak HTTP write.
set -Eeuo pipefail
umask 077
LIVE_KC=prp-mcp-oauth-stage-keycloak-1
LIVE_DB=prp-mcp-oauth-stage-auth-db-1
V2=/root/matrix-prp-mcp-v2-staging
DUMP=/root/prp-mcp-backups/snapshot-4G42atvf/keycloak-stage.dump
EXPECTED_DUMP_SHA256=0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17
echo '=== READ ONLY: PRODUCTION AND KEYCLOAK ==='
printf 'PRP_SERVICE=%s\n' "$(systemctl is-active matrix-prp.service 2>/dev/null || echo UNAVAILABLE)"
for c in "$LIVE_KC" "$LIVE_DB"; do
  printf '%s=%s\n' "$c" "$(docker inspect "$c" -f '{{.State.Status}}' 2>/dev/null || echo NOT_FOUND)"
done
printf 'KEYCLOAK_IMAGE_NAME=%s\n' "$(docker inspect "$LIVE_KC" -f '{{.Config.Image}}' 2>/dev/null || echo UNKNOWN)"
# Keycloak may print JAVA_OPTS information before the version line.
# The old two-line output limit could SIGPIPE under pipefail.
# Read command output once without raw stdout/stderr disclosure; only
# emit a validated version number. Do not stop subsequent backup checks.
version_text=$(docker exec "$LIVE_KC" /opt/keycloak/bin/kc.sh --version 2>/dev/null) || version_text=""
kc_version=""
while IFS= read -r line; do
  case "$line" in
    "Keycloak "*)
      candidate=${line#Keycloak }
      if [[ "$candidate" =~ ^[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
        kc_version=$candidate
        break
      fi
      ;;
  esac
done <<< "$version_text"
if [[ -n "$kc_version" ]]; then
  printf "KEYCLOAK_VERSION=%s\n" "$kc_version"
else
  echo "KEYCLOAK_VERSION=UNVERIFIED"
fi
unset version_text
echo '=== READ ONLY: BACKUP INTEGRITY ==='
if [[ -f "$DUMP" && "$(head -c 5 "$DUMP")" = PGDMP &&
      "$(sha256sum "$DUMP" | awk '{print $1}')" = "$EXPECTED_DUMP_SHA256" ]]; then
  echo 'PINNED_POSTGRES_DUMP=PASS'
else
  echo 'PINNED_POSTGRES_DUMP=FAIL'
fi
echo '=== READ ONLY: HOST BUILD AND ARTIFACT OPTIONS ==='
for app in git docker nsenter python3 curl sha256sum java mvn gh; do
  if command -v "$app" >/dev/null 2>&1; then
    echo "HOST_TOOL_$app=YES"
  else
    echo "HOST_TOOL_$app=NO"
  fi
done
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo 'GH_ACTIONS_ARTIFACT_DOWNLOAD=AUTH_READY'
else
  echo 'GH_ACTIONS_ARTIFACT_DOWNLOAD=NOT_READY'
fi
if docker image inspect quay.io/keycloak/keycloak:26.8.1 >/dev/null 2>&1; then
  echo 'KEYCLOAK_26_8_1_IMAGE=CACHED'
else
  echo 'KEYCLOAK_26_8_1_IMAGE=NOT_CACHED'
fi
if [[ -d "$V2/.git" || -f "$V2/.git" ]]; then
  echo "V2_HEAD=$(git -C "$V2" rev-parse --short=12 HEAD)"
  if [[ -n "$(git -C "$V2" status --porcelain -- app/deploy/mcp-staging/compose.yaml)" ]]; then
    echo 'V2_COMPOSE_LOCAL_CHANGES=PRESENT_DO_NOT_RESET'
  else
    echo 'V2_COMPOSE_LOCAL_CHANGES=NONE'
  fi
else
  echo 'V2_WORKTREE=NOT_FOUND'
fi
echo '=== READ ONLY: RESOURCES / RESIDUES ==='
awk '/MemAvailable:/ {printf "MEM_AVAILABLE_KIB=%s\n", $2}' /proc/meminfo
df -Pk / | awk 'END{printf "DISK_AVAILABLE_KIB=%s\n",$4}'
residual=$(docker ps -a --format '{{.Names}}' | grep -Ec '^prp-kc-(clone|ns)-' || true)
printf 'CLONE_TEST_CONTAINER_RESIDUES=%s\n' "$residual"
echo 'READ_ONLY_PREFLIGHT_COMPLETE=YES'
