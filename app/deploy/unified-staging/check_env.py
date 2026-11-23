#!/usr/bin/env python3
"""Offline-only, fail-closed validation of unified Staging review configuration.

Parses an operator-local .env file but NEVER prints passwords or host identity.
Success is NOT proof of DNS, TLS, host isolation, approval or deployment.
"""
import argparse
import json
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

KEYS = frozenset({
    "PRP_UNIFIED_PUBLIC_HOST", "PRP_UNIFIED_PUBLIC_URL",
    "PRP_UNIFIED_AUTH_ISSUER", "PRP_UNIFIED_LOOPBACK_PORT",
    "PRP_UNIFIED_DB_ROOT_PASSWORD", "PRP_UNIFIED_DB_PASSWORD",
    "PRP_UNIFIED_JWT_SECRET", "PRP_UNIFIED_BOOTSTRAP_USERNAME",
    "PRP_UNIFIED_BOOTSTRAP_PASSWORD",
})
PROTECTED_HOSTS = frozenset({
    "micor.top", "www.micor.top", "auth.micor.top",
    "prp-test.micor.top", "auth-test.micor.top", "prp.micor.top",
})
PROTECTED_PORTS = frozenset({11000, 18081, 18082, 18083})
SECRET_KEYS = (
    "PRP_UNIFIED_DB_ROOT_PASSWORD", "PRP_UNIFIED_DB_PASSWORD",
    "PRP_UNIFIED_JWT_SECRET", "PRP_UNIFIED_BOOTSTRAP_PASSWORD",
)


def parse_env(source):
    values = {}
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=([^\\s\\x00\\r\\n]*)", stripped)
        if not match:
            raise ValueError("INVALID_ENV_ENTRY")
        key, value = match.groups()
        if key in values:
            raise ValueError("DUPLICATE_ENV_KEY")
        values[key] = value
    return values


def valid_dns_host(value):
    if not isinstance(value, str) or len(value) > 253 or value.lower() != value:
        return False
    if value in PROTECTED_HOSTS or value.endswith(".localhost") or value.endswith(".local"):
        return False
    if not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?){2,}", value):
        return False
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        pass
    return all(len(label) <= 63 for label in value.split("."))


def strict_https(value, path=""):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port is not None
            or parsed.path != path or not parsed.hostname):
        raise ValueError("INVALID_HTTPS_URL")
    if value != ("https://" + parsed.hostname + path):
        raise ValueError("NONCANONICAL_HTTPS_URL")
    return parsed.hostname


def check(values):
    if set(values) != KEYS:
        raise ValueError("REQUIRED_STAGE_KEYS_MISSING_OR_EXTRA")
    host = values["PRP_UNIFIED_PUBLIC_HOST"]
    if not valid_dns_host(host):
        raise ValueError("UNSAFE_STAGE_HOST")
    if strict_https(values["PRP_UNIFIED_PUBLIC_URL"]) != host:
        raise ValueError("PUBLIC_HOST_MISMATCH")

    issuer = values["PRP_UNIFIED_AUTH_ISSUER"]
    issuer_host = strict_https(issuer, "/realms/prp-unified")
    if not valid_dns_host(issuer_host) or issuer_host == host:
        raise ValueError("UNSAFE_STAGE_ISSUER")
    if not re.fullmatch(r"[0-9]{4,5}", values["PRP_UNIFIED_LOOPBACK_PORT"]):
        raise ValueError("INVALID_STAGE_PORT")
    port = int(values["PRP_UNIFIED_LOOPBACK_PORT"])
    if port < 20000 or port > 60000 or port in PROTECTED_PORTS:
        raise ValueError("UNREVIEWED_STAGE_PORT")

    secrets = [values[key] for key in SECRET_KEYS]
    if any(not re.fullmatch(r"[0-9a-f]{64}", s) or len(set(s)) < 8
           for s in secrets) or len(set(secrets)) != len(secrets):
        raise ValueError("INVALID_OR_REUSED_STAGE_SECRETS")
    username = values["PRP_UNIFIED_BOOTSTRAP_USERNAME"]
    if (not re.fullmatch(r"[a-z][a-z0-9_]{3,31}", username)
            or username in ("root", "admin", "matrix_prp", "cosmic")):
        raise ValueError("INVALID_SYNTHETIC_OWNER")
    return {
        "schema_version": 1,
        "config_shape": "VALID_FOR_STATIC_REVIEW_ONLY",
        "app_and_auth_hosts_distinct": True,
        "stage_secrets_distinct_format_validated": True,
        "review_port_in_config_range": True,
        "runtime_resource_collision_checked": False,
        "dns_tls_validated": False,
        "mysql_keycloak_identity_validated": False,
        "operator_and_owner_approval_verified": False,
        "deployment_permitted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    try:
        result = check(parse_env(Path(args.env_file).read_text(encoding="utf-8")))
    except (ValueError, OSError, UnicodeError):
        print(json.dumps({"config_shape": "BLOCKED", "deployment_permitted": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
