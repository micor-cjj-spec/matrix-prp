"""Real loopback TLS with disposable test-only keys, no public connections."""
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from phase_tls_context_cache import ContextCache


class TLSHandshakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='prp-disposable-tls-unit-')
        root=Path(cls.temp.name);cls.cert=root/'test-ca.pem';key=root/'test-server-key.pem'
        openssl=shutil.which('openssl')
        if not openssl:
            candidate=Path('C:/Program Files/Git/usr/bin/openssl.exe')
            if candidate.is_file():openssl=str(candidate)
        if not openssl:raise RuntimeError('OPENSSL_REQUIRED_FOR_REAL_TLS_REGRESSION')
        subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes',
            '-keyout',str(key),'-out',str(cls.cert),'-days','1','-subj','/CN=localhost',
            '-addext','subjectAltName=DNS:localhost',
            '-addext','basicConstraints=critical,CA:TRUE',
            '-addext','keyUsage=critical,digitalSignature,keyCertSign,cRLSign'],
            capture_output=True,check=True,timeout=30)
        key.chmod(0o600)
        cls.server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server_context.load_cert_chain(str(cls.cert),str(key))
        cls.server_context.set_alpn_protocols(['http/1.1'])
        cls.listener=socket.socket();cls.listener.bind(('127.0.0.1',0));cls.listener.listen(5)
        cls.listener.settimeout(.2);cls.address=cls.listener.getsockname();cls.stop=threading.Event()
        def serve():
            while not cls.stop.is_set():
                try:client,_=cls.listener.accept()
                except socket.timeout:continue
                except OSError:break
                try:
                    client.settimeout(3)
                    with cls.server_context.wrap_socket(client,server_side=True) as stream:
                        if stream.recv(1)==b'x':stream.sendall(b'y')
                except (OSError,ssl.SSLError):client.close()
        cls.thread=threading.Thread(target=serve,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.stop.set();cls.listener.close();cls.thread.join(timeout=5)
        assert not cls.thread.is_alive()
        cls.temp.cleanup()

    def plan(self,cache):
        plan=cache.create_default_context();plan.set_alpn_protocols(['http/1.1']);return plan

    def test_repeated_fresh_handshakes_verify_certificate_and_do_not_resume_session(self):
        cache=ContextCache(lambda:ssl.create_default_context(cafile=str(self.cert)))
        for _ in range(3):
            with socket.create_connection(self.address,timeout=3) as raw:
                with self.plan(cache).wrap_socket(raw,server_hostname='localhost') as secured:
                    self.assertFalse(secured.session_reused)
                    self.assertEqual(secured.selected_alpn_protocol(),'http/1.1')
                    self.assertTrue(secured.getpeercert())
                    secured.sendall(b'x');self.assertEqual(secured.recv(1),b'y')

    def test_wrong_hostname_rejected_even_after_successful_cached_handshake(self):
        cache=ContextCache(lambda:ssl.create_default_context(cafile=str(self.cert)))
        with socket.create_connection(self.address,timeout=3) as raw:
            with self.plan(cache).wrap_socket(raw,server_hostname='localhost') as secured:
                secured.sendall(b'x');self.assertEqual(secured.recv(1),b'y')
        with socket.create_connection(self.address,timeout=3) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.plan(cache).wrap_socket(raw,server_hostname='wrong.example.invalid')

    def test_untrusted_issuer_rejected(self):
        cache=ContextCache()
        with socket.create_connection(self.address,timeout=3) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.plan(cache).wrap_socket(raw,server_hostname='localhost')


if __name__=='__main__':unittest.main()
