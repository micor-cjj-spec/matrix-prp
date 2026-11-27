"""Disposable end-to-end P4.2 test: Owner MCP -> fixed gateway -> official Grafana MCP.

Only GitHub-hosted CI, synthetic Prometheus samples and ephemeral credentials.
No listener is opened for the Owner gateway (Starlette TestClient is in-process).
The official Grafana MCP runs only on an internal Docker network with no ports.
"""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import uuid
import urllib.parse
from unittest.mock import patch


P3 = "b0c0521bf345231ac1562db66ef92746828466e3"
P4 = "c459ac4c56ebdd2be6808f9f7bac46995625714a"
P3_FIXTURE_BLOB = "0384dee80ac635397b8dcc9170bfecce513773cf"
UID = "prp-synthetic"
OWNER_TOKEN = "synthetic-owner-token"


def check(value, label):
    if not value:
        raise AssertionError(label)
    print("OBS_P42_CASE=" + label + ":PASS", flush=True)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if (
        os.getenv("GITHUB_ACTIONS") != "true"
        or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"
        or len(sys.argv) != 3
    ):
        raise SystemExit("disposable hosted CI only")

    work = Path(sys.argv[1]).resolve()
    p41_path = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(work / "app" / "ops"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    p41 = load_module(p41_path, "p41_product")
    from auth_adapter import GrantFile, parse_grant
    from audit_store import AUDIT_NAME, AuditStoreFixture
    from http_boundary import Budget
    from query_contract import (
        CLIENT, FIXTURE_PROFILE, ISSUER, RESOURCE, SCOPE, Policy,
    )
    from snapshot_contract import SnapshotStore, utc
    from owner_gateway import (
        FixedGrafanaQueryAdapter,
        OwnerBoundGrafanaGateway,
        QUERIES,
        TOOL_NAME,
        WINDOWS,
        build_app,
    )
    from starlette.testclient import TestClient

    prefix = "p42-" + uuid.uuid4().hex[:10]
    names = {key: prefix + "-" + key for key in ("p3", "prom", "grafana", "mcp")}
    network = prefix
    admin_password = secrets.token_urlsafe(32)
    upstream_caller = secrets.token_urlsafe(32)
    admin = {
        "Authorization": "Basic "
        + __import__("base64").b64encode(
            ("admin:" + admin_password).encode()
        ).decode()
    }
    created = []

    with tempfile.TemporaryDirectory(prefix="p42-") as temp:
        root = Path(temp)
        root.chmod(0o700)
        fixtures = root / "fixtures"
        fixtures.mkdir(mode=0o755)
        p3_path = fixtures / "p3.py"
        p3_path.write_bytes(
            p41.exact(P3, "app/observability/p3/fixture.py", P3_FIXTURE_BLOB)
        )
        p3_path.chmod(0o644)
        (fixtures / "state.json").write_text(json.dumps({"node": True}))
        (fixtures / "state.json").chmod(0o644)
        prom_config = fixtures / "prometheus.yml"
        prom_config.write_text(
            "global:\n"
            "  scrape_interval: 2s\n"
            "  scrape_timeout: 1s\n"
            "scrape_configs:\n"
            "  - job_name: node\n"
            "    metrics_path: /metrics/node\n"
            "    sample_limit: 250\n"
            "    static_configs:\n"
            "      - targets: ['p3:8080']\n"
            "        labels:\n"
            "          environment: synthetic\n"
            "          instance: fixture-node\n"
        )
        prom_config.chmod(0o644)

        try:
            images = {}
            for key, tag in p41.IMAGES.items():
                p41.run("docker", "pull", "--platform", "linux/amd64", tag, timeout=300)
                image = json.loads(p41.run("docker", "image", "inspect", tag))[0]
                check(
                    image["Os"] == "linux"
                    and image["Architecture"] == "amd64"
                    and bool(image["RepoDigests"]),
                    "pinned-image-" + key,
                )
                images[key] = image["Id"]
                print(
                    "OBS_P42_IMAGE=" + key + "|" + tag + "|"
                    + image["RepoDigests"][0] + "|" + image["Id"],
                    flush=True,
                )

            p41.run("docker", "network", "create", "--internal", network)

            def start(key, image, memory, options=(), args=(), alias=None):
                created.append(names[key])
                p41.run(
                    "docker", "run", "-d", "--pull", "never",
                    "--name", names[key],
                    "--network", network,
                    "--network-alias", alias or key,
                    "--memory", memory,
                    "--memory-swap", memory,
                    "--cpus", "0.75",
                    "--pids-limit", "128",
                    "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges",
                    *options, images[image], *args,
                )

            def mount(path, target):
                return (
                    "--mount",
                    "type=bind,src=" + str(path) + ",dst=" + target + ",readonly",
                )

            start(
                "p3", "python", "128m",
                mount(fixtures, "/control"),
                ("python", "/control/p3.py", "metrics"),
            )
            start(
                "prom", "prom", "384m",
                mount(prom_config, "/fixture/prometheus.yml"),
                (
                    "--config.file=/fixture/prometheus.yml",
                    "--storage.tsdb.retention.time=1h",
                    "--storage.tsdb.retention.size=128MB",
                    "--query.timeout=5s",
                    "--query.max-concurrency=2",
                    "--query.max-samples=10000",
                ),
            )
            start(
                "grafana", "grafana", "384m",
                (
                    "-e", "GF_SECURITY_ADMIN_PASSWORD=" + admin_password,
                    "-e", "GF_AUTH_ANONYMOUS_ENABLED=false",
                    "-e", "GF_ANALYTICS_REPORTING_ENABLED=false",
                    "-e", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
                    "-e", "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false",
                ),
            )

            def address(key, port):
                item = json.loads(p41.run("docker", "inspect", names[key]))[0]
                if (
                    set(item["NetworkSettings"]["Networks"]) != {network}
                    or item["HostConfig"]["PortBindings"]
                ):
                    raise AssertionError("container network boundary")
                return (
                    "http://"
                    + item["NetworkSettings"]["Networks"][network]["IPAddress"]
                    + ":" + str(port)
                )

            prom = address("prom", 9090)
            grafana = address("grafana", 3000)
            p41.eventually(
                lambda: p41.api(grafana, "/api/health").get("database") == "ok",
                "grafana-ready",
            )
            p41.eventually(
                lambda: bool(p41.api(
                    prom,
                    "/api/v1/query?query="
                    + urllib.parse.quote(
                        'node_memory_MemAvailable_bytes{environment="synthetic",instance="fixture-node"}'
                    ),
                )["data"]["result"]),
                "synthetic-node-scrape",
            )
            p41.api(
                grafana,
                "/api/datasources",
                "POST",
                {
                    "name": "PRP P4.2 synthetic only",
                    "uid": UID,
                    "type": "prometheus",
                    "url": "http://prom:9090",
                    "access": "proxy",
                    "isDefault": True,
                },
                admin,
            )
            account = p41.api(
                grafana,
                "/api/serviceaccounts",
                "POST",
                {"name": "p42-owner-viewer", "role": "Viewer"},
                admin,
            )["id"]
            viewer_record = p41.api(
                grafana,
                f"/api/serviceaccounts/{account}/tokens",
                "POST",
                {"name": "p42-ephemeral", "secondsToLive": 600},
                admin,
            )
            viewer_token = viewer_record["key"]
            viewer_header = {"Authorization": "Bearer " + viewer_token}
            check(
                len(p41.api(grafana, "/api/datasources", headers=viewer_header)) == 1,
                "grafana-viewer-one-datasource",
            )
            write_status = p41.request(
                grafana,
                "/api/datasources",
                "POST",
                {"name": "forbidden", "type": "prometheus", "url": "http://prom:9090"},
                viewer_header,
            )[0]
            check(write_status in (401, 403), "grafana-viewer-write-denied")

            start(
                "mcp", "mcp", "256m",
                (
                    "-e", "GRAFANA_URL=http://grafana:3000",
                    "-e", "MCP_GRAFANA_SERVER_TOKEN=" + upstream_caller,
                    "-e", "GRAFANA_USAGE_STATS=disabled",
                ),
                (
                    "-t", "streamable-http",
                    "--address", "0.0.0.0:8000",
                    "--allowed-hosts", "mcp:8000",
                    "--enabled-tools", "prometheus",
                    "--disable-write",
                    "--disable-api",
                    "--disable-rendering",
                    "--disable-assistant",
                    "--require-user-credentials",
                    "--log-tool-calls",
                    "--prometheus-enforced-matchers", 'environment="synthetic"',
                    "--prometheus-guardrail-mode", "enforce",
                    "--prometheus-guardrail-max-range", "1h",
                    "--prometheus-guardrail-max-points", "120",
                ),
            )
            mcp_url = address("mcp", 8000)
            p41.eventually(
                lambda: p41.request(
                    mcp_url, "/healthz", headers={"Host": "mcp:8000"}
                )[0] in (200, 401),
                "official-grafana-mcp-ready",
            )
            upstream = p41.Client(mcp_url, upstream_caller, viewer_token)
            upstream.init()
            tools = upstream.rpc("tools/list", {})["result"]["tools"]
            names_found = {tool["name"] for tool in tools}
            check(
                "query_prometheus" in names_found
                and names_found <= {
                    "query_prometheus",
                    "query_prometheus_histogram",
                    "list_prometheus_metric_names",
                    "list_prometheus_metric_metadata",
                    "list_prometheus_label_names",
                    "list_prometheus_label_values",
                },
                "upstream-prometheus-readonly-toolset",
            )

            # Readiness at wall-clock now is insufficient: the fixed range
            # ends at a rounded-down evaluation instant. Prove that the exact
            # common endpoint already has real samples for every fixed metric.
            # Capture the successful endpoint itself, never a later clock read.
            ready = {}
            def aligned_metrics_ready():
                candidate = int(time.time())
                endpoint = candidate - candidate % 30
                for expr in QUERIES.values():
                    data = p41.api(prom, "/api/v1/query?" + urllib.parse.urlencode(
                        {"query": expr, "time": str(endpoint)}))
                    rows = data["data"]["result"]
                    if (data.get("status") != "success" or len(rows) != 1
                            or rows[0]["value"][0] != endpoint):
                        return False
                ready["now"] = endpoint
                return True

            p41.eventually(aligned_metrics_ready, "exact-aligned-metric-readiness", seconds=90)
            now = ready["now"]
            check(now % 30 == 0, "real-samples-at-fixed-window-end")
            revoked = {"value": False}
            revoke_after_query = {"value": False}
            fail_audit = {"value": False}
            revoke_on_audit = {"value": False}
            injected_audit_events = []
            injected_query_responses = []
            grant_id = str(uuid.uuid4())

            def grant():
                return parse_grant(json.dumps({
                    "version": 1,
                    "grantId": grant_id,
                    "issuer": ISSUER,
                    "resource": RESOURCE,
                    "client": CLIENT,
                    "subject": FIXTURE_PROFILE.subject,
                    "environment": "staging",
                    "scope": SCOPE,
                    "issuedAt": now - 20,
                    "expiresAt": now + 600,
                    "active": not revoked["value"],
                }).encode())

            def introspect(token):
                claims = {
                    "active": token == OWNER_TOKEN or token in (
                        "wrong-scope", "wrong-subject", "wrong-audience", "expired"
                    ),
                    "iss": ISSUER,
                    "sub": FIXTURE_PROFILE.subject,
                    "aud": [RESOURCE],
                    "client_id": CLIENT,
                    "scope": SCOPE,
                    "token_type": "Bearer",
                    "iat": now - 10,
                    "exp": now + 300,
                }
                if token == "wrong-scope":
                    claims["scope"] = "prp.tasks.read"
                elif token == "wrong-subject":
                    claims["sub"] = "another-subject"
                elif token == "wrong-audience":
                    claims["aud"] = ["https://other.invalid/mcp"]
                elif token == "expired":
                    claims["exp"] = now
                return json.dumps(claims).encode()

            grants = GrantFile(
                root / "grant-fixture",
                reader_gid=os.getegid(),
                owner_uid=os.geteuid(),
            )
            snapshot_dir = root / "snapshot"
            snapshot_dir.mkdir(mode=0o700)
            audit_dir = root / "audit"
            audit_dir.mkdir(mode=0o700)
            audit_file = audit_dir / AUDIT_NAME
            audit_file.touch(mode=0o600)
            audit_file.chmod(0o600)
            durable_audit = AuditStoreFixture(
                audit_dir, owner_uid=os.geteuid(), clock=lambda: now
            )

            class SwitchAudit:
                def __call__(self, event):
                    if fail_audit["value"] and event["outcome"] == "handled" and event["candidateStatus"] == 200:
                        fail_audit["value"] = False
                        injected_audit_events.append(dict(event))
                        return False
                    ok = durable_audit(event)
                    if ok and revoke_on_audit["value"] and event["outcome"] == "handled" and event["candidateStatus"] == 200:
                        injected_audit_events.append(dict(event))
                        revoke_on_audit["value"] = False
                        revoked["value"] = True
                    return ok

            audit = SwitchAudit()
            server = {
                "policy": Policy(True),
                "introspect": introspect,
                "grants": grants,
                "trusted_clock": lambda: now,
                "store": SnapshotStore(snapshot_dir),
            }
            upstream_calls = []

            def upstream_rpc(method, params):
                upstream_calls.append(json.loads(json.dumps({
                    "method": method, "params": params,
                })))
                response = upstream.rpc(method, params)
                if revoke_after_query["value"] and method == "tools/call" and not p41.failed(response):
                    injected_query_responses.append(response)
                    revoke_after_query["value"] = False
                    revoked["value"] = True
                return response

            adapter = FixedGrafanaQueryAdapter(
                upstream_rpc, datasource_uid=UID, clock=lambda: now
            )
            gateway = OwnerBoundGrafanaGateway(
                server=server,
                query_adapter=adapter,
                audit_sink=audit,
                budget=Budget(),
                disclosure_check=lambda: True,
            )

            with patch.object(grants, "current", side_effect=grant):
                app = build_app(gateway, server)
                with TestClient(app, base_url="https://ops.invalid") as client:
                    def post(method, params=None, token=OWNER_TOKEN, request_id=1):
                        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
                        if params is not None:
                            message["params"] = params
                        headers = {
                            "Host": "ops.invalid",
                            "Accept": "application/json, text/event-stream",
                            "Content-Type": "application/json",
                        }
                        if token is not None:
                            headers["Authorization"] = "Bearer " + token
                        if method != "initialize":
                            headers["MCP-Protocol-Version"] = "2025-06-18"
                        return client.post("/mcp", json=message, headers=headers)

                    missing = post("tools/list", {}, token=None)
                    check(missing.status_code == 401, "missing-owner-bearer-denied")
                    for token in ("wrong-scope", "wrong-subject", "wrong-audience", "expired"):
                        denied = post("tools/list", {}, token=token)
                        check(denied.status_code >= 400, "owner-identity-denied-" + token)

                    initialized = post(
                        "initialize",
                        {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "p42-ci", "version": "1"},
                        },
                    )
                    check(
                        initialized.status_code == 200
                        and initialized.json()["result"]["protocolVersion"] == "2025-06-18",
                        "owner-gateway-sdk-initialize",
                    )
                    notify = client.post(
                        "/mcp",
                        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                        headers={
                            "Host": "ops.invalid",
                            "Accept": "application/json, text/event-stream",
                            "Content-Type": "application/json",
                            "Authorization": "Bearer " + OWNER_TOKEN,
                            "MCP-Protocol-Version": "2025-06-18",
                        },
                    )
                    check(notify.status_code in (200, 202), "owner-gateway-initialized")

                    listed = post("tools/list", {}, request_id=2)
                    exposed = listed.json()["result"]["tools"]
                    check(len(exposed) == 1 and exposed[0]["name"] == TOOL_NAME,
                          "single-fixed-owner-tool")
                    schema = exposed[0]["inputSchema"]
                    check(
                        schema["additionalProperties"] is False
                        and set(schema["properties"]) == {"metric", "window"}
                        and set(schema["required"]) == {"metric", "window"},
                        "strict-no-arbitrary-query-schema",
                    )

                    request_id = 3
                    for metric in QUERIES:
                        request_id += 1
                        response = post(
                            "tools/call",
                            {"name": TOOL_NAME, "arguments": {"metric": metric, "window": "5m"}},
                            request_id=request_id,
                        )
                        check(response.status_code == 200, "fixed-query-" + metric)
                        result = response.json()["result"]
                        payload = result["structuredContent"]
                        check(
                            result["isError"] is False
                            and payload["metric"] == metric
                            and payload["window"] == "5m"
                            and payload["status"] == "available"
                            and 0 < len(payload["samples"]) <= 61
                            and payload["samples"][-1][0] == now
                            and set(payload) == {"metric", "window", "startAt", "endAt", "stepSeconds", "status", "samples"},
                            "bounded-result-" + metric,
                        )
                        args = upstream_calls[-1]["params"]["arguments"]
                        check(
                            upstream_calls[-1]["params"]["name"] == "query_prometheus"
                            and args == {
                                "datasourceUid": UID,
                                "expr": QUERIES[metric],
                                "queryType": "range",
                                "startTime": utc(now - now % 5 - 300),
                                "endTime": utc(now - now % 5),
                                "stepSeconds": 5,
                            },
                            "server-fixed-promql-and-window-" + metric,
                        )

                    for window, expected_step in (("15m", 15), ("30m", 30)):
                        request_id += 1
                        response = post(
                            "tools/call",
                            {"name": TOOL_NAME, "arguments": {
                                "metric": "memory_available_bytes", "window": window,
                            }},
                            request_id=request_id,
                        )
                        check(
                            response.status_code == 200
                            and response.json()["result"]["isError"] is False,
                            "bounded-window-" + window,
                        )
                        args = upstream_calls[-1]["params"]["arguments"]
                        check(
                            args["startTime"] == utc(now - now % expected_step - WINDOWS[window][0])
                            and args["endTime"] == utc(now - now % expected_step)
                            and args["stepSeconds"] == expected_step
                            and args["datasourceUid"] == UID
                            and args["expr"] == QUERIES["memory_available_bytes"],
                            "fixed-time-range-" + window,
                        )

                    calls_before = len(upstream_calls)
                    duplicate = client.post("/mcp", json={"jsonrpc":"2.0","id":99,"method":"tools/call","params":{"name":TOOL_NAME,"arguments":{"metric":"memory_available_bytes","window":"5m"}}}, headers=[("Authorization","Bearer "+OWNER_TOKEN),("Authorization","Bearer other"),("Accept","application/json, text/event-stream")])
                    check(duplicate.status_code == 400, "duplicate-authorization-denied")
                    for bad_args in (
                        {"metric": "memory_available_bytes", "window": "5m", "expr": "up"},
                        {"metric": "memory_available_bytes", "window": "2h"},
                        {"metric": "memory_available_bytes", "window": "5m", "offset": "2h"},
                        {"metric": "memory_available_bytes", "window": "5m", "startTime": "2020-01-01T00:00:00Z"},
                        {"metric": "memory_available_bytes", "window": "5m", "datasourceUid": "other"},
                        {"metric": "up", "window": "5m"},
                        {"metric": "memory_available_bytes", "window": "now-1d"},
                    ):
                        request_id += 1
                        denied = post(
                            "tools/call",
                            {"name": TOOL_NAME, "arguments": bad_args},
                            request_id=request_id,
                        )
                        check(
                            denied.status_code == 200
                            and (denied.json().get("result", {}).get("isError") is True or denied.json().get("error") is not None),
                            "invalid-query-arguments-denied",
                        )
                    check(len(upstream_calls) == calls_before, "invalid-args-no-downstream-call")

                    def receipts():
                        return [json.loads(line) for line in audit_file.read_text().splitlines()]

                    def denied_without_data(response):
                        value = response.json().get("result", {})
                        return (response.status_code == 200
                                and value.get("isError") is True
                                and "structuredContent" not in value
                                and "samples" not in response.text)

                    fixed = {"name": TOOL_NAME, "arguments": {
                        "metric": "memory_available_bytes", "window": "5m",
                    }}
                    calls_before = len(upstream_calls)
                    rows_before = len(receipts())
                    hook_before = len(injected_audit_events)
                    fail_audit["value"] = True
                    request_id += 1
                    audit_failed = post("tools/call", fixed, request_id=request_id)
                    check(denied_without_data(audit_failed), "audit-failure-denies-disclosure")
                    check(not fail_audit["value"] and len(injected_audit_events) == hook_before + 1
                          and injected_audit_events[-1]["candidateStatus"] == 200
                          and injected_audit_events[-1]["outcome"] == "handled"
                          and len(upstream_calls) == calls_before + 1
                          and len(receipts()) == rows_before,
                          "audit-failure-hook-consumed-after-successful-query")

                    calls_before = len(upstream_calls)
                    rows_before = len(receipts())
                    hook_before = len(injected_audit_events)
                    revoke_on_audit["value"] = True
                    request_id += 1
                    raced = post("tools/call", fixed, request_id=request_id)
                    check(denied_without_data(raced), "owner-revocation-during-audit-denies-result")
                    check(not revoke_on_audit["value"] and revoked["value"]
                          and len(injected_audit_events) == hook_before + 1
                          and len(upstream_calls) == calls_before + 1,
                          "audit-race-hook-consumed-after-successful-query")
                    pair = receipts()[rows_before:]
                    check(len(pair) == 2
                          and [row["outcome"] for row in pair] == ["handled", "denied"]
                          and [row["candidateStatus"] for row in pair] == [200, 401]
                          and pair[0]["traceId"] == pair[1]["traceId"] == injected_audit_events[-1]["traceId"],
                          "audit-race-correlated-handled-denied-receipts")

                    revoked["value"] = False  # reset only the independent synthetic fixture
                    calls_before = len(upstream_calls)
                    rows_before = len(receipts())
                    hook_before = len(injected_query_responses)
                    revoke_after_query["value"] = True
                    request_id += 1
                    revoked_during_query = post("tools/call", fixed, request_id=request_id)
                    check(denied_without_data(revoked_during_query), "owner-revocation-during-query-denies-result")
                    check(not revoke_after_query["value"] and revoked["value"]
                          and len(injected_query_responses) == hook_before + 1
                          and len(upstream_calls) == calls_before + 1,
                          "query-race-hook-consumed-after-upstream-success")
                    new_rows = receipts()[rows_before:]
                    check(len(new_rows) == 1 and new_rows[0]["candidateStatus"] == 401
                          and new_rows[0]["outcome"] == "denied",
                          "query-race-authoritative-grant-denial-receipt")

                    calls_before = len(upstream_calls)
                    request_id += 1
                    after_revoke = post(
                        "tools/call",
                        {"name": TOOL_NAME, "arguments": {
                            "metric": "memory_available_bytes", "window": "5m",
                        }},
                        request_id=request_id,
                    )
                    check(
                        after_revoke.status_code >= 400
                        or after_revoke.json().get("result", {}).get("isError") is True,
                        "owner-revocation-next-request-denied",
                    )
                    check(len(upstream_calls) == calls_before,
                          "revoked-owner-no-downstream-call")

            rows = [
                json.loads(line)
                for line in audit_file.read_text().splitlines()
                if line.strip()
            ]
            audit_text = audit_file.read_text()
            check(
                any(row["outcome"] == "handled" for row in rows)
                and any(row["outcome"] == "denied" for row in rows),
                "durable-owner-audit-success-and-denial",
            )
            check(
                all(set(row) == {
                    "version", "traceId", "route", "candidateStatus", "outcome", "recordedAt"
                } for row in rows),
                "audit-minimal-schema",
            )
            check(
                all(secret not in audit_text for secret in (
                    OWNER_TOKEN, upstream_caller, viewer_token, admin_password,
                    "node_memory_MemAvailable_bytes", "cpu_busy_percent", "now-5m",
                    "fixture-node", "foreign-marker",
                )),
                "audit-no-identity-query-or-metric-data",
            )
            check(
                p41.run("docker", "network", "inspect", "--format", "{{.Internal}}", network) == "true",
                "internal-only-network",
            )
            for name in created:
                item = json.loads(p41.run("docker", "inspect", name))[0]
                check(not item["HostConfig"]["PortBindings"], "no-published-port-" + name)
            print(
                "OBS_P42_INTEGRATION=PASS; LIVE_OAUTH_TUNNEL_REAL_DATA=NOT_ENABLED",
                flush=True,
            )
        finally:
            for name in reversed(created):
                __import__("subprocess").run(["docker", "rm", "-f", "-v", name], capture_output=True, timeout=30)
            __import__("subprocess").run(["docker", "network", "rm", network], capture_output=True, timeout=30)


if __name__ == "__main__":
    main()
