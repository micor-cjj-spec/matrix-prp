"""Offline-testable phase dispatcher. No SSH, credentials or deployment CLI.

The injected verifier must obtain trusted root-local route proofs separately;
the journal and hosted artifact are not authorities for those proofs.
"""
import copy
import datetime
import re
import time
from guard_release_engine import GateError, sign, utc, epoch
from linux_external_collector import public_job, IDENTITY

ACTIVE = {'PREFLIGHT': 'preflight', 'COLLECT_EXTERNAL_EVIDENCE': 'post_reload',
          'POST_ROLLBACK': 'post_rollback'}
TERMINAL = {'ACCEPT', 'REJECTED', 'ROLLED_BACK', 'RECOVERY_REQUIRED'}
WAITING = {'PRECHECK', 'PREFLIGHT_VERIFY', 'BACKUP', 'INSTALL_PAIR', 'NGINX_TEST',
           'RELOAD', 'VERIFY_POLICY_B', 'ROLLBACK', 'POST_ROLLBACK_VERIFY'}


class Watcher:
    def __init__(self, publisher, verify, submit, pin):
        self.publisher, self.verify, self.submit, self.pin = publisher, verify, submit, pin
        self.seen = set()
        self.pending = None
        self.deployment = None

    def step(self, snapshot, key=None):
        if not isinstance(snapshot, dict):
            raise GateError('TRANSACTION_SNAPSHOT_FORMAT')
        state = snapshot.get('state')
        if state in TERMINAL:
            self.pending = None
            return state
        if state in WAITING:
            return 'WAIT'
        if state not in ACTIVE:
            raise GateError('UNKNOWN_TRANSACTION_STATE')
        try:
            job = public_job(snapshot['job'])
        except (KeyError, TypeError):
            raise GateError('REMOTE_JOB_FORMAT') from None
        for name, size in [('deployment_id',32), ('nonce',48),
                           ('manifest_sha256',64), ('probe_sha256',64)]:
            if not isinstance(job[name], str) or not re.fullmatch('[0-9a-f]{'+str(size)+'}', job[name]):
                raise GateError('REMOTE_JOB_IDENTITY_FORMAT')
        try:
            stamp = datetime.datetime.fromisoformat(job['issued_utc'])
            if stamp.utcoffset() != datetime.timedelta(0): raise ValueError()
            issued = epoch(job['issued_utc'])
        except (ValueError, TypeError):
            raise GateError('REMOTE_JOB_TIME_FORMAT') from None
        budget = job['max_seconds']
        if type(budget) is not int or not 1 <= budget <= 900:
            raise GateError('REMOTE_JOB_BUDGET')
        if not issued <= time.time()+2 or time.time() > issued+budget:
            raise GateError('REMOTE_JOB_EXPIRED_OR_FUTURE')
        if job['phase'] != ACTIVE[state] or job['manifest_sha256'] != self.pin:
            raise GateError('UNREVIEWED_REMOTE_JOB')
        if self.deployment is None:
            self.deployment = job['deployment_id']
        if job['deployment_id'] != self.deployment:
            raise GateError('TRANSACTION_CHANGED')
        identity = (job['deployment_id'], job['phase'], job['nonce'])
        if self.pending and self.pending[0] != identity:
            # Never deliver a late artifact into a different active phase.
            raise GateError('ACTIVE_JOB_CHANGED_DURING_COLLECTION')
        if self.pending is None:
            if identity in self.seen:
                return 'WAIT'
            self.seen.add(identity)  # An ambiguous dispatch must never be retried.
            handle = self.publisher.start(copy.deepcopy(job))
            self.pending = (identity, handle, job, utc())
            return 'STARTED'
        _, handle, original, started = self.pending
        if original != job:
            raise GateError('ACTIVE_JOB_MUTATED')
        result = self.publisher.poll(handle)
        if result['state'] == 'RUNNING':
            return 'RUNNING'
        if result['state'] not in {'COMPLETED', 'FAILED'}:
            raise GateError('UNKNOWN_PUBLISHER_STATE')
        if not isinstance(key, bytes) or len(key) != 32:
            raise GateError('SESSION_KEY_UNAVAILABLE')
        try:
            if result['state'] == 'FAILED':
                raise GateError('HOSTED_COLLECTION_FAILED')
            envelope = self.verify(result, copy.deepcopy(original), key)
        except GateError:
            # Explicit incomplete evidence: unchanged root gate rejects it.
            # Do not label unknown transport/provenance failures safe denials.
            payload = {name: original[name] for name in IDENTITY}
            payload.update(started_utc=started, ended_utc=utc(), dns=[],
                           observations=[], collector_failure='HOSTED_EVIDENCE_REJECTED')
            envelope = sign(payload, key)
        self.submit(copy.deepcopy(original), envelope)
        self.pending = None
        return 'SUBMITTED'
