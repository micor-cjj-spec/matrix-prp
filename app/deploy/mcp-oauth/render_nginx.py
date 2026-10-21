#!/usr/bin/env python3
"""Generate *review-only* HTTPS Nginx locations for PRP MCP, never install them.

PRP Web uses /prp/. The backend serves /api/ without the /prp/ prefix.
The output belongs INSIDE an existing trusted HTTPS server block and must
never be pasted into an unrestricted/default server.
"""
import argparse
import ipaddress
import re
from pathlib import Path


def public_host(host):
    if not isinstance(host, str) or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host):
        raise ValueError("HTTPS public Host must be a DNS name, not a URL or header expression")
    if host.startswith(".") or ".." in host or "." not in host or host.lower() == "localhost":
        raise ValueError("Use an explicit externally owned DNS name")
    try:
        ipaddress.ip_address(host)
        raise ValueError("Use an HTTPS hostname rather than an IP literal")
    except ValueError as error:
        if str(error).startswith("Use an HTTPS hostname"):
            raise
    for label in host.split("."):
        if not 1 <= len(label) <= 63 or label.startswith("-") or label.endswith("-"):
            raise ValueError("Malformed HTTPS public hostname")
    return host.lower()


def render(host):
    host = public_host(host)
    locations = [
        "/.well-known/oauth-protected-resource/api/mcp",
        "/api/mcp",
        "/api/mcp/link",
    ]
    chunks = [
        "# Generated PRP OAuth/MCP Nginx location snippet.",
        "# Review in the existing TLS server_name " + host + " block.",
        "# Reject other Host values using the existing default_server (return 421/444).",
        "# Upstream Java stays bound to 127.0.0.1:11000; no /prp/ API prefix.",
        "# Keep the existing /api/ and /prp/ locations untouched.",
        "",
    ]
    for path in locations:
        chunks.extend([
            "location = " + path + " {",
            "    if ($host != " + host + ") { return 421; }",
            "    limit_except GET POST { deny all; }" if path.endswith("/api/mcp") else
                "    limit_except GET { deny all; }" if path.startswith("/.well-known/") else
                "    limit_except POST { deny all; }",
            "    proxy_pass http://127.0.0.1:11000;",
            "    proxy_http_version 1.1;",
            "    proxy_set_header Host " + host + ";",
            "    proxy_set_header X-Forwarded-Host " + host + ";",
            "    proxy_set_header X-Forwarded-Proto https;",
            "    proxy_set_header X-Forwarded-For $remote_addr;",
            "    proxy_set_header Connection \"\";",
            "    proxy_cache off;",
            "    proxy_buffering off;",
            "    proxy_read_timeout 75s;",
            "    client_max_body_size 128k;",
            "    add_header Cache-Control \"no-store\" always;",
            "}",
            "",
        ])
    return "\n".join(chunks)


def main():
    parser = argparse.ArgumentParser(description="Render read-only Nginx MCP/OAuth path contract")
    parser.add_argument("--host", required=True, help="The DNS host from the actual HTTPS resource URL")
    parser.add_argument("--output", help="Optional output path for review-only Nginx snippet")
    args = parser.parse_args()
    source = render(args.host)
    if args.output:
        out = Path(args.output)
        if out.exists():
            raise SystemExit("Refusing to overwrite existing Nginx snippet")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(source, encoding="utf-8")
        print("Generated review-only Nginx snippet: " + str(out))
    else:
        print(source)


if __name__ == "__main__":
    main()
