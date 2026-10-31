#!/usr/bin/env python3
"""Read-only public DNS/TLS/OAuth discovery probe. No credentials or writes.

Prints fixed status categories only. Does not contact admin APIs or send tokens.
Exit status 0 means observations were collected, NOT that deployment is approved.
"""
import json
import socket
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

HOSTS = ("auth-test.micor.top", "prp-test.micor.top")
URLS = {
    "issuer_discovery": "https://auth-test.micor.top/realms/prp-mcp/.well-known/openid-configuration",
    "protected_resource": "https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp",
    "protected_resource_root": "https://prp-test.micor.top/.well-known/oauth-protected-resource",
}
EXPECTED_ISSUER = "https://auth-test.micor.top/realms/prp-mcp"
EXPECTED_RESOURCE = "https://prp-test.micor.top/api/mcp"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        return None

def classify_json(name, document):
    if not isinstance(document, dict):
        return "INVALID_JSON_SHAPE"
    if name == "issuer_discovery":
        if document.get("issuer") != EXPECTED_ISSUER:
            return "ISSUER_MISMATCH"
        endpoints = ("authorization_endpoint", "token_endpoint", "jwks_uri")
        if not all(isinstance(document.get(k), str)
                   and document[k].startswith(EXPECTED_ISSUER + "/") for k in endpoints):
            return "ISSUER_ENDPOINT_MISMATCH"
        return "METADATA_MATCH"
    if document.get("resource") != EXPECTED_RESOURCE:
        return "RESOURCE_MISMATCH"
    servers = document.get("authorization_servers")
    if not isinstance(servers, list) or EXPECTED_ISSUER not in servers:
        return "AUTHORIZATION_SERVER_MISMATCH"
    return "METADATA_MATCH"

def probe_dns(host):
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return "RESOLVED" if records else "NO_RECORDS"
    except (socket.gaierror, OSError):
        return "DNS_UNAVAILABLE"

def probe_tls(host):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                return "TRUSTED_TLS" if tls.version() else "TLS_UNVERIFIED"
    except (OSError, ssl.SSLError):
        return "TLS_UNAVAILABLE_OR_UNTRUSTED"

def probe_metadata(name, url):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or parts.password:
        return "REFUSED_NON_ALLOWLIST_URL"
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(url, headers={"Accept": "application/json"}), timeout=8) as response:
            if response.status != 200:
                return "HTTP_NON_200"
            if response.headers.get_content_type() != "application/json":
                return "INVALID_CONTENT_TYPE"
            body = response.read(65537)
            if len(body) > 65536:
                return "OVERSIZE_RESPONSE"
            return classify_json(name, json.loads(body))
    except HTTPError as exc:
        return "HTTP_" + str(exc.code)
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return "HTTP_OR_JSON_UNAVAILABLE"

def main():
    findings = {"mode": "READ_ONLY_PUBLIC_NO_GO",
                "dns": {host: probe_dns(host) for host in HOSTS},
                "tls": {host: probe_tls(host) for host in HOSTS},
                "discovery": {name: probe_metadata(name, url)
                              for name, url in URLS.items()},
                "real_chatgpt_signature_verified": False,
                "production_change_authorized": False}
    print(json.dumps(findings, sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
