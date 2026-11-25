import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_snapshot import SharedSnapshotWriter, SharedSnapshotReader
from snapshot_contract import unavailable
from test_snapshot_contract import NOW, sample

class SharedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)
        self.uid=os.geteuid()
        self.gid=os.getegid()
        os.chmod(self.directory,0o2750)
        self.writer=SharedSnapshotWriter(self.directory,self.uid,self.gid)
        self.reader=SharedSnapshotReader(self.directory,self.uid,self.gid)

    def as_reader(self):
        return (patch("shared_snapshot.os.geteuid",return_value=self.uid+10000),
                patch("shared_snapshot.os.getegid",return_value=self.gid),
                patch("shared_snapshot.os.getgroups",return_value=[self.gid]))

    def test_writer_creates_group_readonly_snapshot(self):
        self.writer.write(sample())
        info=(self.directory/"status.json").stat()
        self.assertEqual(info.st_uid,self.uid)
        self.assertEqual(info.st_gid,self.gid)
        self.assertEqual(stat.S_IMODE(info.st_mode),0o640)
        self.assertEqual(info.st_nlink,1)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode),0o2750)

    def test_separate_reader_identity_reads_snapshot(self):
        self.writer.write(sample())
        patches=self.as_reader()
        with patches[0],patches[1],patches[2]:
            result=self.reader.read(NOW)
        self.assertEqual(result["status"],"fresh")
        self.assertEqual(result["disk"]["totalBytes"],102400)

    def test_reader_has_no_write_surface(self):
        self.assertFalse(hasattr(self.reader,"write"))
        self.assertFalse(hasattr(self.writer,"read_raw"))

    def test_writer_rejects_wrong_uid(self):
        with patch("shared_snapshot.os.geteuid",return_value=self.uid+1):
            with self.assertRaises(PermissionError):
                self.writer.write(sample())

    def test_reader_rejects_writer_uid_and_missing_group(self):
        with patch("shared_snapshot.os.geteuid",return_value=self.uid),patch("shared_snapshot.os.getgroups",return_value=[self.gid]):
            self.assertEqual(self.reader.read(NOW),unavailable())
        with patch("shared_snapshot.os.geteuid",return_value=self.uid+1),patch("shared_snapshot.os.getegid",return_value=self.gid+1),patch("shared_snapshot.os.getgroups",return_value=[]):
            self.assertEqual(self.reader.read(NOW),unavailable())

    def test_reader_rejects_wrong_directory_owner_group_or_mode(self):
        self.writer.write(sample())
        original=os.stat(self.directory)
        cases=[(self.uid+1,self.gid,0o2750),(self.uid,self.gid+1,0o2750),(self.uid,self.gid,0o2770),(self.uid,self.gid,0o750)]
        for uid,gid,mode in cases:
            with self.subTest(uid=uid,gid=gid,mode=oct(mode)):
                # The real filesystem metadata cannot be forged without privilege;
                # exercise the exact verifier with a patched fstat result.
                with patch("shared_snapshot.os.fstat",side_effect=lambda fd, u=uid,g=gid, m=mode: type("S",(),{"st_mode":stat.S_IFDIR|m,"st_uid":u,"st_gid":g})()):
                    with self.assertRaises(PermissionError):
                        from shared_snapshot import _open_directory
                        _open_directory(self.directory,self.uid,self.gid)

    def test_reader_rejects_symlink_hardlink_and_fifo(self):
        self.writer.write(sample())
        target=self.directory/"other"
        target.write_bytes((self.directory/"status.json").read_bytes())
        target.chmod(0o640)
        (self.directory/"status.json").unlink()
        (self.directory/"status.json").symlink_to(target)
        patches=self.as_reader()
        with patches[0],patches[1],patches[2]:
            self.assertEqual(self.reader.read(NOW),unavailable())
        (self.directory/"status.json").unlink()
        os.link(target,self.directory/"status.json")
        patches=self.as_reader()
        with patches[0],patches[1],patches[2]:
            self.assertEqual(self.reader.read(NOW),unavailable())
        (self.directory/"status.json").unlink()
        os.mkfifo(self.directory/"status.json",0o640)
        patches=self.as_reader()
        with patches[0],patches[1],patches[2]:
            self.assertEqual(self.reader.read(NOW),unavailable())

    def test_bad_file_mode_and_group_are_denied(self):
        self.writer.write(sample())
        path=self.directory/"status.json"
        patches=self.as_reader()
        path.chmod(0o644)
        with patches[0],patches[1],patches[2]:
            self.assertEqual(self.reader.read(NOW),unavailable())
        path.chmod(0o640)
        with patch("shared_snapshot.os.geteuid",return_value=self.uid+1),patch("shared_snapshot.os.getegid",return_value=self.gid),patch("shared_snapshot.os.getgroups",return_value=[self.gid]),patch("shared_snapshot.os.fstat",side_effect=lambda fd: type("S",(),{"st_mode":stat.S_IFREG|0o640,"st_uid":self.uid,"st_gid":self.gid+1,"st_nlink":1,"st_size":100})()):
            self.assertEqual(self.reader.read(NOW),unavailable())
