#!/usr/bin/env python3
"""Zero-secret tests for a metadata-only, permanently non-authorizing inventory."""
import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("b2_evidence_inventory.py")
spec = importlib.util.spec_from_file_location("b2_evidence_inventory", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EvidenceInventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.guard = Path(self.temp.name) / "host-guard"
        self.guard.mkdir(mode=0o700)
        self.guard.chmod(0o700)
        self.dump = Path(self.temp.name) / "restore.dump"
        self.dump.write_bytes(b"fake test marker; not a backup")
        self.dump.chmod(0o600)

    def fixture(self, filename):
        file = self.guard / filename
        file.write_bytes(b"not valid approval content; INVENTORY MUST NOT READ THIS")
        file.chmod(0o600)
        return file

    def inspect(self):
        return mod.examine(self.guard, self.dump, trusted_uid=os.getuid())

    def test_missing_receipts_cannot_authorize(self):
        evidence = self.inspect()
        self.assertEqual(evidence["requirements"]["approved_install"], "MISSING")
        self.assertEqual(evidence["requirements"]["fresh_b2_restore"], "MISSING")
        self.assertFalse(evidence["deployment_permitted"])
        self.assertEqual(evidence["b2_authorization"], "BLOCKED_UNTIL_INDEPENDENT_REVIEW")

    def test_presence_is_never_approval_even_for_forged_content(self):
        for filename in mod.REQUIRED.values():
            self.fixture(filename)
        before = sorted(self.guard.iterdir())
        result = self.inspect()
        self.assertEqual(result["requirements"]["approved_install"],
                         "PRESENT_METADATA_ONLY_UNVERIFIED")
        self.assertEqual(result["requirements"]["fresh_b2_restore"],
                         "PRESENT_METADATA_ONLY_UNVERIFIED")
        self.assertFalse(result["deployment_permitted"])
        self.assertEqual(before, sorted(self.guard.iterdir()))
        self.assertNotIn("not valid approval content", str(result))

    def test_symlink_and_broad_permissions_cannot_pass(self):
        approval = self.fixture(mod.REQUIRED["approved_install"])
        approval.chmod(0o644)
        self.assertEqual(self.inspect()["requirements"]["approved_install"],
                         "WEAK_FILE_PERMISSIONS")
        approval.unlink()
        approval.symlink_to(self.dump)
        self.assertEqual(self.inspect()["requirements"]["approved_install"],
                         "UNSAFE_NONREGULAR_OR_SYMLINK")

    def test_nonregular_parent_blocks_receipt_inspection(self):
        self.guard.rmdir()
        self.guard.symlink_to(self.dump)
        self.assertEqual(self.inspect()["host_guard_directory"], "UNSAFE_PATH")
        self.assertEqual(self.inspect()["requirements"]["approved_install"],
                         "NOT_INSPECTED_UNSAFE_PARENT")

    def test_weak_parent_blocks_receipt_inspection(self):
        self.guard.chmod(0o777)
        result = self.inspect()
        self.assertEqual(result["host_guard_directory"], "UNSAFE_OWNER_OR_PERMISSIONS")
        self.assertFalse(result["deployment_permitted"])

    def test_inventory_never_reads_file_contents(self):
        evidence = self.fixture(mod.REQUIRED["approved_install"])
        # If this were parsed, it would be invalid JSON; metadata-only succeeds.
        self.assertEqual(self.inspect()["requirements"]["approved_install"],
                         "PRESENT_METADATA_ONLY_UNVERIFIED")
        self.assertEqual(evidence.read_bytes(),
                         b"not valid approval content; INVENTORY MUST NOT READ THIS")


if __name__ == "__main__":
    unittest.main()
