#!/usr/bin/env bash
# First-empty-volume initialization only. No PRP database access, no credential output.
set -euo pipefail
case "${PRP_HEALTH_DB_PASSWORD:-}" in ''|*[!A-Za-z0-9_-]*) echo AUTH_DB_SECRET_FORMAT_INVALID >&2; exit 1;; esac
if (( ${#PRP_HEALTH_DB_PASSWORD} < 32 )); then echo AUTH_DB_SECRET_TOO_SHORT >&2; exit 1; fi
if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres >/dev/null 2>&1 <<SQL
CREATE ROLE prp_health_auth LOGIN PASSWORD '$PRP_HEALTH_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE DATABASE prp_health_auth OWNER prp_health_auth;
SQL
then
  echo AUTH_DATABASE_INITIALIZATION_FAILED >&2
  exit 1
fi
