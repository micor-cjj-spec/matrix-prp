"""Owner-authorized fixed-query gateway to the official Grafana MCP.

This is an offline integration candidate, not a deployable live profile.
Authentication, grant checks and audit are imported from the exact #424 source
commit by the dedicated CI workflow. Grafana credentials and datasource UID
are trusted server configuration; none are accepted from MCP arguments.
"""
import json
import re
import threading
import uuid

from auth_adapter import authorize_request, GrantFile
from mcp_adapter import ServerVerifiedContext
from query_contract import (
    CLIENT, FIXTURE_PROFILE, ISSUER, RESOURCE, SCOPE, Policy, QueryDenied,
)
from rpc_adapter import dispatch_fixture
from snapshot_contract import utc

TOOL_NAME = "prp_observability_query"
AUTH_PROBE = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
MAX_OUTPUT_BYTES = 32768

# PromQL is server-owned. Every selector is pinned to the synthetic PRP scope.
QUERIES = {
    "cpu_busy_percent": (
        '100 * (1 - avg by (instance) (rate('
        'node_cpu_seconds_total{mode="idle",environment="synthetic",'
        'instance="fixture-node"}[2m])))'
    ),
    "memory_available_bytes": (
        'node_memory_MemAvailable_bytes{environment="synthetic",'
        'instance="fixture-node"}'
    ),
    "root_disk_available_bytes": (
        'node_filesystem_avail_bytes{mountpoint="/",environment="synthetic",'
        'instance="fixture-node"}'
    ),
    "node_scrape_up": (
        'up{job="node",environment="synthetic",instance="fixture-node"}'
    ),
}

# 61 evaluation points or fewer; never accepts absolute timestamps or free-form
# durations from the caller. The upstream MCP is independently capped at 1h/120.
WINDOWS = {
    "5m": ("now-5m", "now", 5),
    "15m": ("now-15m", "now", 15),
    "1h": ("now-1h", "now", 60),
}

TOOL_DESCRIPTOR = {
    "name": TOOL_NAME,
    "description": (
        "Read one fixed PRP infrastructure metric for a bounded time window. "
        "Owner-authorized, read-only; arbitrary PromQL and datasource selection are unavailable."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "metric": {"type": "string", "enum": list(QUERIES)},
            "window": {"type": "string", "enum": list(WINDOWS)},
        },
        "required": ["metric", "window"],
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
}


class GatewayDenied(ValueError):
    """Uniform caller-facing denial."""


class InvalidArguments(ValueError):
    pass


