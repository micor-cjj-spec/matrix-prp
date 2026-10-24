"""Archive and composed-reader tests; cryptographic CLI is mocked here."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError
import hosted_evidence_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def archive(self,names):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,raw in names:z.writestr(name,raw)
        return stream.getvalue()

    def test_single_json_bundle(self):
        self.assertEqual(delivery.signature_bundle(self.archive([('attestation.json',b'{}')])),b'{}')

    def test_extra_traversal_duplicates_and_bad_json_rejected(self):
        for names in [[('../escape.json',b'{}')],[('a.json',b'{}'),('b.json',b'{}')],
                      [('a.json',b'{"x":1,"x":2}')],[('a.json',b'[]')],[('a.txt',b'{}')]]:
            with self.subTest(names=names):
                with self.assertRaises(GateError):delivery.signature_bundle(self.archive(names))

    def test_composition_reads_fresh_context(self):
        channel=Mock();channel.read.return_value=({'context':{'fixture':True}},b'x'*32)
        verifier=delivery.DeliveryVerifier(channel,{},'pin','cli','sha')
        result=dict(bundle_archive=self.archive([('bundle.json',b'{}')]),run={},artifact={},archive=b'zip',expected='run')
        def accept(*args):
            self.assertEqual(args[-1](),{'fixture':True})
            return {'verified-fixture':True}
        with patch.object(delivery,'accept_with_trusted_reader',side_effect=accept):
            self.assertEqual(verifier(result,{},b'x'*32),{'verified-fixture':True})
        channel.read.assert_called_once()

    def test_changed_session_rejected(self):
        channel=Mock();channel.read.return_value=({'context':{}},b'y'*32)
        verifier=delivery.DeliveryVerifier(channel,{},'pin','cli','sha')
        result=dict(bundle_archive=self.archive([('bundle.json',b'{}')]),run={},artifact={},archive=b'zip',expected='run')
        with patch.object(delivery,'accept_with_trusted_reader',side_effect=lambda *args:args[-1]()):
            with self.assertRaises(GateError):verifier(result,{},b'x'*32)


if __name__=='__main__':unittest.main()
