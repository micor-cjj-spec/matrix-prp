import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prp_offsite", Path(__file__).with_name("prp-offsite-backup.py"))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class OffsiteBackupTests(unittest.TestCase):
    def test_rejects_nonremote_or_secret_bearing_repository(self):
        for value in ("", "/mnt/backup", "local:/backups", "s3:http://s3.example/bucket",
                      "s3:https://localhost/bucket", "s3:https://user:password@s3.example/bucket",
                      "s3:https://s3.example/bucket?token=secret"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                backup.validate_repository(value)
        backup.validate_repository("s3:https://s3.example.com/private-bucket/prp")
        for value in ("", "http://alerts.example.com/hook", "https://localhost/hook",
                      "https://user:secret@alerts.example.com/hook"):
            with self.subTest(alert=value), self.assertRaises(RuntimeError):
                backup.validate_alert_url(value)
        backup.validate_alert_url("https://alerts.example.com/private/hook")

    def restored_fixture(self, target, *, db=b"CREATE TABLE sample(id INT);", video=b"video bytes"):
        stage = target / "var/lib/matrix-prp-backup/backup-test"
        stage.mkdir(parents=True)
        (stage / "matrix_prp.sql").write_bytes(db)
        meta = {
            "format_version": 1,
            "schema_version": 17,
            "database_bytes": len(db),
            "database_sha256": hashlib.sha256(db).hexdigest(),
            "media_files": 1,
            "media_bytes": len(video),
        }
        (stage / "manifest.json").write_text(json.dumps(meta))
        conf = target / "etc/matrix-prp/application.yml"
        conf.parent.mkdir(parents=True)
        conf.write_text("spring: {}")
        nginx = target / "etc/nginx/snippets/matrix-prp.conf"
        nginx.parent.mkdir(parents=True)
        nginx.write_text("internal;")
        media = target / "srv/matrix-prp/video/media/42"
        media.mkdir(parents=True)
        (media / "test.mp4").write_bytes(video)
        meta["media_inventory_sha256"] = backup.inventory(media.parent)[2]
        (stage / "manifest.json").write_text(json.dumps(meta))
        return stage, media

    def test_restored_snapshot_validates_dump_and_video_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            stage, media = self.restored_fixture(target)
            backup.verify_restored(target)
            (stage / "matrix_prp.sql").write_bytes(b"tampered bytes")
            with self.assertRaisesRegex(RuntimeError, "SHA256|missing bytes"):
                backup.verify_restored(target)
            (stage / "matrix_prp.sql").write_bytes(b"CREATE TABLE sample(id INT);")
            # Name swap with identical byte size must also be detected.
            (media / "test.mp4").rename(media / "renamed.mp4")
            with self.assertRaisesRegex(RuntimeError, "inventory"):
                backup.verify_restored(target)
            (media / "renamed.mp4").unlink()
            with self.assertRaisesRegex(RuntimeError, "inventory"):
                backup.verify_restored(target)

    def test_backup_encrypts_remote_data_without_publishing_sql_to_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            config = root / "etc/matrix-prp"
            config.mkdir(parents=True)
            (config / "application.yml").write_text("dummy")
            nginx = root / "etc/nginx.conf"
            nginx.write_text("internal;")
            media = root / "videos"
            media.mkdir()
            (media / "a.mp4").write_bytes(b"immutable media")
            commands = []
            def fake_run(args, **kwargs):
                commands.append(args)
                if args[:2] == backup.DOCKER[:2]:
                    kwargs["stdout"].write(b"-- private database snapshot --")
                return None
            with patch.object(backup, "STATE", state), patch.object(backup, "CONFIG", config), \
                 patch.object(backup, "NGINX", nginx), patch.object(backup, "MEDIA", media), \
                 patch.object(backup, "KNOWLEDGE", root / "missing"), \
                 patch.object(backup, "preflight", return_value=None), \
                 patch.dict(backup.os.environ, {"RESTIC_PASSWORD_FILE": str(config / "custom-unlock.key")}), \
                 patch.object(backup.subprocess, "run", side_effect=fake_run), \
                 patch.object(backup.subprocess, "check_output", return_value="17"):
                backup.backup()
            self.assertEqual(commands[-2][0:2], ["restic", "backup"])
            self.assertIn(str(config / "restic-password"), commands[-2])
            self.assertIn(str(config / "custom-unlock.key"), commands[-2])
            self.assertIn(str(config / "backup.env"), commands[-2])
            self.assertEqual(commands[-1], ["restic", "check"])
            self.assertFalse(list(state.glob("backup-*/matrix_prp.sql")))
            self.assertNotIn("private database snapshot", repr(commands))

    def test_changed_media_during_backup_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "videos"
            media.mkdir()
            (media / "a.mp4").write_bytes(b"a")
            def fake_run(args, **kwargs):
                if args[0] == "docker":
                    kwargs["stdout"].write(b"-- SQL --")
                elif args[:2] == ["restic", "backup"]:
                    (media / "b.mp4").write_bytes(b"unexpected upload")
                return None
            with patch.object(backup, "STATE", root / "state"), \
                 patch.object(backup, "CONFIG", root), patch.object(backup, "NGINX", root / "nginx"), \
                 patch.object(backup, "MEDIA", media), patch.object(backup, "KNOWLEDGE", root / "absent"), \
                 patch.object(backup, "preflight", return_value=None), \
                 patch.object(backup.subprocess, "run", side_effect=fake_run), \
                 patch.object(backup.subprocess, "check_output", return_value="17"):
                with self.assertRaisesRegex(RuntimeError, "changed during snapshot"):
                    backup.backup()


if __name__ == "__main__":
    unittest.main()
