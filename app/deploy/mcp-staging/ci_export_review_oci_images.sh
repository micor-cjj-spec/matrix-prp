#!/usr/bin/env bash
# Explicitly unapproved, short-lived REVIEW artifact after full disposable OCI tests.
# No registry push, Keycloak mutation, production DB/host contact or deployment.
set -Eeuo pipefail
umask 077

if [[ "${GITHUB_ACTIONS:-}" != true ||
      "${RUNNER_OS:-}" != Linux ||
      ! "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ||
      ! -d "${RUNNER_TEMP:-}/" ]]; then
  echo "GITHUB_DISPOSABLE_LINUX_RUNNER_REQUIRED" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)"
revision="$(git rev-parse HEAD)"
if [[ ! "$revision" =~ ^[a-f0-9]{40}$ || "$revision" != "${GITHUB_SHA:-}" ]]; then
  echo "REVIEW_REVISION_NOT_EXACT_CI_CHECKOUT" >&2
  exit 2
fi

tag="${revision:0:12}"
api="prp-mcp-review-api-ci-only:${tag}"
web="prp-mcp-review-web-ci-only:${tag}"
dest="${RUNNER_TEMP}/prp-reviewed-oci-images"
if [[ -e "$dest" || -L "$dest" ]]; then
  echo "REVIEW_ARCHIVE_DEST_ALREADY_EXISTS" >&2
  exit 2
fi
mkdir -m 700 -- "$dest"

for image in "$api" "$web"; do
  if [[ "$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")" != "$revision" ||
        "$(docker image inspect -f '{{ index .Config.Labels "prp.release-authorized" }}' "$image")" != false ]]; then
    echo "OCI_IMAGE_REVIEW_LABEL_MISMATCH" >&2
    exit 2
  fi
done

api_id="$(docker image inspect -f '{{.Id}}' "$api")"
web_id="$(docker image inspect -f '{{.Id}}' "$web")"
[[ "$api_id" =~ ^sha256:[a-f0-9]{64}$ && "$web_id" =~ ^sha256:[a-f0-9]{64}$ ]] || {
  echo "OCI_IMAGE_IDS_UNVERIFIED" >&2
  exit 2
}
[[ "$(docker image inspect -f '{{.Config.User}}' "$api")" == prp ]] || {
  echo "OCI_BACKEND_USER_CHANGED" >&2
  exit 2
}

# docker save exports exactly the reviewed runtime image references, not
# the build-stage layers. Compressed files are ephemeral CI-only artifacts.
docker save "$api" | gzip -1 > "$dest/backend-image.tar.gz"
docker save "$web" | gzip -1 > "$dest/web-image.tar.gz"
test -s "$dest/backend-image.tar.gz" && test -s "$dest/web-image.tar.gz"
(
  cd "$dest"
  sha256sum backend-image.tar.gz web-image.tar.gz > SHA256SUMS
  sha256sum --check --status SHA256SUMS
)
python3 - "$dest/REVIEW-MANIFEST.json" "$revision" "$api_id" "$web_id" <<'PY'
import json
import os
import sys
from pathlib import Path
path, commit, backend, gateway = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "status": "CI_REVIEW_ONLY_NO_RELEASE_AUTHORITY",
    "github_source_checkout_sha": commit,
    "backend_image_id": backend,
    "gateway_image_id": gateway,
    "gateway_host_port": "NOT_INSTALLED",
    "expected_existing_v2_port": "127.0.0.1:18082",
    "legacy_18081_compose_allowed": False,
    "no_registry_push": True,
    "no_host_deployment": True,
    "no_g0_b2_approval": True,
    "production_prp_database_touched": False,
    "mcp_writes_enabled": False,
    "archives": ["backend-image.tar.gz", "web-image.tar.gz"],
    "digest_file": "SHA256SUMS",
}
p = Path(path)
p.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(p, 0o600)
PY
echo "REVIEW_OCI_ARCHIVE_PREPARED=YES"
echo "REVIEW_IMAGE_SOURCE_SHA=$revision"
echo "REVIEW_ONLY_NOT_APPROVED_FOR_INSTALL=YES"
echo "ORIGINAL_KEYCLOAK_AND_NGINX_UNCHANGED=YES"
