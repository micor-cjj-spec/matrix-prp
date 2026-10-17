#!/bin/sh
# Installed root-owned. This SSH key cannot open a shell, forward ports or use SFTP.
set -eu
case "${SSH_ORIGINAL_COMMAND:-}" in
  controller-sha256) exec /usr/bin/sha256sum /usr/local/sbin/prp-release ;;
  # Optional read-only diagnostic; available only after independent root approval.
  # The helper reads exactly one fixed root-only file and emits allowlisted JSON.
  diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;
  deploy|status|check) exec sudo -n /usr/local/sbin/prp-release "$SSH_ORIGINAL_COMMAND" ;;
  rollback\ *)
    release=${SSH_ORIGINAL_COMMAND#rollback }
    case "$release" in ''|*[!a-zA-Z0-9._-]*) echo 'Invalid release ID' >&2; exit 2;; esac
    exec sudo -n /usr/local/sbin/prp-release rollback "$release"
    ;;
  *) echo 'Allowed: deploy, status, check, controller-sha256, diagnose, rollback RELEASE_ID' >&2; exit 2 ;;
esac
