import json
import os
import struct
import subprocess
import sys
import unittest

import probe_sftp_init as sftp

VERSION = struct.pack(">IBI", 5, 2, 3)
ACCEPTED = b"debug2: subsystem request accepted on channel 0\n"
REJECTED = b"subsystem request failed on channel 0\n"
GATEWAY = b"Allowed: deploy, status, check, rollback RELEASE_ID\n"


class SFTPClassificationTests(unittest.TestCase):
    def test_init_is_exactly_one_initialization_packet(self):
        self.assertEqual(sftp.INIT, b"\x00\x00\x00\x05\x01\x00\x00\x00\x03")

    def test_complete_version_response_including_extensions(self):
        extension = struct.pack(">I", 3)+b"key"+struct.pack(">I", 5)+b"value"
        packet = struct.pack(">I", 5+len(extension))+VERSION[4:]+extension
        self.assertEqual(sftp.version_packet(packet), 3)
        for data in [VERSION[:3], VERSION[:8], b"\xff\xff\xff\xff", sftp.INIT,
                     struct.pack(">IBI", 9, 2, 3)+struct.pack(">I", 0)]:
            self.assertIsNone(sftp.version_packet(data))

    def test_version_always_proves_access_even_if_denial_markers_coexist(self):
        for code in [0, 2, 255, None]:
            result = sftp.classify(VERSION, GATEWAY+REJECTED, code)
            self.assertEqual(result["category"], "SFTP_ACCESSIBLE")
            self.assertTrue(result["version_response"])

    def test_explicit_protocol_and_gateway_rejection(self):
        self.assertEqual(sftp.classify(b"", REJECTED, 255)["category"], "SSH_PROTOCOL_REJECTED")
        self.assertEqual(sftp.classify(b"", GATEWAY, 2)["category"], "GATEWAY_REJECTED")
        for out, err, code in [(b"", REJECTED, 2), (b"payload", REJECTED, 255),
                               (b"", REJECTED+ACCEPTED, 255), (b"", b"", 2)]:
            self.assertNotIn(sftp.classify(out, err, code)["category"],
                             {"SSH_PROTOCOL_REJECTED", "GATEWAY_REJECTED"})

    def test_transport_error_never_becomes_rejection(self):
        for marker, category in [(b"Permission denied (publickey).", "AUTHENTICATION_ERROR"),
                                 (b"Host key verification failed.", "HOST_KEY_ERROR"),
                                 (b"Connection reset by peer", "NETWORK_ERROR")]:
            result = sftp.classify(b"", marker+REJECTED+GATEWAY, 255)
            self.assertEqual(result["category"], category)
        self.assertEqual(sftp.classify(b"", REJECTED, 255, timed_out=True)["category"], "TIMEOUT")
        self.assertEqual(sftp.classify(b"", REJECTED, 255, limited=True)["category"], "OUTPUT_LIMIT")

    def test_eof_startup_failure_and_abnormal_exit_remain_unaccepted(self):
        self.assertEqual(sftp.classify(b"", b"", 0, stdout_eof=True)["category"], "EOF_WITHOUT_VERSION")
        self.assertEqual(sftp.classify(b"", ACCEPTED, 2)["category"], "SUBSYSTEM_EXITED_WITHOUT_VERSION")
        self.assertEqual(sftp.classify(b"", b"subsystem not found", 255)["category"], "SUBSYSTEM_STARTUP_FAILED")
        self.assertEqual(sftp.classify(b"", b"unknown failure", 2)["category"], "UNKNOWN_ERROR")

    def test_only_metadata_leaves_classifier(self):
        secret = b"PRIVATE_TOKEN_PERSONAL_DATA"
        result = sftp.classify(secret, secret+ACCEPTED, 2)
        encoded = json.dumps(result)
        self.assertNotIn(secret.decode(), encoded)
        self.assertEqual(result["stderr_bytes"], len(secret+ACCEPTED))
        self.assertFalse(result["stderr_empty"])


@unittest.skipIf(os.name == "nt", "Pipe selectors run on the Linux Actions runner")
class BoundedExchangeTests(unittest.TestCase):
    def run_child(self, script, timeout=3):
        return sftp.exchange([sys.executable, "-c", script], timeout=timeout)

    def test_devnull_eof_can_hide_a_working_sftp_server(self):
        script = "import sys; data=sys.stdin.buffer.read(9); sys.exit(2) if not data else None; sys.stdout.buffer.write(bytes.fromhex('000000050200000003')); sys.stdout.buffer.flush(); sys.stdin.buffer.read(1)"
        old = subprocess.run([sys.executable, "-c", script], stdin=subprocess.DEVNULL,
                             capture_output=True, timeout=3)
        self.assertEqual((old.returncode, old.stdout), (2, b""))
        new = self.run_child(script)
        self.assertEqual(new["category"], "SFTP_ACCESSIBLE")
        self.assertTrue(new["stdin_held_open"])
        self.assertTrue(new["stopped_after_version"])

    def test_only_init_sent_and_open_stdin_does_not_deliver_eof(self):
        result = self.run_child("import sys; d=sys.stdin.buffer.read(9); assert d==bytes.fromhex('000000050100000003'); sys.stdin.buffer.read(1)", timeout=0.5)
        self.assertEqual(result["category"], "TIMEOUT")
        self.assertTrue(result["init_sent"])
        self.assertIsNone(result["exit_code"])

    def test_eof_without_version_is_not_rejection(self):
        result = self.run_child("import sys; sys.stdin.buffer.read(9)")
        self.assertEqual(result["category"], "EOF_WITHOUT_VERSION")
        self.assertFalse(result["version_response"])

    def test_stdout_and_stderr_are_bounded_before_process_completion(self):
        for stream, limit, key in [("stdout", sftp.MAX_STDOUT, "stdout_bytes"),
                                   ("stderr", sftp.MAX_STDERR, "stderr_bytes")]:
            result = self.run_child("import sys,time; sys.stdin.buffer.read(9); sys."+stream+".buffer.write(b'X'*1000000); sys."+stream+".buffer.flush(); time.sleep(10)")
            self.assertEqual(result["category"], "OUTPUT_LIMIT")
            self.assertLessEqual(result[key], limit)


if __name__ == "__main__":
    unittest.main()
