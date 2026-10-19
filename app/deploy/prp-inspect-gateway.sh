#!/bin/sh
# Dedicated prp-inspect ONLY. Must be installed root:root 0755.
# SSH authorized_keys must contain restrict,command="/usr/local/bin/prp-inspect-gateway".
# No shell, client-supplied paths/flags, SFTP, or sudo argument passthrough.
set -eu
umask 077
case "${SSH_ORIGINAL_COMMAND-}" in
    report) exec /usr/bin/sudo -n /usr/local/sbin/prp-inspect-report ;;
    *) exit 2 ;;
esac
