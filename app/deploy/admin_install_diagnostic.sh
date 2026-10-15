#!/usr/bin/env bash
# Administrator-only installation. Does not replace the production controller.
set -Eeuo pipefail
umask 077
if [[ $# != 2 || ( "$1" != "--check" && "$1" != "--apply" ) ]]; then
  echo "Usage: sudo bash app/deploy/admin_install_diagnostic.sh --check|--apply /absolute/installed/gateway" >&2
  exit 2
fi
mode="$1"; gateway="$2"
[[ "$EUID" == 0 && "$gateway" == /* && -f "$gateway" && ! -L "$gateway" ]] || exit 2
[[ "$(stat -c '%u:%g' "$gateway")" == "0:0" ]] || exit 2
[[ "$(stat -c '%a' "$gateway")" =~ ^(700|750|755)$ ]] || exit 2
here="$(cd -- "$(dirname -- "$0")" && pwd)"
controller=/usr/local/sbin/prp-release
helper="$here/read_only_diagnostic.py"
manifest="$here/controller-manifest.json"
target=/usr/local/sbin/prp-diagnose
sudoers=/etc/sudoers.d/90-prp-diagnose
expected="$(python3 - "$manifest" <<'PY'
import json,sys
a=json.load(open(sys.argv[1],encoding='utf8'))['approved_controller']
assert a['path']=='/usr/local/sbin/prp-release'
print(a['sha256'])
PY
)"
actual="$(sha256sum "$controller" | cut -d' ' -f1)"
[[ "$expected" == "$actual" ]] || { echo "STOP: unapproved controller hash" >&2; exit 2; }
[[ -f "$helper" && ! -e "$target" && ! -e "$sudoers" ]] || { echo "STOP: missing source or existing diagnostic installation" >&2; exit 2; }
python3 -m py_compile "$helper"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
cp -a -- "$gateway" "$work/gateway.before"
python3 - "$gateway" "$work/gateway.after" <<'PY'
import pathlib,sys
source=pathlib.Path(sys.argv[1]).read_text()
anchor='  controller-sha256) exec /usr/bin/sha256sum /usr/local/sbin/prp-release ;;'
if source.count(anchor)!=1 or 'prp-diagnose' in source or 'diagnose)' in source:
    raise SystemExit('Installed gateway unexpected: review required')
addition='  diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;'
pathlib.Path(sys.argv[2]).write_text(source.replace(anchor,anchor+'\n'+addition))
PY
sh -n "$work/gateway.after"
printf '%s\n' 'prp-deploy ALL=(root) NOPASSWD: /usr/local/sbin/prp-diagnose' > "$work/sudoers"
chmod 440 "$work/sudoers"
visudo -cf "$work/sudoers" >/dev/null
diff -u "$work/gateway.before" "$work/gateway.after" || [[ $? == 1 ]]
echo "Existing production controller: $actual"
echo "Helper SHA256: $(sha256sum "$helper" | cut -d' ' -f1)"
if [[ "$mode" == "--check" ]]; then
  echo "CHECK ONLY: No files modified."
  exit 0
fi
backup="/var/backups/prp-diagnose/$(date -u '+%Y%m%dT%H%M%SZ')"
[[ ! -e "$backup" ]] || exit 2
install -d -o root -g root -m 0700 "$backup"
cp -a "$gateway" "$backup/gateway.original"
echo "$gateway" > "$backup/gateway.path"
chmod 600 "$backup/gateway.path"
done_helper=0; done_sudoers=0; done_gateway=0
rollback() {
  if (( done_gateway )); then cp -a "$backup/gateway.original" "$gateway"; fi
  if (( done_sudoers )); then rm -f "$sudoers"; fi
  if (( done_helper )); then rm -f "$target"; fi
}
trap rollback ERR
install -o root -g root -m 0755 "$helper" "$target"
done_helper=1
install -o root -g root -m 0440 "$work/sudoers" "$sudoers"
done_sudoers=1
visudo -cf "$sudoers" >/dev/null
cp "$work/gateway.after" "$gateway"
chmod --reference="$backup/gateway.original" "$gateway"
chown --reference="$backup/gateway.original" "$gateway"
done_gateway=1
sh -n "$gateway"
[[ "$(sha256sum "$controller" | cut -d' ' -f1)" == "$expected" ]]
"$target" | python3 -c '
import json,sys
r=json.load(sys.stdin)
assert r.get("schema_version")==1
assert r.get("state") in ("available","stale","no_log","unavailable")
assert set(r)=={"schema_version","state","code","stage","table","exception","timestamp_utc"}
'
trap - ERR
echo "INSTALL OK: backup $backup"
echo "Verify gateway through existing restricted SSH identity before deploying."
