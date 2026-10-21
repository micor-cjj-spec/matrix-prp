#!/usr/bin/env python3
"""Generate an isolated Keycloak realm with the exact MCP resource URI.

This does not deploy Keycloak or configure an external MCP OAuth client.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def canonical_resource(value):
    if not isinstance(value, str):
        raise ValueError("Explicit HTTPS MCP resource URL is required")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment
            or not parsed.path.endswith("/api/mcp") or "//" in parsed.path
            or "/../" in parsed.path or "/./" in parsed.path):
        raise ValueError("MCP resource must be an exact HTTPS URL ending in /api/mcp")
    return value


def build_realm(resource, template=None):
    resource = canonical_resource(resource)
    base = json.loads((template or ROOT / "realm/prp-mcp-realm.json").read_text(encoding="utf-8"))
    if base.get("realm") != "prp-mcp" or not base.get("enabled"):
        raise ValueError("Unexpected Keycloak realm template")
    if base.get("clients"):
        raise ValueError("Template must not pre-register arbitrary clients")
    base["clients"] = [{
        "clientId": "matrix-prp-mcp-resource",
        "name": "Matrix PRP MCP Protected Resource",
        "enabled": True,
        "protocol": "openid-connect",
        "bearerOnly": True,
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "attributes": {
            "resource_url": resource
        }
    }]
    return base


def main():
    parser = argparse.ArgumentParser(description="Build reviewed Keycloak MCP resource realm")
    parser.add_argument("--resource", required=True, help="Exact HTTPS URI published by PRP MCP")
    parser.add_argument("--output", default=str(ROOT / ".generated/realm/prp-mcp-realm.json"),
                        help="Destination JSON for Keycloak first-time import")
    options = parser.parse_args()
    result = build_realm(options.resource)
    target = Path(options.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit("Refusing to overwrite existing Keycloak realm import; review state first")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {target}; contains one protected-resource client and NO OAuth login clients.")
    print("First-import only. Register actual OAuth clients/scopes and audience after admin review.")


if __name__ == "__main__":
    main()
