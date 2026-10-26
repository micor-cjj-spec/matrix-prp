#!/usr/bin/env python3
"""Validate a staging-only configuration BEFORE Compose can start.

Read-only. Passwords are checked for presence/length but never printed.
"""
import argparse
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit


REQUIRED = (
    "PRP_STAGE_PUBLIC_HOST", "PRP_STAGE_PUBLIC_URL", "PRP_STAGE_MCP_RESOURCE",
    "PRP_STAGE_AUTH_PUBLIC_URL", "PRP_STAGE_AUTH_ISSUER", "PRP_STAGE_AUTH_JWKS_URI",
    "PRP_STAGE_DB_ROOT_PASSWORD", "PRP_STAGE_DB_PASSWORD", "PRP_STAGE_JWT_SECRET",
    "PRP_STAGE_ADMIN_USERNAME", "PRP_STAGE_ADMIN_PASSWORD",
    "PRP_STAGE_MCP_ENABLED", "PRP_STAGE_OAUTH_ENABLED",
)


def parse_env(source):
    entries = {}
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if not match:
            raise ValueError("Invalid .env line or unsupported shell expansion")
        key, value = match.groups()
        if key in entries:
            raise ValueError("Duplicate staging environment variable")
        if not value or any(c in value for c in ("\r", "\n", "\0", "`", "$")):
            raise ValueError("Empty or unsafe staging configuration value")
        entries[key] = value
    return entries


def canonical_url(value, expected_path, label):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.port not in (None, 443) or
            parsed.query or parsed.fragment or parsed.path != expected_path or
            value.endswith("/") != expected_path.endswith("/")):
        raise ValueError(label + " must be an exact HTTPS URL")
    return parsed.hostname.lower()


def staging_dns_host(host, label):
    """Ensure DNS values are safe to interpolate into an Nginx config."""
    if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9.-]{4,253}", host):
        raise ValueError(label + " must be a lowercase staging DNS name")
    if "." not in host or ".." in host or host.startswith(".") or host.endswith("."):
        raise ValueError(label + " must be an explicit staging DNS name")
    if host in ("micor.top", "www.micor.top", "localhost"):
        raise ValueError(label + " must be non-production DNS")
    for part in host.split("."):
        if not 1 <= len(part) <= 63 or part.startswith("-") or part.endswith("-"):
            raise ValueError(label + " has an invalid DNS label")
    # A literal IP is not a managed, isolated DNS hostname.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError(label + " must be a DNS name, not an IP address")
    return host


def check(config):
    missing = [k for k in REQUIRED if k not in config]
    if missing:
        raise ValueError("Missing required staging settings: " + ", ".join(missing))
    host = config["PRP_STAGE_PUBLIC_HOST"].lower()
    if (host != config["PRP_STAGE_PUBLIC_HOST"] or
            not re.fullmatch(r"[a-z0-9.-]{4,253}", host) or
            ".." in host or "." not in host or host in ("micor.top", "www.micor.top")):
        raise ValueError("Staging public hostname must be non-production DNS")
    if host.split(".")[0] in ("www", "api") and host.endswith(".micor.top"):
        raise ValueError("Do not reuse existing PRP live subdomains")
    for label in host.split("."):
        if not label or len(label) > 63 or label[0] == "-" or label[-1] == "-":
            raise ValueError("Invalid staging DNS hostname")
    if canonical_url(config["PRP_STAGE_PUBLIC_URL"], "", "staging public URL") != host:
        raise ValueError("PRP public host differs from public URL")
    if canonical_url(config["PRP_STAGE_MCP_RESOURCE"], "/api/mcp", "MCP resource") != host:
        raise ValueError("MCP resource must be on the exact staging public hostname")
    staging_dns_host(host, "PRP staging")
    auth_host = canonical_url(config["PRP_STAGE_AUTH_PUBLIC_URL"], "", "OAuth public URL")
    staging_dns_host(auth_host, "OAuth staging")
    if auth_host == host:
        raise ValueError("OAuth issuer must use a separate non-production hostname")
    if canonical_url(config["PRP_STAGE_AUTH_ISSUER"], "/realms/prp-mcp", "OAuth issuer") != auth_host:
        raise ValueError("Issuer must be exactly the staged Keycloak realm")
    if canonical_url(config["PRP_STAGE_AUTH_JWKS_URI"],
                     "/realms/prp-mcp/protocol/openid-connect/certs", "JWKS") != auth_host:
        raise ValueError("JWKS URI must belong to the exact staged Keycloak issuer")
    if config["PRP_STAGE_MCP_ENABLED"] not in ("true", "false") or config["PRP_STAGE_OAUTH_ENABLED"] not in ("true", "false"):
        raise ValueError("Feature flags must use literal true or false")
    if config["PRP_STAGE_MCP_ENABLED"] == "true" and config["PRP_STAGE_OAUTH_ENABLED"] != "true":
        raise ValueError("Staging MCP cannot activate without OAuth")
    if config["PRP_STAGE_OAUTH_ENABLED"] == "true" and config["PRP_STAGE_MCP_ENABLED"] != "true":
        raise ValueError("Staging OAuth requires MCP")
    secret_keys = ("PRP_STAGE_DB_ROOT_PASSWORD", "PRP_STAGE_DB_PASSWORD",
                   "PRP_STAGE_JWT_SECRET", "PRP_STAGE_ADMIN_PASSWORD")
    for key in secret_keys:
        value = config[key]
        if len(value) < 24 or "REPLACE" in value.upper() or "PASSWORD" in value.upper():
            raise ValueError(key + ": use a unique generated secret; example values are forbidden")
    if len(set(config[k] for k in secret_keys)) != len(secret_keys):
        raise ValueError("Do not reuse a secret between staging services")
    if not re.fullmatch(r"[a-zA-Z0-9_]{3,32}", config["PRP_STAGE_ADMIN_USERNAME"]):
        raise ValueError("Invalid staging admin username")
    return {
        "stage_host": host,
        "oauth_host": auth_host,
        "mcp_enabled": config["PRP_STAGE_MCP_ENABLED"] == "true",
        "oauth_enabled": config["PRP_STAGE_OAUTH_ENABLED"] == "true",
        "production_host_excluded": True,
    }


def main():
    parser = argparse.ArgumentParser(description="PRP isolated MCP staging configuration gate")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    args = parser.parse_args()
    checked = check(parse_env(args.env_file.read_text(encoding="utf-8")))
    print("PASS: staging configuration isolated from production DNS and credentials.")
    print("MCP/OAuth feature flags:", checked["mcp_enabled"], checked["oauth_enabled"])
    print("Secrets deliberately omitted from output.")


if __name__ == "__main__":
    main()
