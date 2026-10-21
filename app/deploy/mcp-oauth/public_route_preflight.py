#!/usr/bin/env python3
"""Read-only unauthenticated HTTPS staging preflight.

Verifies RFC 9728 metadata/challenge and canonical public endpoint wiring
without leaking credentials or touching user data. Never modifies a server.
"""
import argparse
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def canonical_resource(value):
    if not isinstance(value, str):
        raise ValueError("MCP resource must be an explicit HTTPS URL")
    uri = urlsplit(value)
    if (uri.scheme != "https" or not uri.hostname or uri.username or uri.password
            or uri.port not in (None, 443) or uri.query or uri.fragment
            or uri.path != "/api/mcp"):
        raise ValueError("PRP MCP must be published at https://<host>/api/mcp")
    if uri.hostname in ("micor.top", "www.micor.top"):
        raise ValueError("Refusing production PRP domain; staging only")
    return value.rstrip("/")


def metadata_uri(resource):
    value = canonical_resource(resource)
    uri = urlsplit(value)
    return uri.scheme + "://" + uri.netloc + "/.well-known/oauth-protected-resource/api/mcp"


def inspect(resource, issuer, fetch):
    expected = canonical_resource(resource)
    if not issuer.startswith("https://") or urlsplit(issuer).query or urlsplit(issuer).fragment:
        raise ValueError("Explicit HTTPS OAuth issuer required")
    well_known = metadata_uri(expected)
    metadata_status, metadata_headers, metadata = fetch(well_known, "GET", None)
    if metadata_status != 200 or metadata_headers.get("content-type", "").split(";")[0] != "application/json":
        raise ValueError("Protected resource metadata must be public JSON (200)")
    if metadata.get("resource") != expected:
        raise ValueError("Advertised resource disagrees with request URL")
    if metadata.get("authorization_servers") != [issuer]:
        raise ValueError("Unexpected OAuth authorization server")
    if metadata.get("bearer_methods_supported") != ["header"]:
        raise ValueError("Bearer scheme is not an HTTP header")
    if "prp.tasks.read" not in metadata.get("scopes_supported", []):
        raise ValueError("Expected PRP task scope is absent")

    status, headers, _ = fetch(expected, "POST",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "prp-unauth-preflight", "version": "1.0"}}})
    if status != 401:
        raise ValueError("Unauthenticated MCP initialize must fail with HTTP 401")
    challenge = headers.get("www-authenticate", "")
    if not challenge.startswith("Bearer ") or 'resource_metadata="' + well_known + '"' not in challenge:
        raise ValueError("MCP OAuth challenge must reference the exact resource metadata URL")
    return {"resource": expected, "issuer": issuer,
            "metadata_public": True, "unauthenticated_mcp_denied": True}


def https_fetch(uri, method, body):
    if urlsplit(uri).scheme != "https":
        raise ValueError("Network preflight cannot fetch insecure URLs")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.update({"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    request = Request(uri, data=data, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=9)
    except HTTPError as err:
        response = err
    with response:
        # Do not silently follow a redirect to a different or insecure
        # endpoint: metadata and the MCP resource are exact public URLs.
        if response.geturl() != uri:
            raise ValueError("OAuth/MCP preflight forbids endpoint redirects")
        status = response.status
        headers_out = {k.lower(): v for k, v in response.headers.items()}
        # Error bodies may contain environment details; never consume or print them.
        if status != 200 or body is not None:
            return status, headers_out, {}
        content = response.read(100001)
        if len(content) > 100000:
            raise ValueError("Metadata size limit exceeded")
        return status, headers_out, json.loads(content)


def main():
    parser = argparse.ArgumentParser(description="Read-only OAuth and Nginx HTTPS staging preflight")
    parser.add_argument("--resource", required=True)
    parser.add_argument("--issuer", required=True)
    args = parser.parse_args()
    outcome = inspect(args.resource, args.issuer, https_fetch)
    print(json.dumps(outcome, indent=2))
    print("Public OAuth discovery and unauthenticated denial passed; no login/token/tool data checked.")


if __name__ == "__main__":
    main()
