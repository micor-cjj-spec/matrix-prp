"""Compose reviewed components for an already-started transaction only.

No root coordinator launch, approval creation, service mutation, or registration
authorization is inferred. The caller explicitly constructs an authorized
Publisher. Run from a complete reviewed bundle, not loose development files.
"""
from pathlib import Path
import time
from guard_release_engine import GateError,digest,sha
from pinned_transaction_channel import PinnedChannel
from hosted_evidence_delivery import DeliveryVerifier
from hosted_transaction_watcher import Watcher


def watch_existing(client,transaction,manifest,pin,publisher,cli_path,cli_sha256,
                   max_wait=2400):
    if digest(manifest)!=pin:raise GateError('WATCH_MANIFEST_DRIFT')
    if type(max_wait) is not int or not 1<=max_wait<=3600:raise GateError('WATCH_WAIT_BOUND')
    root=Path(__file__).resolve().parent
    sources=manifest.get('reviewed_sources',{})
    required={'watch_existing_hosted_transaction.py','hosted_transaction_watcher.py',
              'hosted_evidence_delivery.py','pinned_transaction_channel.py',
              'trusted_phase_context.py','hosted_phase_publisher.py','attested_evidence_bridge.py'}
    if not required.issubset(sources):raise GateError('WATCH_SOURCE_SET')
    for name,wanted in sources.items():
        path=root/name
        if Path(name).name!=name or path.is_symlink() or not path.is_file() or sha(path)!=wanted:
            raise GateError('WATCH_REVIEWED_SOURCE_DRIFT')
    channel=PinnedChannel(client,transaction,manifest,pin)
    verifier=DeliveryVerifier(channel,manifest,pin,cli_path,cli_sha256)
    watcher=Watcher(publisher,verifier,channel.submit,pin)
    deadline=time.monotonic()+max_wait
    while time.monotonic()<deadline:
        snapshot,key=channel.read()
        state=watcher.step(snapshot,key)
        # Release the local reference after this step; never persist it.
        key=None
        if state in {'ACCEPT','REJECTED','ROLLED_BACK','RECOVERY_REQUIRED'}:
            return {'state':state,'phases_dispatched':len(watcher.seen)}
        time.sleep(1)
    # Do not restart the coordinator or dispatch again after observation expiry.
    raise GateError('WATCH_OBSERVATION_DEADLINE_CHECK_EXISTING_TRANSACTION')
