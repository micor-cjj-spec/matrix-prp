#!/usr/bin/env python3
"""Read-only unauthenticated HTTPS staging preflight.

Verifies RFC 9728 metadata/challenge and canonical public endpoint wiring
without leaking credentials or touching user data. Never modifies a server.
"""
import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

STAGING_RESOURCE = "https://prp-test.micor.top/api/mcp"
STAGING_ISSUER = "https://auth-test.micor.top/realms/prp-mcp"
STAGING_METADATA = "https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp"


class RedirectForbidden(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RedirectForbidden("OAuth/MCP preflight forbids endpoint redirects")


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
    if metadata.get("scopes_supported") != ["prp.tasks.read"]:
        raise ValueError("Task-only advertised scopes required before ChatGPT linking")

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
    if (uri == STAGING_METADATA and method == "GET" and body is None):
        pass
    elif (uri == STAGING_RESOURCE and method == "POST"
          and isinstance(body, dict)
          and body.get("method") == "initialize"
          and body.get("jsonrpc") == "2.0"):
        pass
    else:
        raise ValueError("Fixed staging URL and GET metadata / POST initialize only")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.update({"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    request = Request(uri, data=data, headers=headers, method=method)
    # Avoid inherited system proxies, implicit redirects, or disabled TLS
    # verification. Use the external GitHub runner's direct HTTPS path.
    opener = build_opener(
        ProxyHandler({}), NoRedirect(),
        HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(request, timeout=9)
    except HTTPError as err:
        response = err
    except (OSError, URLError, TimeoutError):
        raise ValueError("External staging HTTPS transport unverified") from None
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
        document = json.loads(content)
        if not isinstance(document, dict):
            raise ValueError("OAuth resource metadata must be a JSON object")
        return status, headers_out, document


def main():
    parser = argparse.ArgumentParser(description="Read-only OAuth and Nginx HTTPS staging preflight")
    parser.add_argument("--resource", required=True)
    parser.add_argument("--issuer", required=True)
    args = parser.parse_args()
    if args.resource != STAGING_RESOURCE or args.issuer != STAGING_ISSUER:
        parser.error("Only fixed PRP test environment can be probed externally")
    outcome = inspect(args.resource, args.issuer, https_fetch)
    print(json.dumps(outcome, indent=2))
    print("Public OAuth discovery and unauthenticated denial passed; no login/token/tool data checked.")


if __name__ == "__main__":
    main()
