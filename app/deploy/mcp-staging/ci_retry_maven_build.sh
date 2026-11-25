#!/usr/bin/env bash
# Disposable CI only. Based on #313's bounded category-specific retry.
set -Eeuo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_OS:-}" != Linux ||
      -z "${RUNNER_TEMP:-}" || ! "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]]; then
  echo 'CI_MAVEN_RETRY_RUNNER_REQUIRED' >&2
  exit 2
fi
mode="${1:-}"
case "$mode" in E2E|OCI) ;; *) echo 'CI_MAVEN_RETRY_MODE_INVALID' >&2; exit 2;; esac
shift
if (( $# == 0 )); then echo 'CI_MAVEN_RETRY_COMMAND_REQUIRED' >&2; exit 2; fi
umask 077
log="$(mktemp "$RUNNER_TEMP/prp-maven-build.XXXXXX")"
trap 'rm -f -- "$log"' EXIT
# Only explicit transport/bootstrap markers permit retry. A generic POM
# error can mean a nonexistent artifact or invalid configuration.
for attempt in 1 2 3; do
  if "$@" >"$log" 2>&1; then
    echo "${mode}_DIAG_MAVEN_BUILD_SUCCESS_ATTEMPT=$attempt"
    exit 0
  else
    status=$?
  fi
  diagnostic=UNKNOWN
  retryable=false
  # Hard failures take precedence over incidental transport text.
  if grep -Eiq 'checksum (mismatch|validation failed|failure)|invalid checksum|PKIX path building failed|certificate verify failed|SSLHandshakeException' "$log"; then
    diagnostic=INTEGRITY_OR_TLS
  elif grep -Eiq 'No space left on device|Disk quota exceeded' "$log"; then
    diagnostic=RUNNER_DISK_SPACE
  elif grep -Eiq 'OutOfMemoryError|Java heap space|Cannot allocate memory|Killed process' "$log"; then
    diagnostic=MEMORY_OR_PROCESS
  elif grep -Eiq 'COMPILATION ERROR|Compilation failure|cannot find symbol|package .* does not exist|Tests run:.*(Failures: [1-9]|Errors: [1-9])' "$log"; then
    diagnostic=JAVA_COMPILATION_OR_TEST
  elif grep -Eiq 'Permission denied|No such file or directory|cannot execute|status code: (401|403|404)' "$log"; then
    diagnostic=LAUNCH_OR_FILESYSTEM
  elif [[ "$mode" == E2E ]] && grep -Eq '(wget|curl): Failed to fetch .*apache-maven-[0-9.]+-bin.zip' "$log"; then
    diagnostic=WRAPPER_DOWNLOAD
    retryable=true
  elif grep -Eiq 'Could not transfer artifact|Could not resolve dependencies|Non-resolvable parent POM' "$log"; then
    diagnostic=DEPENDENCY_OR_NETWORK
    if grep -Eiq 'status code: 429|Too Many Requests|UnknownHostException|Connection timed out|Read timed out|Connection reset|Name or service not known' "$log"; then
      retryable=true
    fi
  fi
  if [[ "$retryable" == true && "$attempt" -lt 3 ]]; then
    echo "${mode}_DIAG_MAVEN_RETRY_CATEGORY=$diagnostic ATTEMPT=$attempt" >&2
    # 8s then 20s, no source/version changes and no unbounded retry.
    if [[ "$attempt" == 1 ]]; then sleep 8; else sleep 20; fi
    continue
  fi
  echo "${mode}_DIAG_MAVEN_BUILD_CATEGORY=$diagnostic" >&2
  echo 'CI_MAVEN_BUILD_FAILED' >&2
  exit "$status"
done
