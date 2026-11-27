#!/bin/bash
# Only supported action is read-only plan, on target or disposable CI.
set -euo pipefail
umask 077
[[ $(id -u) = 0 ]] || { echo ROOT_REQUIRED; exit 2; }
here=$(cd -- "$(dirname -- "$0")" && pwd)
mode=${1:-plan}
[[ $# -le 1 && ( $mode = plan || $mode = ci ) ]] || exit 2
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
if [[ $mode = plan ]]; then
  . /etc/os-release
  [[ $ID = debian && $VERSION_ID = 13 ]]
  base=/opt/matrix-prp-remote-executor-v11
  cfg=/etc/matrix-prp-remote-executor-v11
  [[ $(cat "$base/.p72-prepared") = f24896eca0d2016e843b919fbcc7ef6f45521cab ]]
  (cd "$base/src"; printf '%s\n' \
    '2dbc71f0e08133f7d96d2dcde1f98091689fd8c4fe98fc556b70e0d3c3f6c379  protocol.py' \
    'a18bc246e6050e97a0b9e3d2d9c459b7d595cb62c04a04d765e6448919fc4b35  executor.py' \
    '9c41fe75a5a7766507a7a5659e26404668ebfccc133e409f7abd0048e0c5aa88  bridge.py' | sha256sum -c -)
  for path in "$cfg"/{receiver.enabled,worker.enabled,sandbox.enabled,issue,recipient.crt,recipient.key,signer.crt,signer.key,authorized_keys} \
      /etc/matrix-prp-chat-shell/execution.enabled /run/prp-remote-v11-handoff \
      /usr/local/libexec/prp-rex-v11-login; do
    [[ ! -e "$path" && ! -L "$path" ]] || { echo PREEXISTING_CONFIG_OR_GATE; exit 2; }
  done
  for unit in prp-remote-executor-v11.service prp-remote-v11-handoff.service; do
    [[ $(systemctl show "$unit" -p LoadState --value) = not-found ]] || { echo UNIT_ALREADY_PRESENT; exit 2; }
  done
  for user in prp-remote-v11 prp-remote-worker-v11; do
    [[ $(id -u "$user") != 0 && $(id -G "$user") = $(id -g "$user") ]]
    [[ $(getent passwd "$user" | cut -d: -f7) = /usr/sbin/nologin ]]
    [[ $(passwd -S "$user" | awk '{print $2}') = L ]]
  done
  [[ $(id -u prp-remote-v11) != $(id -u prp-remote-worker-v11) ]]
  [[ $(id -g prp-remote-v11) != $(id -g prp-remote-worker-v11) ]]
  if findmnt -rn -o TARGET | awk -v p="$base/rootfs" '$0==p || index($0,p"/")==1 {f=1} END{exit !f}'; then
    echo ROOTFS_MOUNT_PRESENT; exit 2
  fi
  dpkg-query --admindir="$base/rootfs/var/lib/dpkg" -W -f='${Package}\t${Version}\n' > "$work/rootfs.tsv"
  cmp -s "$work/rootfs.tsv" "$base/rootfs-packages.tsv"
  echo TARGET_SOURCE_IDENTITIES_ROOTFS_AND_GATES=PASS
  # Exact live config copied to a temporary file; no sshd reload or writes to /etc.
  cp /etc/ssh/sshd_config "$work/base"
else
  # No real keys: test fixture isolated from the target and never used to listen.
  [[ ${GITHUB_ACTIONS:-} = true && ${RUNNER_ENVIRONMENT:-} = github-hosted &&
      ${GITHUB_EVENT_NAME:-} = pull_request && ${GITHUB_REPOSITORY:-} = micor-cjj-spec/matrix-prp ]]
  test -x /usr/sbin/sshd
  install -d -m 0755 /run/sshd
  ssh-keygen -q -t ed25519 -N '' -f "$work/synthetic_host_key"
  printf '%s\n' "HostKey $work/synthetic_host_key" 'UsePAM yes' 'StrictModes yes' 'PermitUserEnvironment no' 'AcceptEnv LANG LC_* COLORTERM NO_COLOR' > "$work/base"
fi
{ cat "$work/base"; printf '\n'; cat "$here/sshd-match.conf.review"; } > "$work/candidate"
python3 -I "$here/verify.py" "$work/base" "$work/candidate"
for unit in prp-remote-executor-v11.service prp-remote-v11-handoff.service; do
  cp "$here/$unit.review" "$work/$unit"
done
systemd-analyze verify --man=no "$work/prp-remote-executor-v11.service" "$work/prp-remote-v11-handoff.service"
echo UNIT_TEMPLATE_PAIR=PASS
echo P73C_PLAN_ONLY=PASS
echo SSH_RELOAD=FALSE
echo SERVICE_STARTED=FALSE
echo ACTIVATION=BLOCKED
