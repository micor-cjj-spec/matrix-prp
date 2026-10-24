"""Actual temporary-file replacement and fault recovery; no server access."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import upgrade_candidate_helpers as helper

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.backup=self.root/'backup'
        self.sources={name:b'new_value=2\n' for name in helper.ALLOWED}
        self.changes={name:{'before':hashlib.sha256(b'old_value=1\n').hexdigest(),'after':hashlib.sha256(raw).hexdigest()} for name,raw in self.sources.items()}
        for name in helper.ALLOWED:(self.root/name).write_bytes(b'old_value=1\n')
    def old(self):return all(helper.sha(self.root/n)==c['before'] for n,c in self.changes.items())
    def test_success_and_explicit_restore(self):
        result=helper.upgrade(self.root,self.backup,self.changes,self.sources,lambda:None)
        self.assertEqual(result['files_changed'],4)
        helper.restore(self.root,self.backup,self.changes);self.assertTrue(self.old())
    def test_failed_acceptance_restores_every_old_byte(self):
        def fail():raise RuntimeError('injected check failure')
        with self.assertRaises(RuntimeError):helper.upgrade(self.root,self.backup,self.changes,self.sources,fail)
        self.assertTrue(self.old())
    def test_partial_replacement_failure_restores_old_bytes(self):
        replace=helper.os.replace;calls=0
        def fail_once(*args):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('injected replace failure')
            return replace(*args)
        with patch.object(helper.os,'replace',side_effect=fail_once):
            with self.assertRaises(OSError):helper.upgrade(self.root,self.backup,self.changes,self.sources,lambda:None)
        self.assertTrue(self.old());self.assertFalse(list(self.root.glob('*.helper-upgrade-pending')))
    def test_unknown_target_state_blocks_before_backup(self):
        (self.root/next(iter(helper.ALLOWED))).write_bytes(b'unknown')
        with self.assertRaises(AssertionError):helper.upgrade(self.root,self.backup,self.changes,self.sources,lambda:None)
        self.assertFalse(self.backup.exists())
    def test_unapproved_file_never_written(self):
        self.sources['guard_release_engine.py']=b'unsafe=1'
        with self.assertRaises(AssertionError):helper.upgrade(self.root,self.backup,self.changes,self.sources,lambda:None)
        self.assertTrue(self.old());self.assertFalse(self.backup.exists())

if __name__=='__main__':unittest.main()
