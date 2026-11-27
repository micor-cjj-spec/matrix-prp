"""Deterministic minimal adaptation of exact accepted source, offline only.

No modification to accepted PRs. Generate reviewable candidate modules in a
disposable directory; never install them or change real configuration.
"""
import hashlib
from pathlib import Path
import sys

GATEWAY_BLOB = "9898d0102fb75bf538a1eadfea5c25dbb300e826"
RUNTIME_BLOB = "a8442994f4e52ba6b5189d9ddeb60f0c4b019b57"


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("accepted source anchor mismatch")
    return source.replace(before, after)


def materialize(gateway_path, runtime_path, destination):
    gateway_raw = Path(gateway_path).read_bytes()
    runtime_raw = Path(runtime_path).read_bytes()
    if git_blob(gateway_raw) != GATEWAY_BLOB or git_blob(runtime_raw) != RUNTIME_BLOB:
        raise ValueError("accepted source blob mismatch")
    g = gateway_raw.decode("utf-8")
    g = replace_once(g, "def build_app(gateway, server):",
        "def build_app(gateway, server, *, approved=None):")
    g = replace_once(g,
        '    if profile != FIXTURE_PROFILE:\n        raise ValueError("only the offline fixture profile is supported")',
        '''    from profile_config import ApprovedProfile
    from urllib.parse import urlsplit
    if profile == FIXTURE_PROFILE:
        if approved is not None:
            raise ValueError("fixture cannot use live approval")
    elif type(approved) is not ApprovedProfile or approved.identity != profile:
        raise ValueError("approved identity required")
    if gateway._server != server:
        raise ValueError("identity configuration mismatch")
    host = urlsplit(profile.resource).netloc''')
    g = replace_once(g, 'allowed_hosts=["ops.invalid"],', 'allowed_hosts=[host],')
    # #494 transport remains unchanged apart from a fixed server-owned host.
    rt = runtime_raw.decode("utf-8")
    rt = replace_once(rt, 'def __init__(self, app, enabled):\n        self.app, self.enabled = app, enabled',
        '''def __init__(self, app, enabled, *, host="ops.invalid"):
        self.app, self.enabled = app, enabled
        self.host = host''')
    rt = replace_once(rt, 'headers.get("host") != "ops.invalid"', 'headers.get("host") != self.host')
    # Exclude synthetic launcher and credentials from the profile candidate.
    # Keep only the actual bounded transport classes and their fixed imports.
    start = rt.index("class RequestRejected(ValueError):")
    end = rt.index("\ndef main():", start)
    bounded = '''"""Exact #494 bounded SDK transport with server-pinned host."""
import asyncio
from asgi_runtime import extract_scope, send_response, MAX_BODY_EVENTS, SEND_SECONDS
from http_boundary import parse_headers, response, MAX_RESPONSE, CONCURRENCY
from query_contract import require
from rpc_adapter import MAX_RPC
DEADLINE = 8

''' + rt[start:end]
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "owner_gateway.py").write_text(g)
    (dest / "bounded_sdk.py").write_text(bounded)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(2)
    materialize(*sys.argv[1:])
