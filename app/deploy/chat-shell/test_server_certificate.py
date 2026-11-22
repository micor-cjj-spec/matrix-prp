"""Pin the reviewed server encryption certificate; never store its private key."""
from pathlib import Path
import subprocess
import unittest

DIR=Path(__file__).resolve().parent
FINGERPRINT="7A:3E:13:F5:47:7F:E1:88:F7:8A:B1:C1:21:2D:5E:90:92:36:09:86:6D:95:05:C4:D5:B2:28:81:DE:2C:DC:68"

class CertificateSafety(unittest.TestCase):
    def test_exact_verified_public_certificate(self):
        cert=DIR/'recipient.crt'
        pem=cert.read_bytes()
        self.assertTrue(pem.startswith(b'-----BEGIN CERTIFICATE-----'))
        self.assertTrue(pem.rstrip().endswith(b'-----END CERTIFICATE-----'))
        r=subprocess.run(['openssl','x509','-in',str(cert),'-noout','-fingerprint','-sha256'],capture_output=True,text=True,check=True)
        self.assertEqual(r.stdout.strip(),'sha256 Fingerprint='+FINGERPRINT)
        self.assertEqual(subprocess.run(['openssl','x509','-in',str(cert),'-noout','-checkend','0'],capture_output=True).returncode,0)
        self.assertFalse((DIR/'recipient.key').exists(),'Never commit a decryption key')

if __name__ == '__main__':
    unittest.main()
