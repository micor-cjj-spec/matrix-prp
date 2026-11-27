"""Offline MCP tools/list and tools/call contract. No server or transport.

This adapter is deliberately not registered with the application. A future
transport must create ServerVerifiedContext only after real OAuth/JWKS and
authoritative grant verification. Request metadata is ignored, never identity.
"""
import copy
import json
from dataclasses import dataclass

from query_contract import TOOL, QueryDenied, query_status_fixture, FIXTURE_PROFILE
from snapshot_contract import SnapshotStore
from shared_snapshot import SharedSnapshotReader

_TOOL = {
    "name": TOOL,
    "description": "Read the latest pre-collected, time-bounded PRP host status snapshot. Does not run commands or trigger collection.",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
}

@dataclass(frozen=True)
class ServerVerifiedContext:
    """Server-owned context, never populated from MCP arguments or _meta."""
    policy: object
    identity_provider: object
    grant_provider: object
    trusted_clock: object
    store: object
    profile: object = FIXTURE_PROFILE

def tools_list():
    """Static offline capability projection; no dynamic tool discovery."""
    return {"tools": [copy.deepcopy(_TOOL)]}

def _error():
    return {
        "content": [{"type": "text", "text": "Read-only status query denied."}],
        "isError": True,
    }

def tools_call(params, context):
    """Dispatch exactly one empty-argument tool through the authorization contract."""
    try:
        if type(context) is not ServerVerifiedContext:
            raise QueryDenied("query denied")
        if type(params) is not dict or not {"name", "arguments"}.issubset(params):
            raise QueryDenied("query denied")
        if set(params) - {"name", "arguments", "_meta"}:
            raise QueryDenied("query denied")
        if type(params["name"]) is not str or params["name"] != TOOL:
            raise QueryDenied("query denied")
        if type(params["arguments"]) is not dict or params["arguments"]:
            raise QueryDenied("query denied")
        if "_meta" in params and type(params["_meta"]) is not dict:
            raise QueryDenied("query denied")
        # The only accepted arguments are {}, serialized canonically. Metadata
        # is deliberately discarded and can never influence identity or scope.
        result = query_status_fixture(
            TOOL, b"{}",
            policy=context.policy,
            identity_provider=context.identity_provider,
            grant_provider=context.grant_provider,
            trusted_clock=context.trusted_clock,
            store=context.store,
            profile=context.profile,
        )
        payload = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return {
            "content": [{"type": "text", "text": payload}],
            "structuredContent": copy.deepcopy(result),
            "isError": False,
        }
    except Exception:
        return _error()
