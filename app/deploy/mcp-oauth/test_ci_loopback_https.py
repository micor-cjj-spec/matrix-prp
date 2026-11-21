"""No external network: verify the disposable PKCE driver preserves TLS identity."""
import unittest
from unittest.mock import Mock, patch

import ci_pkce_browser as driver


class LoopbackHTTPSConnectionTests(unittest.TestCase):
    def test_local_ipv4_transport_keeps_original_tls_server_hostname(self):
        for host in ("auth-e2e.localhost", "prp-e2e.localhost"):
            with self.subTest(host=host), patch.object(driver.socket, "create_connection") as dial:
                context = Mock()
                conn = driver.LoopbackHTTPSConnection(host, context=context)
                conn.connect()
                self.assertEqual(dial.call_args.args[0], ("127.0.0.1", 443))
                context.wrap_socket.assert_called_once_with(
                    dial.return_value, server_hostname=host)

    def test_external_hostname_rejected_before_socket_creation(self):
        context = Mock()
        with patch.object(driver.socket, "create_connection") as dial:
            conn = driver.LoopbackHTTPSConnection("remote.example.invalid", context=context)
            with self.assertRaises(OSError):
                conn.connect()
            dial.assert_not_called()

    def test_tls_verification_error_does_not_fallback_to_insecure_transport(self):
        with patch.object(driver.socket, "create_connection") as dial:
            context = Mock()
            context.wrap_socket.side_effect = ValueError("synthetic TLS failure")
            conn = driver.LoopbackHTTPSConnection("auth-e2e.localhost", context=context)
            with self.assertRaises(ValueError):
                conn.connect()
            dial.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
