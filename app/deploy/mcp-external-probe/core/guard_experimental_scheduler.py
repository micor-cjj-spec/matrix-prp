"""Isolated experiment only. Not wired into any production manifest or launcher."""
import copy
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED


def schedule(requests, probe, deadline, concurrency=2, cadence=.18):
    if concurrency not in (1, 2):
        raise ValueError('CONCURRENCY_LIMIT')
    if cadence < .18:
        raise ValueError('CADENCE_LIMIT')
    queued = time.monotonic()
    items = iter(requests.items())
    output = {}
    pending = {}
    exhausted = False
    next_launch = queued
    counter_lock = threading.Lock()
    active = 0
    peak = 0

    def execute(ident, spec):
        nonlocal active, peak
        if time.monotonic() >= deadline:
            raise TimeoutError('PHASE_DEADLINE')
        queue_seconds = time.monotonic() - queued
        with counter_lock:
            active += 1
            peak = max(peak, active)
        try:
            result = probe(spec)
        finally:
            finished_seconds = time.monotonic() - queued
            with counter_lock:
                active -= 1
        if not isinstance(result, dict):
            raise ValueError('INVALID_OBSERVATION')
        if 'request_id' in result and result['request_id'] != ident:
            raise ValueError('REQUEST_ID_MISMATCH')
        result = copy.deepcopy(result)
        result['request_id'] = ident
        result['queue_seconds'] = queue_seconds
        result['dispatch_finished_seconds'] = finished_seconds
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        try:
            while pending or not exhausted:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError('PHASE_DEADLINE')
                if not exhausted and len(pending) < concurrency and now >= next_launch:
                    try:
                        ident, spec = next(items)
                    except StopIteration:
                        exhausted = True
                    else:
                        future = executor.submit(execute, ident, copy.deepcopy(spec))
                        pending[future] = ident
                        next_launch = time.monotonic() + cadence
                if not pending:
                    if not exhausted:
                        time.sleep(min(.05, max(0, min(next_launch, deadline) - time.monotonic())))
                    continue
                timeout = min(.05, max(0, deadline - time.monotonic()))
                done, _ = wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
                for future in done:
                    ident = pending.pop(future)
                    output[ident] = future.result()  # Never suppress worker exceptions.
            if time.monotonic() >= deadline:
                raise TimeoutError('PHASE_DEADLINE')
        finally:
            for future in pending:
                future.cancel()
    if set(output) != set(requests):
        raise ValueError('INCOMPLETE_OBSERVATIONS')
    if active != 0 or peak > concurrency:
        raise ValueError('WORKER_RESOURCE_ACCOUNTING')
    for result in output.values():
        result['scheduler_peak_workers'] = peak
    return [output[ident] for ident in requests]
