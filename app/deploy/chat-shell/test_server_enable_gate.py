"""Host-side default-deny execution switch regression tests (no privileged actions)."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import prp_shell_executor as executor
from protocol import InvalidJob, b64_encode

class HostExecutionGate(unittest.TestCase):
    def test_unit_tests_resolve_checked_out_protocol_not_installed_global_copy(self):
        import protocol
        self.assertEqual(Path(protocol.__file__).resolve().parent,
                         Path(executor.__file__).resolve().parent)
    def test_missing_marker_symlink_wrong_mode_and_content_denied(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            flag=folder/'execution.enabled'
            with self.assertRaises(InvalidJob):
                executor.require_execution_enabled(flag, os.getuid())

            flag.write_bytes(executor.ENABLE_VALUE)
            os.chmod(flag,0o600)
            with self.assertRaises(InvalidJob):
                executor.require_execution_enabled(flag, os.getuid())

            os.chmod(flag,0o400)
            executor.require_execution_enabled(flag, os.getuid())

            link=folder/'link'
            link.symlink_to(flag)
            with self.assertRaises(InvalidJob):
                executor.require_execution_enabled(link, os.getuid())

            os.chmod(flag,0o600)
            flag.write_bytes(b'WRONG_ENABLE_VALUE\n')
            os.chmod(flag,0o400)
            with self.assertRaises(InvalidJob):
                executor.require_execution_enabled(flag, os.getuid())

            with self.assertRaises(InvalidJob):
                executor.require_execution_enabled(flag, os.getuid()+1)

    def test_disabled_rejects_before_replay_claim_or_shell_execution(self):
        request={'jobId':'test-job','ciphertext':b64_encode(b'test-ciphertext')}
        with (mock.patch.object(executor,'openssl_cms_decrypt',return_value=b'{}'),
              mock.patch.object(executor,'validate_payload',return_value={'jobId':'test-job'}),
              mock.patch.object(executor,'require_execution_enabled',side_effect=InvalidJob('disabled')),
              mock.patch.object(executor,'claim') as claim,
              mock.patch.object(executor,'execute') as execute):
            with self.assertRaises(InvalidJob):
                executor.process_request(request,None)
            claim.assert_not_called()
            execute.assert_not_called()

if __name__=='__main__':
    unittest.main()
