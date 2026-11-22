#!/bin/sh
# Root-owned forced-command gateway, installed only after separate review.
set -eu
case "${SSH_ORIGINAL_COMMAND-}" in
  run) exec sudo -n /usr/local/sbin/prp-chat-shell-executor ;;
  *) echo PRP_SHELL_GATEWAY_REJECTED >&2; exit 2 ;;
esac
