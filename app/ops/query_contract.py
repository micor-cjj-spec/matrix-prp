"""D-M03 synthetic read authorization and dispatch contract, NOT an MCP server.

Only a future independently authenticated transport may populate the verified
identity and current grant; this module does not verify OAuth JWTs, connect
to an issuer, install a tool, or grant anyone live access.
"""
from dataclasses import dataclass
import uuid
from snapshot_contract import ENV, SnapshotStore, strict_json, utc, query_snapshot
from shared_snapshot import SharedSnapshotReader

TOOL = "prp_ops_status_get"
SCOPE = "prp.ops.read"
ISSUER = "https://issuer.invalid/ops-staging"   # deliberately non-live fixture
RESOURCE = "https://ops.invalid/mcp"
CLIENT = "https://chatgpt.com/oauth/client.json"
SUBJECT = "synthetic-staging-owner"
SCOPES = frozenset({SCOPE})
MAX_ARGS = 256

class QueryDenied(ValueError):
    """Uniform denial; no tokens, subject, resource or grant details."""

@dataclass(frozen=True)
class Policy:
    enabled: bool = False
    # Actual policy is pinned by server configuration, never request arguments.

@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    audience: str
    client: str
    subject: str
    scopes: frozenset
    grant_id: str
    issued_at: int
    expires_at: int

@dataclass(frozen=True)
class CurrentGrant:
    grant_id: str
    issuer: str
    resource: str
    client: str
    subject: str
    environment: str
    scopes: frozenset
    issued_at: int
    expires_at: int
    active: bool

def require(condition):
    if condition is not True:
        raise QueryDenied("query denied")

def grant_id_valid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False

def instant(clock, previous=None):
    now = clock()
    utc(now)  # exact bounded integer UTC epoch, not model-supplied
    require(previous is None or now >= previous)
    return now

def validity(issued, expires, now):
    utc(issued)
    utc(expires)
    require(issued <= now < expires)

def check_identity(identity, now):
    require(type(identity) is VerifiedIdentity)
    require(type(identity.issuer) is str and identity.issuer == ISSUER
            and type(identity.audience) is str and identity.audience == RESOURCE
            and type(identity.client) is str and identity.client == CLIENT
            and type(identity.subject) is str and identity.subject == SUBJECT
            and type(identity.scopes) is frozenset and identity.scopes == SCOPES
            and grant_id_valid(identity.grant_id))
    validity(identity.issued_at, identity.expires_at, now)

def check_grant(grant, identity, now):
    require(type(grant) is CurrentGrant)
    require(grant.active is True
            and type(grant.grant_id) is str and grant.grant_id == identity.grant_id
            and type(grant.issuer) is str and grant.issuer == ISSUER
            and type(grant.resource) is str and grant.resource == RESOURCE
            and type(grant.client) is str and grant.client == CLIENT
            and type(grant.subject) is str and grant.subject == SUBJECT
            and type(grant.environment) is str and grant.environment == ENV
            and type(grant.scopes) is frozenset and grant.scopes == SCOPES)
    validity(grant.issued_at, grant.expires_at, now)
    require(grant.issued_at <= identity.issued_at)

def query_status_fixture(tool_name, raw_arguments, *, policy, identity_provider,
                         grant_provider, trusted_clock, store):
    """Read only one pre-existing snapshot; never collect, write or refresh.

    All keyword-only arguments are independently controlled synthetic adapter
    inputs, not caller payload or model metadata. Grant provider must return
    current authoritative state (no stale cache). Both pre-read and
    pre-disclosure checks are required; real verification/revocation
    linearization, quotas, deadlines and identity isolation remain open.
    """
    try:
        require(type(policy) is Policy and policy.enabled is True)
        require(type(tool_name) is str and tool_name == TOOL)
        args = strict_json(raw_arguments, MAX_ARGS)
        require(type(args) is dict and not args)
        require(type(store) in (SnapshotStore, SharedSnapshotReader))
        require(callable(identity_provider) and callable(grant_provider)
                and callable(trusted_clock))
        initial = instant(trusted_clock)
        identity = identity_provider()
        check_identity(identity, initial)
        grant = grant_provider(identity.grant_id)
        before = instant(trusted_clock, initial)
        check_identity(identity, before)
        check_grant(grant, identity, before)
        raw = store.read_raw()
        latest = grant_provider(identity.grant_id)
        after = instant(trusted_clock, before)
        check_identity(identity, after)
        check_grant(latest, identity, after)
        require(latest == grant)
        # Freshness is measured after the final grant check, not at entry.
        return query_snapshot(raw, after)
    except Exception:
        raise QueryDenied("query denied") from None