class FixedGrafanaQueryAdapter:
    """Call only the upstream official Grafana MCP query_prometheus tool."""

    def __init__(self, rpc, *, datasource_uid):
        if not callable(rpc):
            raise ValueError("invalid upstream")
        if type(datasource_uid) is not str or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,40}", datasource_uid
        ):
            raise ValueError("invalid datasource")
        self._rpc = rpc
        self._datasource_uid = datasource_uid
        self._lock = threading.Lock()

    def query(self, metric, window):
        if type(metric) is not str or metric not in QUERIES:
            raise GatewayDenied("query denied")
        if type(window) is not str or window not in WINDOWS:
            raise GatewayDenied("query denied")
        start, end, step = WINDOWS[window]
        arguments = {
            "datasourceUid": self._datasource_uid,
            "expr": QUERIES[metric],
            "queryType": "range",
            "startTime": start,
            "endTime": end,
            "stepSeconds": step,
        }
        # The upstream MCP session is shared by this adapter. Serialize calls;
        # the outer owner boundary still applies the existing #424 rate budget.
        with self._lock:
            response = self._rpc(
                "tools/call",
                {"name": "query_prometheus", "arguments": arguments},
            )
        if (
            type(response) is not dict
            or response.get("jsonrpc") != "2.0"
            or "error" in response
            or type(response.get("result")) is not dict
            or response["result"].get("isError") is True
        ):
            raise GatewayDenied("query denied")
        encoded = json.dumps(response["result"], sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        if not 0 < len(encoded) <= MAX_OUTPUT_BYTES:
            raise GatewayDenied("query denied")
        # Defense in depth: upstream synthetic matcher must not disclose the
        # foreign positive-control series even if a product regression occurs.
        if b"foreign-marker" in encoded or b'"environment":"foreign"' in encoded:
            raise GatewayDenied("query denied")
        return {"metric": metric, "window": window, "data": response["result"]}


class OwnerBoundGrafanaGateway:
    """Apply #424 Owner Grant, budget and durable audit around fixed Grafana calls."""

    def __init__(
        self, *, server, query_adapter, audit_sink, budget, disclosure_check
    ):
        if (
            type(server) is not dict
            or type(server.get("policy")) is not Policy
            or server["policy"].enabled is not True
            or type(server.get("grants")) is not GrantFile
            or not callable(server.get("introspect"))
            or not callable(server.get("trusted_clock"))
            or not callable(audit_sink)
            or not callable(disclosure_check)
            or type(budget).__name__ != "Budget"
            or type(query_adapter) is not FixedGrafanaQueryAdapter
        ):
            raise ValueError("invalid gateway configuration")
        self._server = dict(server)
        self._query = query_adapter
        self._audit = audit_sink
        self._budget = budget
        self._disclosure = disclosure_check

    def _audit_event(self, status, outcome):
        event = {
            "version": 1,
            "traceId": str(uuid.uuid4()),
            "route": "mcp",
            "candidateStatus": status,
            "outcome": outcome,
        }
        return self._audit(event) is True

    def record_auth_denial(self):
        # Match #424: do not let unadmitted traffic bypass the audit budget.
        try:
            if not self._budget.acquire():
                return
            try:
                self._audit_event(401, "denied")
            finally:
                self._budget.release()
        except Exception:
            pass

    @staticmethod
    def _arguments(value):
        if (
            type(value) is not dict
            or set(value) != {"metric", "window"}
            or type(value.get("metric")) is not str
            or value["metric"] not in QUERIES
            or type(value.get("window")) is not str
            or value["window"] not in WINDOWS
        ):
            raise InvalidArguments("invalid arguments")
        return value["metric"], value["window"]

    def call(self, bearer_token, arguments):
        try:
            acquired = self._budget.acquire()
        except Exception:
            raise GatewayDenied("query denied") from None
        if acquired is not True:
            raise GatewayDenied("query denied")
        status, outcome = 503, "unavailable"
        candidate = None
        final_check = None
        try:
            try:
                metric, window = self._arguments(arguments)
                if self._disclosure() is not True:
                    raise GatewayDenied("query denied")
                receipts = []
                auth_status, _ = dispatch_fixture(
                    AUTH_PROBE,
                    "Bearer " + bearer_token,
                    _capture=receipts.append,
                    **self._server,
                )
                if auth_status != 200 or len(receipts) != 1:
                    status, outcome = 401, "denied"
                    raise GatewayDenied("query denied")
                final_check = receipts[0]
                candidate = self._query.query(metric, window)
                # Re-read the authoritative grant after the downstream call.
                # The callback repeats OAuth introspection and exact identity,
                # grant generation, expiry and active-state checks from #424.
                final_check()
                if self._disclosure() is not True:
                    raise GatewayDenied("query denied")
                status, outcome = 200, "handled"
            except InvalidArguments:
                status, outcome = 400, "denied"
                candidate = None
            except QueryDenied:
                status, outcome = 401, "denied"
                candidate = None
            except GatewayDenied:
                if status == 503:
                    status, outcome = 503, "unavailable"
                candidate = None
            except Exception:
                status, outcome = 503, "unavailable"
                candidate = None

            # Persist a minimal receipt before disclosing any metric result.
            # No caller token, subject, grant ID, metric, PromQL, window or
            # returned data is included in the audit event.
            if not self._audit_event(status, outcome):
                raise GatewayDenied("query denied")
            if status != 200 or candidate is None:
                raise GatewayDenied("query denied")

            try:
                # Same final pre-disclosure revalidation pattern as #424.
                final_check()
                if self._disclosure() is not True:
                    raise GatewayDenied("query denied")
            except Exception:
                # Preserve a second denial receipt if revocation races the
                # audit append. Audit failure remains fail-closed.
                self._audit_event(401, "denied")
                raise GatewayDenied("query denied") from None
            return candidate
        finally:
            self._budget.release()


def build_app(gateway, server):
    """Build an SDK Streamable HTTP app; never starts a listener."""
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.auth.provider import AccessToken, TokenVerifier
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.transport_security import TransportSecuritySettings

    profile = server.get("profile", FIXTURE_PROFILE)
    if profile != FIXTURE_PROFILE:
        raise ValueError("only the offline fixture profile is supported")

    class Verifier(TokenVerifier):
        async def verify_token(self, token):
            try:
                context = authorize_request("Bearer " + token, **server)
                identity = context.identity_provider()
                return AccessToken(
                    token=token,
                    client_id=identity.client,
                    scopes=list(identity.scopes),
                    resource=identity.audience,
                    subject=identity.subject,
                    expires_at=identity.expires_at,
                    claims={"iss": identity.issuer},
                )
            except Exception:
                gateway.record_auth_denial()
                return None

    descriptor = json.loads(json.dumps(TOOL_DESCRIPTOR))

    async def list_tools(ctx, params):
        return types.ListToolsResult(
            tools=[types.Tool.model_validate(descriptor)]
        )

    async def call_tool(ctx, params):
        try:
            access = get_access_token()
            if access is None or params.name != TOOL_NAME:
                raise GatewayDenied("query denied")
            result = gateway.call(access.token, params.arguments)
            payload = json.dumps(result, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False)
            return types.CallToolResult.model_validate({
                "content": [{"type": "text", "text": payload}],
                "structuredContent": result,
                "isError": False,
            })
        except Exception:
            return types.CallToolResult(
                content=[types.TextContent(
                    type="text", text="Read-only observability query denied."
                )],
                isError=True,
            )

    mcp_server = Server(
        "prp-observability-owner-gateway",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        get_tool_input_schema=lambda name: (
            descriptor["inputSchema"] if name == TOOL_NAME else None
        ),
    )
    return mcp_server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=4096,
        token_verifier=Verifier(),
        auth=AuthSettings(
            issuer_url=profile.issuer,
            resource_server_url=profile.resource,
            required_scopes=[SCOPE],
            validate_token_resource=True,
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["ops.invalid"],
            allowed_origins=["https://chatgpt.com"],
        ),
    )
