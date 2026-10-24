"""Isolated entrypoint guards; no remote transport or hosted dispatch."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError,digest,sha
import watch_existing_hosted_transaction as entry


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        names=['watch_existing_hosted_transaction.py','hosted_transaction_watcher.py',
               'hosted_evidence_delivery.py','pinned_transaction_channel.py',
               'trusted_phase_context.py','hosted_phase_publisher.py','attested_evidence_bridge.py']
        for name in names:(self.root/name).write_text('OFFLINE SOURCE FIXTURE '+name)
        self.manifest={'reviewed_sources':{name:sha(self.root/name) for name in names}}
        self.channel=Mock();self.publisher=Mock()

    def invoke(self,**kwargs):
        return entry.watch_existing(None,'fixture',self.manifest,digest(self.manifest),
                                    self.publisher,'unused-cli','unused-sha',**kwargs)

    def test_source_drift_prevents_channel_creation(self):
        (self.root/'hosted_phase_publisher.py').write_text('drift')
        with patch.object(entry,'__file__',str(self.root/'watch_existing_hosted_transaction.py')),patch.object(entry,'PinnedChannel') as factory:
            with self.assertRaises(GateError):self.invoke()
            factory.assert_not_called()

    def test_terminal_has_no_dispatch_and_returns_real_state(self):
        self.channel.read.return_value=({'state':'ROLLED_BACK'},None)
        with patch.object(entry,'__file__',str(self.root/'watch_existing_hosted_transaction.py')),patch.object(entry,'PinnedChannel',return_value=self.channel):
            self.assertEqual(self.invoke(),{'state':'ROLLED_BACK','phases_dispatched':0})
        self.publisher.start.assert_not_called()

    def test_observation_timeout_never_restarts_or_dispatches(self):
        self.channel.read.return_value=({'state':'PRECHECK'},None)
        with patch.object(entry,'__file__',str(self.root/'watch_existing_hosted_transaction.py')),patch.object(entry,'PinnedChannel',return_value=self.channel),patch.object(entry.time,'monotonic',side_effect=[0,1,5]),patch.object(entry.time,'sleep'):
            with self.assertRaisesRegex(GateError,'CHECK_EXISTING_TRANSACTION'):self.invoke(max_wait=3)
        self.channel.read.assert_called_once()
        self.publisher.start.assert_not_called()
        self.channel.submit.assert_not_called()

    def test_invalid_wait_bound_fails_before_transport(self):
        for bound in [True,0,3601]:
            with self.subTest(bound=bound),patch.object(entry,'PinnedChannel') as factory:
                with self.assertRaises(GateError):self.invoke(max_wait=bound)
                factory.assert_not_called()


if __name__=='__main__':unittest.main()
