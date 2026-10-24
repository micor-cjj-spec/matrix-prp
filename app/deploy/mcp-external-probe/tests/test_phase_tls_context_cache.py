"""Context-policy tests. These mocks do not prove real TLS handshakes."""
import concurrent.futures
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from phase_tls_context_cache import ContextCache,load_probes

class CacheTests(unittest.TestCase):
    def factory(self):
        factory=Mock()
        def make():
            value=Mock();value.verify_mode=ssl.CERT_REQUIRED;value.check_hostname=True
            return value
        factory.side_effect=make
        return factory

    def test_context_cached_but_every_call_wraps_a_new_socket(self):
        factory=self.factory();cache=ContextCache(factory)
        for _ in range(3):
            plan=cache.create_default_context();plan.set_alpn_protocols(['http/1.1']);plan.wrap_socket(object(),server_hostname='micor.top')
        factory.assert_called_once()
        context=cache.context(True,('http/1.1',))
        self.assertEqual(context.wrap_socket.call_count,3)
        context.set_alpn_protocols.assert_called_once_with(['http/1.1'])

    def test_hostname_and_alpn_policies_cannot_leak_between_probes(self):
        cache=ContextCache(self.factory())
        first=cache.context(False,('http/1.1',));second=cache.context(True,('http/1.1',));third=cache.context(True,('h2','http/1.1'))
        self.assertIsNot(first,second);self.assertIsNot(second,third)
        self.assertFalse(first.check_hostname);self.assertTrue(second.check_hostname)

    def test_two_worker_threads_have_separate_contexts(self):
        cache=ContextCache(self.factory());barrier=threading.Barrier(2)
        def work():
            context=cache.context(True,('http/1.1',));barrier.wait(timeout=5);return id(context)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(work);two=pool.submit(work)
            self.assertNotEqual(one.result(),two.result())

    def test_weakened_or_drifted_context_refused(self):
        cache=ContextCache(self.factory());context=cache.context(True,('http/1.1',));context.verify_mode=ssl.CERT_NONE
        with self.assertRaises(ValueError):cache.context(True,('http/1.1',))
        factory=self.factory();factory.side_effect=None;factory.return_value.verify_mode=ssl.CERT_NONE
        with self.assertRaises(ValueError):ContextCache(factory).context(True,('http/1.1',))

    def test_session_injection_and_unreviewed_policy_refused(self):
        cache=ContextCache(self.factory());plan=cache.create_default_context();plan.set_alpn_protocols(['http/1.1'])
        with self.assertRaises(ValueError):plan.wrap_socket(object(),session=object())
        with self.assertRaises(ValueError):cache.context(True,('unknown',))

    def test_phase_instances_do_not_share_contexts(self):
        factory=self.factory();one=ContextCache(factory);two=ContextCache(factory)
        self.assertIsNot(one.context(True,('http/1.1',)),two.context(True,('http/1.1',)))

    def test_immutable_loader_does_not_mutate_standard_ssl_module(self):
        factory=ssl.create_default_context
        probe=load_probes(Path(__file__).resolve().parent.parent/'release-v4/guard_external_probe.py')
        self.assertIs(ssl.create_default_context,factory)
        self.assertIsNot(probe.ssl,ssl)
        self.assertIs(probe.ssl.SSLCertVerificationError,ssl.SSLCertVerificationError)
        with tempfile.TemporaryDirectory() as directory:
            fake=Path(directory)/'probe.py';fake.write_text('raise RuntimeError("must not execute")')
            with self.assertRaises(ValueError):load_probes(fake)

if __name__=='__main__':unittest.main()
