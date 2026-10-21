#!/usr/bin/env bash
# ENG-03E: executable JAR smoke checks on two already prepared disposable
# MySQL 8.4 schemas. Cannot access production or install root controllers.
set -euo pipefail

if [[ "${CI:-}" != "true" || "${GITHUB_ACTIONS:-}" != "true" ||
      "${PRP_EXPANDED_APP_TEST:-}" != "synthetic-only" ||
      "${MYSQL_PWD:-}" != "ci-app-password" ]]; then
  echo "Synthetic CI-only executable-JAR probe" >&2; exit 2
fi

root="${GITHUB_WORKSPACE:?}"
temp="${RUNNER_TEMP:?}"
[[ -d "${root}/baseline/app/backend" && -d "${root}/app/backend" ]] || {
  echo "Two source checkouts are mandatory" >&2; exit 2;
}
[[ "$(git -C "$root" rev-parse HEAD)" = "${GITHUB_SHA:?}" ]] || {
  echo "Candidate source SHA mismatch" >&2; exit 2;
}
mkdir -p "$temp/prp-expand-jar-receipts"
chmod 700 "$temp/prp-expand-jar-receipts"

# Deliberately pin all connection destinations, ports and database names in CI.
# No service, credentials or media path from a remote environment is reused.
probe_one() {
  local label="$1" checkout="$2" database="$3" port="$4"
  case "${label}/${database}/${port}" in
    baseline/matrix_prp_expand_app_baseline/4181|candidate/matrix_prp_expand_app_candidate/4182) ;;
    *) echo "Unexpected synthetic configuration" >&2; exit 2 ;;
  esac
  local source_sha
  source_sha="$(git -C "$checkout" rev-parse HEAD)"
  (
    cd "$checkout/app/backend"
    chmod +x ./mvnw
    ./mvnw -B -DskipTests package
  )
  local jar="$checkout/app/backend/target/matrix-prp-backend-0.0.1-SNAPSHOT.jar"
  [[ -f "$jar" ]] || { echo "Packaged runnable JAR missing" >&2; exit 2; }
  echo "ENG-03E $label packaged source SHA: $source_sha"
  echo "ENG-03E $label packaged JAR SHA256: $(sha256sum "$jar" | cut -d' ' -f1)"

  (
    export MATRIX_PRP_DB_URL="jdbc:mysql://127.0.0.1:3306/${database}?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true"
    export MATRIX_PRP_DB_USER=matrix_prp
    export MATRIX_PRP_DB_PASSWORD=ci-app-password
    export MATRIX_PRP_FLYWAY_ENABLED=false
    export MATRIX_PRP_BOOTSTRAP_USERNAME=video_admin
    export MATRIX_PRP_BOOTSTRAP_PASSWORD=video-test-admin-password-2026
    export MATRIX_PRP_JWT_SECRET=ci-integration-only-secret-key-at-least-32-bytes
    export MATRIX_PRP_VIDEO_ROOT="$temp/prp-expand-jar-media-$label"
    export MATRIX_PRP_AI_SPRING_AI_ENABLED=false
    export MATRIX_PRP_CODEX_ENABLED=false
    export MATRIX_PRP_OPENCLAW_ENABLED=false
    # Isolated localhost listener, independent process; no test profile that
    # could disable JDBC and silently replace real persistence.
    exec java -Xmx280m -XX:MaxMetaspaceSize=180m -jar "$jar" \
      --server.address=127.0.0.1 --server.port="$port"
  ) > "$temp/prp-expand-$label-jar.log" 2>&1 &
  local pid=$!
  cleanup() {
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      wait "$pid" || true
    fi
  }
  trap cleanup EXIT INT TERM
  if ! python3 "$root/app/scripts/probe-expanded-jar-http.py" \
      --port "$port" --jar "$jar" --commit "$source_sha" \
      --output "$temp/prp-expand-jar-receipts/prp-$label-jar-http.json"; then
    echo "ENG-03E failed to probe $label JAR (last log lines, secrets redacted)" >&2
    # Avoid uploading traces; application log can include private/session data.
    exit 1
  fi
  cleanup
  trap - EXIT INT TERM
}
probe_one baseline "$root/baseline" matrix_prp_expand_app_baseline 4181
probe_one candidate "$root" matrix_prp_expand_app_candidate 4182

python3 - "$temp/prp-expand-jar-receipts" <<'PY'
import json
import sys
from pathlib import Path
folder = Path(sys.argv[1])
a = json.loads((folder / "prp-baseline-jar-http.json").read_text())
b = json.loads((folder / "prp-candidate-jar-http.json").read_text())
assert a["source_commit"] != b["source_commit"], "Two distinct source commits required"
for data in (a,b):
    assert data["production_deployment_attested"] is False
    assert data["production_authorized"] is False
    assert all(v == "PASS" for v in data["checks"].values())
print("ENG-03E: both packaged JARs verified over localhost HTTP; provenance receipts are non-authorizing")
PY
