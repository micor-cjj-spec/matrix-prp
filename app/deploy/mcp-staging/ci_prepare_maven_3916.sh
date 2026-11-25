#!/usr/bin/env bash
# CI-only bootstrap of the exact Apache Maven binary required by PRP.
# This script installs only into RUNNER_TEMP. It never modifies production hosts.
set -Eeuo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true ||
      "${RUNNER_OS:-}" != Linux ||
      -z "${RUNNER_TEMP:-}" ||
      ! "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]]; then
  echo 'CI_OFFICIAL_MAVEN_RUNNER_REQUIRED' >&2
  exit 2
fi

version='3.9.16'
# Verified against the independent checksum published at:
# https://downloads.apache.org/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip.sha512
checksum='ed41650d42485cfc243fad22158caf9cbb5dc408ce7a09ddb94dd42a019de929ca43065bfa450612cf12bf78b5cafa3884b96c090de326ff590448c933454af3'
url='https://downloads.apache.org/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip'
maven_dir="${RUNNER_TEMP}/apache-maven-${version}"
archive="${RUNNER_TEMP}/apache-maven-${version}-bin.zip"
umask 077
cleanup() { rm -f -- "$archive"; }
trap cleanup EXIT

# A retry never switches to a different origin or relaxes content verification.
download_ok=0
for delay in 0 8 20; do
  if (( delay > 0 )); then sleep "$delay"; fi
  rm -f -- "$archive"
  if curl --fail --silent --show-error --proto '=https' \
      --connect-timeout 10 --max-time 90 \
      --output "$archive" "$url"; then
    download_ok=1
    break
  fi
done
if [[ "$download_ok" != 1 ]]; then
  echo 'CI_OFFICIAL_MAVEN_DISTRIBUTION_DOWNLOAD_FAILED' >&2
  exit 1
fi

if ! printf '%s  %s\n' "$checksum" "$archive" | sha512sum --check --status; then
  echo 'CI_MAVEN_DISTRIBUTION_CHECKSUM_MISMATCH' >&2
  exit 1
fi
if [[ -e "$maven_dir" ]]; then
  echo 'CI_MAVEN_DESTINATION_ALREADY_EXISTS' >&2
  exit 1
fi
unzip -q "$archive" -d "$RUNNER_TEMP"
if [[ ! -x "$maven_dir/bin/mvn" ]]; then
  echo 'CI_PINNED_MAVEN_EXECUTABLE_MISSING' >&2
  exit 1
fi
echo 'CI_OFFICIAL_MAVEN_3916_SHA512_VERIFIED=YES'
