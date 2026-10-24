"""Local durable dispatch budget: no registration or production transport."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from run_hosted_guard_authorized import BudgetPublisher,GateError,PREPARE


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.ledger=Path(self.temp.name)/'ledger.json'
        self.ledger.write_text(json.dumps({'maximum_temporary_device_registrations':3}))
        self.publisher=Mock();self.wrapper=BudgetPublisher(self.publisher,self.ledger)

    def job(self,phase,deployment='fixture'):
        return dict(deployment_id=deployment,phase=phase,nonce=phase)

    def test_three_phases_then_stop(self):
        for phase in ['preflight','post_reload','post_rollback']:self.wrapper.start(self.job(phase))
        with self.assertRaises(GateError):self.wrapper.start(self.job('post_rollback'))
        self.assertEqual(self.publisher.start.call_count,3)

    def test_ambiguous_post_consumes_one_budget_and_cannot_repeat_phase(self):
        self.publisher.start.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):self.wrapper.start(self.job('preflight'))
        with self.assertRaises(GateError):self.wrapper.start(self.job('preflight'))
        self.publisher.start.assert_called_once()
        self.assertEqual(len(json.loads(self.ledger.read_text())['dispatch_attempts']),1)

    def test_another_transaction_cannot_reuse_authorization(self):
        self.wrapper.start(self.job('preflight'))
        with self.assertRaises(GateError):self.wrapper.start(self.job('post_reload','another'))
        self.publisher.start.assert_called_once()

    def test_embedded_prepare_program_compiles(self):
        compile(PREPARE,'root-preparation-reviewed','exec')


if __name__=='__main__':unittest.main()
