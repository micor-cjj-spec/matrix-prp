"""Bind a trusted admin-channel snapshot to the unchanged root gate context.

Call only with observations returned by the pinned administrator reader, never
with Runner data. Route proofs are reviewed manifest assertions, not new probe
results; freshness is separately established by the current source snapshot.
"""
import copy
from guard_release_engine import GateError, digest
from linux_external_collector import public_job


def bind_context(job, manifest, pin, observed):
    if digest(manifest) != pin or job.get('manifest_sha256') != pin:
        raise GateError('CONTEXT_MANIFEST_DRIFT')
    phase = job.get('phase')
    if phase not in {'preflight', 'post_reload', 'post_rollback'}:
        raise GateError('CONTEXT_PHASE')
    if observed.get('active_job') != public_job(job):
        raise GateError('CONTEXT_ACTIVE_JOB_CHANGED')
    if observed.get('deployment_id') != job['deployment_id'] or observed.get('owner_alive') is not True:
        raise GateError('CONTEXT_OWNER_NOT_LIVE')
    expected_state = {'preflight':'PREFLIGHT', 'post_reload':'COLLECT_EXTERNAL_EVIDENCE',
                      'post_rollback':'POST_ROLLBACK'}[phase]
    if observed.get('state') != expected_state:
        raise GateError('CONTEXT_PHASE_STATE')
    profile = manifest['phases'][phase]
    if observed.get('source_config') != profile['config'] or job['source_config'] != profile['config']:
        raise GateError('CONTEXT_SOURCE_DRIFT')
    if observed.get('reviewed_sources') != manifest['reviewed_sources']:
        raise GateError('CONTEXT_REVIEWED_SOURCE_DRIFT')
    if phase == 'post_reload':
        local = observed.get('local_attestation', {})
        if local != {'deployment_id':job['deployment_id'], 'phase':'post_reload',
                     'verified_observations':len(manifest['local_requests'])}:
            raise GateError('CONTEXT_LOCAL_SUITE_MISSING')
    proofs = profile.get('local_route_proofs', {})
    for name, spec in profile['requests'].items():
        if spec['kind'] in {'authority_denial','path_denial','static_refusal'}:
            proof = proofs.get(name, {})
            if (proof.get('source_config') != profile['config'] or proof.get('case') != spec['case']
                    or proof.get('local_return') is not True or proof.get('upstream_allowed') is not False):
                raise GateError('CONTEXT_REVIEWED_ROUTE_PROOF_MISSING')
    result = public_job(job)
    result['route_proofs'] = copy.deepcopy(proofs)
    return result


def accept_with_trusted_reader(run, artifact, archive, bundle, expected, job,
                               manifest, pin, key, cli_path, cli_sha256, read_context):
    """Obtain root context now, not from an uploaded artifact or cached job.

    Root independently checks the source again after its inbox read. This
    wrapper does not replace that authoritative final check.
    """
    from attested_evidence_bridge import accept_attested
    trusted_job = bind_context(job, manifest, pin, read_context())
    return accept_attested(run, artifact, archive, bundle, expected, trusted_job,
                           manifest, pin, key, cli_path, cli_sha256)
