#!/usr/bin/env bash
# Opt-in, current staged Keycloak PostgreSQL point-in-time BACKUP ONLY.
# Writes a single root-private dump under /root/prp-mcp-backups.
# Does NOT restore, modify live Postgres/Keycloak, issue B2 receipts, install
# clients, alter PRP production, or declare a deployment safe.
set -Eeuo pipefail
umask 077

if [[ ${1:-} != --capture-current || $# -ne 1 ]]; then
  echo "EXPLICIT_CAPTURE_CURRENT_REQUIRED"
  exit 2
fi
if [[ ${EUID} -ne 0 ]]; then
  echo "AUTHORIZED_ROOT_OPERATOR_REQUIRED"
  exit 2
fi

ROOT=/root/prp-mcp-backups
DB=prp-mcp-oauth-stage-auth-db-1
KEYCLOAK=prp-mcp-oauth-stage-keycloak-1
DEST=""
COMPLETE=0

cleanup() {
  local code=$?
  if [[ "$COMPLETE" != 1 && -n "$DEST" && -d "$DEST" ]]; then
    # This directory was freshly created by mktemp under a verified parent.
    # Remove only the three exact files this script owns; no recursive delete.
    rm -f -- "$DEST/keycloak-current.dump" "$DEST/pg-dump-error.private" \
      "$DEST/pg-restore-check-error.private" || true
    rmdir -- "$DEST" 2>/dev/null || true
  fi
  if [[ "$COMPLETE" != 1 ]]; then
    echo "CURRENT_KEYCLOAK_BACKUP=FAILED_NO_B2_APPROVAL"
  fi
  exit "$code"
}
trap cleanup EXIT

echo "=== CURRENT KEYCLOAK BACKUP PRECONDITIONS ==="
test "$(systemctl is-active matrix-prp.service)" = active || {
  echo "PRP_MAIN_SERVICE_NOT_ACTIVE"; exit 2;
}
for name in "$DB" "$KEYCLOAK"; do
  if [[ "$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)" != running ]]; then
    echo "EXPECTED_STAGE_CONTAINER_NOT_RUNNING"
    exit 2
  fi
done
image=$(docker inspect -f '{{.Config.Image}}' "$DB" 2>/dev/null) || {
  echo "STAGE_POSTGRES_IMAGE_NOT_OBSERVED"; exit 2;
}
case "$image" in
  postgres:*|*/postgres:*) ;;
  *) echo "STAGE_POSTGRES_IMAGE_NOT_ALLOWLISTED"; exit 2 ;;
esac
if [[ ! -d "$ROOT" || -L "$ROOT" ]]; then
  echo "BACKUP_PARENT_UNSAFE_OR_MISSING"
  exit 2
fi
owner=$(stat -c '%u' -- "$ROOT")
mode=$(stat -c '%a' -- "$ROOT")
if [[ "$owner" != 0 || ! "$mode" =~ ^[0-7]{3,4}$ ]]; then
  echo "BACKUP_PARENT_OWNER_OR_PERMISSIONS_UNSAFE"
  exit 2
fi
if (( (8#$mode & 0022) != 0 )); then
  echo "BACKUP_PARENT_OWNER_OR_PERMISSIONS_UNSAFE"
  exit 2
fi
available_mem=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
available_disk=$(df -Pk "$ROOT" | awk 'END {print $4}')
if [[ ! "$available_mem" =~ ^[0-9]+$ || ! "$available_disk" =~ ^[0-9]+$ ||
      "$available_mem" -lt 2000000 || "$available_disk" -lt 15000000 ]]; then
  echo "BACKUP_RESOURCE_BUDGET_INSUFFICIENT"
  exit 2
fi

# Intentional new root-private files only, never overwrite a prior backup.
DEST=$(mktemp -d "$ROOT/keycloak-current-review-XXXXXXXX")
DUMP="$DEST/keycloak-current.dump"
echo "BACKUP_WRITE_SCOPE=NEW_ROOT_PRIVATE_DIRECTORY_ONLY"
# Use the existing live database container's own configured database/role.
# Neither role, database name nor password is exported or echoed.
if ! docker exec "$DB" sh -ec '
  if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_DB:-}" ]; then
    exit 42
  fi
  exec pg_dump -w -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' > "$DUMP" 2> "$DEST/pg-dump-error.private"; then
  echo "CURRENT_KEYCLOAK_PG_DUMP_FAILED_REDACTED"
  exit 3
fi
if [[ ! -s "$DUMP" ]]; then
  echo "CURRENT_KEYCLOAK_DUMP_EMPTY"
  exit 3
fi
if ! python3 - "$DUMP" <<'PY'
from pathlib import Path
import sys
with Path(sys.argv[1]).open('rb') as f:
    if f.read(5) != b'PGDMP':
        raise SystemExit(1)
PY
then
  echo "CURRENT_KEYCLOAK_DUMP_BAD_MAGIC"
  exit 3
fi
# Parse the archive through the SAME exact PostgreSQL container, without
# installing a host PG client and without revealing object names.
if ! docker exec -i "$DB" pg_restore --list \
  < "$DUMP" > /dev/null 2> "$DEST/pg-restore-check-error.private"; then
  echo "CURRENT_KEYCLOAK_DUMP_ARCHIVE_INVALID"
  exit 3
fi

# Remove local command stderr before marking the kept backup complete.
rm -f -- "$DEST/pg-dump-error.private" "$DEST/pg-restore-check-error.private"
chmod 0600 -- "$DUMP"
test "$(stat -c '%a' -- "$DUMP")" = 600
test "$(stat -c '%a' -- "$DEST")" = 700
HASH=$(sha256sum "$DUMP" | awk '{print $1}')
BYTES=$(stat -c '%s' "$DUMP")
COMPLETE=1
echo "CURRENT_KEYCLOAK_BACKUP=CAPTURED_AND_ARCHIVE_PARSED"
echo "BACKUP_SHA256=$HASH"
echo "BACKUP_BYTES=$BYTES"
echo "PRIVATE_BACKUP_PATH=$DUMP"
echo "CURRENT_KEYCLOAK_RESTORED=NO"
echo "CURRENT_KEYCLOAK_SIGNING_KEYS_CLONE_VERIFIED=NO"
echo "B2_RECEIPTS_ISSUED=NO"
echo "G0_B2_INSTALL_PERMITTED=NO"
