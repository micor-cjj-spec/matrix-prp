"""Isolated state-machine tests; no remote jobs or production credentials."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'release-v4'))
from guard_release_engine import GateError, utc
from hosted_transaction_watcher import Watcher


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.job = dict(deployment_id='a'*32, phase='preflight', nonce='b'*48,
                        manifest_sha256='c'*64, source_config={}, target={},
                        probe_sha256='d'*64, issued_utc=utc(), max_seconds=900)
        self.snapshot = dict(state='PREFLIGHT', job=self.job)
        self.publisher = Mock()
        self.publisher.start.return_value = 'owned-handle'
        self.publisher.poll.return_value = dict(state='COMPLETED')
        self.verify = Mock(return_value={'fixture': True})
        self.submit = Mock()
        self.w = Watcher(self.publisher, self.verify, self.submit, 'c'*64)

    def test_dispatch_once_and_no_private_context_export(self):
        self.snapshot['job'] = dict(self.job, route_proofs={'private': True}, session_key='secret')
        self.assertEqual(self.w.step(self.snapshot), 'STARTED')
        self.assertEqual(self.publisher.start.call_args.args, (self.job,))
        self.assertEqual(self.w.step(self.snapshot, b'x'*32), 'SUBMITTED')
        self.assertEqual(self.w.step(self.snapshot), 'WAIT')
        self.publisher.start.assert_called_once()

    def test_failed_phase_then_fresh_rollback(self):
        self.w.step(self.snapshot)
        self.verify.side_effect = GateError('LOCAL_ROUTE_PROOF_MISSING')
        self.w.step(self.snapshot, b'x'*32)
        payload = self.submit.call_args.args[1]['payload']
        self.assertEqual(payload['observations'], [])
        self.assertEqual(payload['dns'], [])
        rollback = copy.deepcopy(self.snapshot)
        rollback['state'] = 'POST_ROLLBACK'
        rollback['job'].update(phase='post_rollback', nonce='e'*48)
        self.assertEqual(self.w.step(rollback), 'STARTED')
        self.assertEqual(self.publisher.start.call_count, 2)

    def test_stale_job_never_submitted(self):
        self.w.step(self.snapshot)
        self.snapshot['job'] = dict(self.job, nonce='e'*48)
        with self.assertRaises(GateError): self.w.step(self.snapshot, b'x'*32)
        self.submit.assert_not_called()

    def test_terminal_needs_no_key_or_poll(self):
        self.assertEqual(self.w.step({'state':'ROLLED_BACK'}), 'ROLLED_BACK')
        self.publisher.start.assert_not_called()
        self.publisher.poll.assert_not_called()

    def test_unknown_state_fails_closed(self):
        with self.assertRaises(GateError): self.w.step({'state':'TYPO'})

    def test_ambiguous_dispatch_not_retried(self):
        self.publisher.start.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): self.w.step(self.snapshot)
        self.assertEqual(self.w.step(self.snapshot), 'WAIT')
        self.publisher.start.assert_called_once()

    def test_running_poll_does_not_restart(self):
        self.w.step(self.snapshot)
        self.publisher.poll.return_value = {'state':'RUNNING'}
        for _ in range(3): self.assertEqual(self.w.step(self.snapshot), 'RUNNING')
        self.publisher.start.assert_called_once()
        self.submit.assert_not_called()

    def test_expired_and_malformed_jobs_never_dispatch(self):
        for field, value in [('nonce','../escape'), ('deployment_id','x'),
                             ('issued_utc','2000-01-01T00:00:00+00:00'),
                             ('issued_utc','2026-01-01T00:00:00'),
                             ('max_seconds',True), ('max_seconds',901)]:
            with self.subTest(field=field,value=value):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot['job'][field] = value
                with self.assertRaises(GateError): self.w.step(snapshot)
        self.publisher.start.assert_not_called()

    def test_publisher_cannot_mutate_retained_identity(self):
        def mutate(job):
            job['nonce'] = 'f'*48
            return 'owned-handle'
        self.publisher.start.side_effect = mutate
        self.w.step(self.snapshot)
        self.w.step(self.snapshot, b'x'*32)
        self.assertEqual(self.submit.call_args.args[0]['nonce'], 'b'*48)

    def test_changed_job_fields_same_nonce_rejected(self):
        self.w.step(self.snapshot)
        self.snapshot['job']['target'] = {'unexpected':'host'}
        with self.assertRaises(GateError): self.w.step(self.snapshot, b'x'*32)
        self.publisher.poll.assert_not_called()

    def test_poll_timeout_preserves_same_handle(self):
        self.w.step(self.snapshot)
        self.publisher.poll.side_effect = [TimeoutError(), {'state':'RUNNING'}]
        with self.assertRaises(TimeoutError): self.w.step(self.snapshot)
        self.assertEqual(self.w.step(self.snapshot), 'RUNNING')
        self.assertEqual([c.args for c in self.publisher.poll.call_args_list],
                         [('owned-handle',), ('owned-handle',)])
        self.publisher.start.assert_called_once()


if __name__ == '__main__': unittest.main()
