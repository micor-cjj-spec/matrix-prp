"""Bounded in-process JSON-RPC candidate; no HTTP listener or registration.

The caller supplies a server-extracted single Authorization header. Actual
HTTP framing/header multiplicity, origin, rate limits, lifecycle compatibility
and trusted issuer setup still require separate integration.
"""
from query_contract import QueryDenied, check_grant, check_identity, instant
from snapshot_contract import strict_json
from mcp_adapter import tools_list, tools_call
from auth_adapter import authorize_request

PROTOCOL = "2025-06-18"  # Version already exercised by repository MCP smoke tests.
MAX_RPC = 4096

def error(code, message, request_id=None):
    return {"jsonrpc":"2.0", "id":request_id, "error":{"code":code,"message":message}}

def result(value, request_id):
    return {"jsonrpc":"2.0","id":request_id,"result":value}

def dispatch_fixture(raw, authorization, **server):
    """Returns (HTTP status candidate, JSON response or None)."""
    try:
        context = authorize_request(authorization, **server)
    except QueryDenied:
        return 401, None
    try:
        p = strict_json(raw, MAX_RPC)
    except Exception:
        return 400, error(-32700,"Parse error")
    if (type(p) is not dict or set(p)-{"jsonrpc","id","method","params"}
            or p.get("jsonrpc") != "2.0" or type(p.get("method")) is not str):
        return 400, error(-32600,"Invalid request")
    method = p["method"]
    params = p.get("params", {})
    if "id" not in p:
        if method == "notifications/initialized" and params == {}:
            return 202, None
        return 400, error(-32600,"Invalid notification")
    request_id = p["id"]
    if not (type(request_id) is int and -(1 << 53) < request_id < (1 << 53)
            or type(request_id) is str and 0 < len(request_id) <= 128
               and all(32 <= ord(c) < 127 for c in request_id)):
        return 400, error(-32600,"Invalid request")
    if type(params) is not dict:
        return 200, error(-32602,"Invalid params",request_id)
    try:
        # Discovery and ping are also authorized; no static unauthenticated tools/list.
        identity = context.identity_provider()
        grant = context.grant_provider(identity.grant_id)
        now = instant(context.trusted_clock)
        check_identity(identity, now)
        check_grant(grant, identity, now)
    except Exception:
        return 401, None
    if method == "initialize":
        if (set(params) != {"protocolVersion","capabilities","clientInfo"}
                or params["protocolVersion"] != PROTOCOL
                or type(params["capabilities"]) is not dict
                or type(params["clientInfo"]) is not dict):
            return 200, error(-32602,"Unsupported initialization",request_id)
        return 200, result({"protocolVersion":PROTOCOL,"capabilities":{"tools":{}},
            "serverInfo":{"name":"prp-ops-readonly","version":"0.1.0-offline"}},request_id)
    if method == "ping" and params == {}:
        return 200, result({}, request_id)
    if method == "tools/list" and params == {}:
        return 200, result(tools_list(), request_id)
    if method == "tools/call":
        return 200, result(tools_call(params, context), request_id)
    if method in ("ping","tools/list"):
        return 200, error(-32602,"Invalid params",request_id)
    return 200, error(-32601,"Method not found",request_id)
