#!/usr/bin/env bash
# ENG-03D: run actual Spring Boot finance API integration suites from both
# current main and candidate code against separately expanded CI MySQL schemas.
# This is CI synthetic evidence, NOT proof of deployed JAR compatibility.
set -euo pipefail

if [[ "${CI:-}" != "true" || "${GITHUB_ACTIONS:-}" != "true" ||
      "${PRP_EXPANDED_APP_TEST:-}" != "synthetic-only" ||
      "${MYSQL_PWD:-}" != "ci-app-password" ]]; then
  echo "Refusing non-CI/non-synthetic compatibility rehearsal" >&2
  exit 2
fi

candidate="${GITHUB_WORKSPACE:?GITHUB_WORKSPACE required}"
baseline="${candidate}/baseline"
if [[ ! -f "${baseline}/app/backend/pom.xml" || ! -f "${candidate}/app/backend/pom.xml" ]]; then
  echo "Both independent checkouts must be present" >&2
  exit 2
fi
if ! diff -qr "${baseline}/app/backend/src/main/resources/db/migration" \
                "${candidate}/app/backend/src/main/resources/db/migration" >/dev/null ||
   ! diff -qr "${baseline}/app/docker/mysql/init" "${candidate}/app/docker/mysql/init" >/dev/null; then
  echo "SQL baselines differ: do not claim identical expanded-schema compatibility" >&2
  exit 2
fi

old_schema=matrix_prp_expand_app_baseline
new_schema=matrix_prp_expand_app_candidate
app_mysql() {
  local db="$1"
  shift
  case "$db" in
    "$old_schema"|"$new_schema") ;;
    *) echo "Unexpected DB target" >&2; exit 2;;
  esac
  mysql --protocol=TCP --default-character-set=utf8mb4 -h 127.0.0.1 \
    -u matrix_prp "$db" "$@"
}

for schema in "$old_schema" "$new_schema"; do
  for source in "${candidate}"/app/docker/mysql/init/*.sql; do
    app_mysql "$schema" < "$source"
  done
  while IFS= read -r migration; do
    version="$(basename "$migration" | sed -E 's/^V([0-9]+)__.*/\1/')"
    if [[ "$version" -gt 7 ]]; then
      app_mysql "$schema" < "$migration"
    fi
  done < <(find "${candidate}/app/backend/src/main/resources/db/migration" \
    -maxdepth 1 -name 'V*__*.sql' -type f | sort -V)

  # Test-only additive field, never a Flyway migration or production contract.
  app_mysql "$schema" <<'SQL'
ALTER TABLE prp_finance_transactions
  ADD COLUMN schema_probe VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
SQL
  actual="$(app_mysql "$schema" -N -B -e \
    "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='prp_finance_transactions' AND COLUMN_NAME='schema_probe' AND IS_NULLABLE='YES';")"
  [[ "$actual" == "1" ]] || { echo "Expanded column missing from CI schema" >&2; exit 2; }
done

run_backend() {
  local source="$1" schema="$2" label="$3"
  echo "ENG-03D ${label} source commit: $(git -C "$source" rev-parse HEAD)"
  (
    cd "${source}/app/backend"
    export MATRIX_PRP_DB_URL="jdbc:mysql://127.0.0.1:3306/${schema}?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true"
    export MATRIX_PRP_DB_USER=matrix_prp
    export MATRIX_PRP_DB_PASSWORD=ci-app-password
    export MATRIX_PRP_FLYWAY_ENABLED=false
    export MATRIX_PRP_BOOTSTRAP_USERNAME=video_admin
    export MATRIX_PRP_BOOTSTRAP_PASSWORD=video-test-admin-password-2026
    export MATRIX_PRP_JWT_SECRET=ci-integration-only-secret-key-at-least-32-bytes
    export MATRIX_PRP_VIDEO_ROOT="${RUNNER_TEMP:?}/prp-expand-video-${label}"
    chmod +x ./mvnw
    ./mvnw -B -Dtest=FinanceLedgerDatabaseIT,FinanceImportDatabaseIT test
  )
  local unexpected
  unexpected="$(app_mysql "$schema" -N -B -e \
    "SELECT COUNT(*) FROM prp_finance_transactions WHERE schema_probe IS NOT NULL;")"
  [[ "$unexpected" == "0" ]] || { echo "Legacy backend unexpectedly wrote schema_probe" >&2; exit 2; }
  echo "ENG-03D ${label}: API finance regressions passed on expanded synthetic schema"
}

run_backend "$baseline" "$old_schema" baseline
run_backend "$candidate" "$new_schema" candidate

echo "ENG-03D RESULT: CI-only finance API/ownership/idempotency compatibility passed for two source checkouts."
echo "NOT proven: deployed production JAR, authenticated network HTTP smoke, real backup, controller authorization."
