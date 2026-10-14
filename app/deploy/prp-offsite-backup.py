#!/usr/bin/env python3
"""Opt-in, encrypted off-host PRP backups. Never invoked by the release SSH gateway."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

STATE = Path("/var/lib/matrix-prp-backup")
CONFIG = Path("/etc/matrix-prp")
NGINX = Path("/etc/nginx/snippets/matrix-prp.conf")
MEDIA = Path("/srv/matrix-prp/video/media")
KNOWLEDGE = Path("/srv/matrix-prp/knowledge")
DOCKER = ["docker", "exec", "matrix-mysql", "sh", "-c"]
MYSQL_DUMP = (
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump '
    '--default-character-set=utf8mb4 -uroot --single-transaction '
    '--quick --routines --triggers --events --no-tablespaces matrix_prp'
)
MYSQL_VERSION = (
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B matrix_prp '
    '-e "SELECT version FROM flyway_schema_history WHERE success=1 '
    'AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1"'
)

def fail(message):
    raise RuntimeError(message)

def validate_repository(value):
    # Intentionally reject local / relative backends: they share the host failure domain.
    if not value.startswith("s3:https://"):
        fail("Only an HTTPS S3-compatible off-host restic repository is allowed")
    parsed = urlsplit(value[3:])
    if not parsed.hostname or not parsed.path.strip("/"):
        fail("Remote repository endpoint and bucket are required")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        fail("Do not put credentials or query parameters in the repository URL")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        fail("Loopback S3 endpoints are not off-host backups")

def validate_alert_url(value):
    if not value:
        fail("A production failure-alert webhook is required before enabling the timer")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        fail("Alert endpoint must be a credential-free HTTPS hostname")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        fail("Loopback alert endpoints cannot notify an off-host operator")

def alert_failure():
    url = os.environ.get("PRP_BACKUP_ALERT_WEBHOOK_URL", "")
    validate_alert_url(url)
    body = json.dumps({
        "text": "CRITICAL: Matrix PRP encrypted off-host backup failed. Inspect systemctl status prp-offsite-backup.service and its root-only journal.",
        "service": "matrix-prp-offsite-backup",
        "severity": "critical"
    }).encode()
    request = Request(url, body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            fail("Backup failure notification was not accepted")
    print("PRP failure alert delivered")

def preflight():
    if os.geteuid() != 0:
        fail("Run the backup as root via the dedicated systemd service")
    validate_repository(os.environ.get("RESTIC_REPOSITORY", ""))
    validate_alert_url(os.environ.get("PRP_BACKUP_ALERT_WEBHOOK_URL", ""))
    password = Path(os.environ.get("RESTIC_PASSWORD_FILE", ""))
    if not password.is_absolute() or not password.is_file() or password.is_symlink():
        fail("RESTIC_PASSWORD_FILE must name a real root-owned local file")
    mode = password.stat()
    if mode.st_uid != 0 or stat.S_IMODE(mode.st_mode) & 0o077:
        fail("The restic password file must be owned by root and inaccessible to others")
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        fail("Dedicated S3 access credentials are required")
    for path in (CONFIG / "application.yml", NGINX, MEDIA):
        if not path.exists():
            fail("Required backup source is missing: " + str(path))
    # Fail closed if the repo is absent / inaccessible: initialization is an admin action.
    subprocess.run(["restic", "snapshots", "--json"], check=True, stdout=subprocess.DEVNULL)

def file_digest(path):
    hash_ = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hash_.update(chunk)
    return hash_.hexdigest()

def inventory(root):
    if not root.is_dir():
        fail("Video media directory is missing")
    files = sorted(p for p in root.rglob("*.mp4") if p.is_file())
    # File identities and sizes detect replaced/missing assets even if total bytes stay equal.
    digest = hashlib.sha256()
    total = 0
    for path in files:
        size = path.stat().st_size
        total += size
        digest.update((path.relative_to(root).as_posix() + "\\t" + str(size) + "\\n").encode())
    return (len(files), total, digest.hexdigest())

def schema_version():
    version = subprocess.check_output(DOCKER + [MYSQL_VERSION], text=True).strip()
    if not re.fullmatch(r"[0-9]{1,4}", version):
        fail("Cannot verify the live Flyway schema version")
    return int(version)

def backup():
    preflight()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / "backup.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="backup-", dir=STATE) as stage_name:
            stage = Path(stage_name)
            stage.chmod(0o700)
            before = inventory(MEDIA)
            dump = stage / "matrix_prp.sql"
            with dump.open("wb") as file:
                subprocess.run(DOCKER + [MYSQL_DUMP], stdout=file, check=True)
            dump.chmod(0o600)
            if dump.stat().st_size == 0:
                fail("Empty MySQL dump; refusing to back up")
            meta = {
                "format_version": 1,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "schema_version": schema_version(),
                "database_sha256": file_digest(dump),
                "database_bytes": dump.stat().st_size,
                "media_files": before[0],
                "media_bytes": before[1],
                "media_inventory_sha256": before[2],
            }
            (stage / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n")
            paths = [str(stage), str(CONFIG), str(NGINX), str(MEDIA)]
            if KNOWLEDGE.is_dir():
                paths.append(str(KNOWLEDGE))
            # The Restic encryption key and S3 credentials must not be stored in
            # the same encrypted repository they unlock. Keep them in an independent vault.
            subprocess.run([
                "restic", "backup", "--tag", "matrix-prp",
                "--exclude", str(CONFIG / "restic-password"),
                "--exclude", os.environ.get("RESTIC_PASSWORD_FILE", str(CONFIG / "restic-password")),
                "--exclude", str(CONFIG / "backup.env"),
                *paths
            ], check=True)
            # Detect media additions/deletions during the non-transactional file snapshot.
            if inventory(MEDIA) != before:
                fail("Media inventory changed during snapshot; retry before accepting as verified")
            subprocess.run(["restic", "check"], check=True)
            print("PRP encrypted remote backup completed and repository metadata verified", flush=True)

def verify_restored(target):
    """Run after 'restic restore' onto an ISOLATED machine, never the production root."""
    target = Path(target).resolve()
    if str(target) == "/" or str(target).startswith("/srv/matrix-prp"):
        fail("Refusing to validate against a production filesystem location")
    manifests = list((target / STATE.relative_to("/")).glob("backup-*/manifest.json"))
    if len(manifests) != 1:
        fail("Expected exactly one restored PRP backup manifest")
    manifest = manifests[0]
    meta = json.loads(manifest.read_text())
    dump = manifest.parent / "matrix_prp.sql"
    if meta.get("format_version") != 1 or not dump.is_file():
        fail("Invalid restored manifest or missing database dump")
    if dump.stat().st_size != meta.get("database_bytes") or file_digest(dump) != meta.get("database_sha256"):
        fail("Restored database dump is missing bytes or does not match SHA256")
    if not isinstance(meta.get("schema_version"), int) or meta["schema_version"] < 7:
        fail("Invalid restored schema version")
    for path in [CONFIG / "application.yml", NGINX]:
        if not (target / path.relative_to("/")).is_file():
            fail("Missing restored configuration: " + str(path))
    restored_media = target / MEDIA.relative_to("/")
    if inventory(restored_media) != (meta.get("media_files"), meta.get("media_bytes"), meta.get("media_inventory_sha256")):
        fail("Restored video inventory does not match snapshot metadata")
    print("Restored files validated (database SHA256, config, video inventory).")
    print("Database import and authenticated API/video tests on an isolated host are still required.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "backup", "verify-restored", "alert-failure"])
    parser.add_argument("--target", help="Restored filesystem root on an isolated validation host")
    args = parser.parse_args()
    if args.action == "alert-failure":
        alert_failure()
    elif args.action == "verify-restored":
        if not args.target:
            parser.error("--target is required for verify-restored")
        verify_restored(args.target)
    else:
        if args.target:
            parser.error("--target is only valid for verify-restored")
        if args.action == "preflight":
            preflight()
            print("PRP remote restic repository and required sources are accessible")
        else:
            backup()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Avoid echoing subprocess/environment details containing passwords into journal.
        print("PRP backup/verification failed: " + type(exc).__name__, file=__import__("sys").stderr)
        raise SystemExit(1)
