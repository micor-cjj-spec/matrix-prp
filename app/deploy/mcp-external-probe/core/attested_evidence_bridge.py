"""Review-only attested-artifact bridge. No network or production mutation CLI.

The administrator's HMAC key never enters Actions, environment variables or an
artifact. Pinned GitHub CLI verifies Sigstore provenance before the existing
EvidenceGate independently validates the observations. No boolean receipt or
uploaded `passed` field can substitute for either verification.

API/archive downloads and production integration are NOT implemented here.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from guard_release_engine import EvidenceGate, GateError, sign

REPO='micor-cjj-spec/matrix-prp'
REF='refs/heads/fix/mcp-hosted-network-probe-20261024'
WORKFLOW='.github/workflows/codex-prp-worker.yml'
MAX_PAYLOAD=4_000_000
MAX_ARCHIVE=6_000_000

@dataclass(frozen=True)
class ExpectedRun:
    commit: str
    run_id: int
    attempt: int
    repository_id: int
    owner_id: int
    workflow_id: int=381769081

    def __post_init__(self):
        if not re.fullmatch('[0-9a-f]{40}',self.commit):raise GateError('SOURCE_COMMIT_INVALID')
        for value in [self.run_id,self.attempt,self.repository_id,self.owner_id,self.workflow_id]:
            if type(value) is not int or value<=0:raise GateError('SOURCE_ID_INVALID')

def checked_json(data):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise GateError('DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    try:return json.loads(data,object_pairs_hook=unique)
    except (ValueError,UnicodeError,RecursionError):raise GateError('INVALID_JSON')

def validate_metadata(run,artifact,expected,nonce):
    if not re.fullmatch('[0-9a-f]{48}',nonce):raise GateError('JOB_NONCE_INVALID')
    required={'id':expected.run_id,'run_attempt':expected.attempt,'workflow_id':expected.workflow_id,
              'head_sha':expected.commit,'head_branch':REF.removeprefix('refs/heads/'),
              'event':'workflow_dispatch','status':'completed','conclusion':'success','path':WORKFLOW}
    if any(run.get(k)!=v for k,v in required.items()):raise GateError('GITHUB_RUN_IDENTITY')
    for name in ['repository','head_repository']:
        repo=run.get(name,{})
        if repo.get('id')!=expected.repository_id or repo.get('full_name')!=REPO:
            raise GateError('GITHUB_REPOSITORY_IDENTITY')
    if run['repository'].get('owner',{}).get('id')!=expected.owner_id:raise GateError('GITHUB_OWNER_IDENTITY')
    if artifact.get('name')!='prp-guard-'+nonce or artifact.get('expired') is not False:
        raise GateError('GITHUB_ARTIFACT_IDENTITY')
    if type(artifact.get('id')) is not int or artifact['id']<=0:raise GateError('GITHUB_ARTIFACT_IDENTITY')
    w=artifact.get('workflow_run',{})
    for k,v in {'id':expected.run_id,'repository_id':expected.repository_id,'head_repository_id':expected.repository_id,
                'head_sha':expected.commit,'head_branch':REF.removeprefix('refs/heads/')}.items():
        if w.get(k)!=v:raise GateError('GITHUB_ARTIFACT_RUN_MISMATCH')

def payload_from_archive(archive,artifact):
    if not isinstance(archive,bytes) or len(archive)>MAX_ARCHIVE:raise GateError('ARTIFACT_ARCHIVE_LIMIT')
    if artifact.get('digest')!='sha256:'+hashlib.sha256(archive).hexdigest():raise GateError('ARTIFACT_ARCHIVE_DIGEST')
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            entries=z.infolist()
            if len(entries)!=1:raise GateError('ARTIFACT_FILE_SET')
            item=entries[0]
            if item.filename!='observations.json' or item.file_size>MAX_PAYLOAD or item.flag_bits&1 or stat.S_ISLNK(item.external_attr>>16):
                raise GateError('ARTIFACT_FILE_SET')
            raw=z.read(item)
    except (zipfile.BadZipFile,RuntimeError,ValueError):raise GateError('ARTIFACT_ZIP_INVALID')
    if len(raw)>MAX_PAYLOAD:raise GateError('ARTIFACT_PAYLOAD_LIMIT')
    payload=checked_json(raw)
    if not isinstance(payload,dict):raise GateError('ARTIFACT_PAYLOAD_TYPE')
    return raw,payload

def validate_statement(statement,raw,expected):
    if statement.get('_type')!='https://in-toto.io/Statement/v1' or statement.get('predicateType')!='https://slsa.dev/provenance/v1':
        raise GateError('PROVENANCE_TYPE')
    if statement.get('subject')!=[{'name':'observations.json','digest':{'sha256':hashlib.sha256(raw).hexdigest()}}]:
        raise GateError('PROVENANCE_SUBJECT')
    p=statement.get('predicate',{});definition=p.get('buildDefinition',{})
    if definition.get('buildType')!='https://actions.github.io/buildtypes/workflow/v1':
        raise GateError('PROVENANCE_BUILD_TYPE')
    workflow=definition.get('externalParameters',{}).get('workflow',{})
    if workflow!={'ref':REF,'repository':'https://github.com/'+REPO,'path':WORKFLOW}:raise GateError('PROVENANCE_WORKFLOW')
    github=definition.get('internalParameters',{}).get('github',{})
    if any(github.get(k)!=v for k,v in {'event_name':'workflow_dispatch','repository_id':str(expected.repository_id),
                                      'repository_owner_id':str(expected.owner_id),'runner_environment':'github-hosted'}.items()):raise GateError('PROVENANCE_REPOSITORY')
    source={'uri':'git+https://github.com/'+REPO+'@'+REF,'digest':{'gitCommit':expected.commit}}
    if definition.get('resolvedDependencies',[]).count(source)!=1:raise GateError('PROVENANCE_COMMIT')
    details=p.get('runDetails',{})
    if details.get('builder',{}).get('id')!='https://github.com/'+REPO+'/'+WORKFLOW+'@'+REF:raise GateError('PROVENANCE_RUNNER')
    invocation='https://github.com/'+REPO+'/actions/runs/'+str(expected.run_id)+'/attempts/'+str(expected.attempt)
    if details.get('metadata',{}).get('invocationId')!=invocation:raise GateError('PROVENANCE_RUN_ATTEMPT')

def verify_cli(raw,bundle,expected,cli_path,cli_sha256):
    cli=Path(cli_path)
    if not re.fullmatch('[0-9a-f]{64}',cli_sha256) or not cli.is_file() or cli.is_symlink() or hashlib.sha256(cli.read_bytes()).hexdigest()!=cli_sha256:
        raise GateError('PROVENANCE_VERIFIER_NOT_PINNED')
    if not isinstance(bundle,bytes) or not 1<=len(bundle)<=2_000_000:raise GateError('PROVENANCE_BUNDLE_LIMIT')
    with tempfile.TemporaryDirectory(prefix='prp-attestation-') as directory:
        root=Path(directory);artifact=root/'observations.json';proof=root/'bundle.json';artifact.write_bytes(raw);proof.write_bytes(bundle)
        artifact.chmod(0o600);proof.chmod(0o600)
        args=[str(cli.resolve()),'attestation','verify',str(artifact),'--bundle',str(proof),'--repo',REPO,'--hostname','github.com',
              '--signer-digest',expected.commit,
              '--source-digest',expected.commit,'--source-ref',REF,'--deny-self-hosted-runners',
              '--cert-oidc-issuer','https://token.actions.githubusercontent.com',
              '--cert-identity','https://github.com/'+REPO+'/'+WORKFLOW+'@'+REF,
              '--predicate-type','https://slsa.dev/provenance/v1','--format','json']
        # No administrator/session keys, personal CLI config or token environment.
        env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE','SSL_CERT_FILE','SSL_CERT_DIR'}}
        env.update(GH_CONFIG_DIR=str(root/'empty-cli-config'),GH_PROMPT_DISABLED='1',NO_COLOR='1')
        try:p=subprocess.run(args,capture_output=True,timeout=30,env=env)
        except (OSError,subprocess.TimeoutExpired):raise GateError('PROVENANCE_VERIFICATION_UNAVAILABLE')
        # A nonzero exit can be a policy, network or tool error. Do not claim
        # cryptographic refusal merely from an abnormal exit.
        if p.returncode or len(p.stdout)>2_000_000:raise GateError('PROVENANCE_VERIFICATION_FAILED')
        results=checked_json(p.stdout)
        if not isinstance(results,list) or len(results)!=1:raise GateError('PROVENANCE_VERDICT_FORMAT')
        try:statement=results[0]['verificationResult']['statement']
        except (KeyError,TypeError):raise GateError('PROVENANCE_VERDICT_FORMAT')
        validate_statement(statement,raw,expected)

def accept_attested(run,artifact,archive,bundle,expected,job,manifest,pin,key,cli_path,cli_sha256,now=None):
    """Local administrator bridge only; caller retains key in memory.

    The unchanged root gate must still verify the returned HMAC independently.
    This function is inert until invoked with a real pinned verifier and bundle.
    """
    validate_metadata(run,artifact,expected,job['nonce'])
    raw,payload=payload_from_archive(archive,artifact)
    verify_cli(raw,bundle,expected,cli_path,cli_sha256)
    envelope=sign(payload,key)
    EvidenceGate(manifest,pin,key).verify(envelope,job,now=now)
    return envelope
