"""Offline, in-memory review-only Keycloak Realm *candidate* for #218.

NO host connection, file writing, Keycloak Admin REST, client grant or approval.
This does not register a ChatGPT login client and is NOT an import or deploy tool.
"""

from copy import deepcopy
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-oauth"))
from build_realm import build_realm

REALM = "prp-mcp218"
READ_SCOPES = ("prp.reviews.read", "prp.video.read")


def _exact_candidate_resource(resource):
    """Accept only a planned independent HTTPS MCP hostname and exact path."""
    if not isinstance(resource, str):
        raise ValueError("REVIEW_RESOURCE_URL_REQUIRED")
    try:
        parsed = urlsplit(resource)
        # Use exact reconstruction: no credentials, query, fragment, port,
        # percent-encoded host, trailing dot, or alternate resource path.
        host = parsed.hostname
        if (parsed.scheme != "https" or not host
                or parsed.netloc != host
                or parsed.path != "/api/mcp"
                or parsed.query or parsed.fragment
                or resource != f"https://{host}/api/mcp"):
            raise ValueError("REVIEW_RESOURCE_MUST_BE_NEW_HTTPS")
    except ValueError as exc:
        raise ValueError("REVIEW_RESOURCE_MUST_BE_NEW_HTTPS") from None
    labels = host.split(".")
    if (len(host) > 253 or len(labels) < 2 or not labels[0].startswith("mcp218-")
            or labels[0] == "mcp218-"
            or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part)
                       and len(part) <= 63 for part in labels)
            or labels[-1] in ("test", "invalid", "example", "localhost", "local")):
        raise ValueError("REVIEW_RESOURCE_MUST_BE_DEDICATED")
    return resource


def build_review_video_candidate(resource):
    """Construct a resource-only candidate in memory; nothing is installed."""
    resource = _exact_candidate_resource(resource)
    # Reuse the existing safe Keycloak realm and signed-subject mapper contract,
    # while excluding the old built-in task/finance/health/write scope inventory.
    result = build_realm(resource)
    if (result["realm"] != "prp-mcp" or len(result["clients"]) != 1
            or len(result["clientScopes"]) != 7):
        raise ValueError("UPSTREAM_REALM_SHAPE_CHANGED")
    by_name = {scope["name"]: scope for scope in result["clientScopes"]}
    if len(by_name) != 7 or "basic" not in by_name or "prp.tasks.read" not in by_name:
        raise ValueError("UPSTREAM_SCOPE_SHAPE_CHANGED")
    base_read = by_name["prp.tasks.read"]
    if not all(base_read["attributes"].get(k) == v for k, v in {
        "include.in.token.scope": "true",
        "display.on.consent.screen": "true",
        "consent.screen.text": "prp.tasks.read",
    }.items()):
        raise ValueError("UPSTREAM_CONSENT_SHAPE_CHANGED")
    result["realm"] = REALM
    result["displayName"] = "PRP MCP218 Review/Video Isolated Canary (UNDEPLOYED CANDIDATE)"
    protected = result["clients"][0]
    if not protected.get("bearerOnly") or protected.get("standardFlowEnabled"):
        raise ValueError("UPSTREAM_RESOURCE_CLIENT_SHAPE_CHANGED")
    protected["clientId"] = "matrix-prp-mcp218-resource"
    protected["name"] = "PRP MCP218 Readonly Resource (review only)"
    new_scopes = []
    for name in READ_SCOPES:
        scope = deepcopy(base_read)
        scope["name"] = name
        scope["description"] = f"PRP MCP218 readonly permission: {name}"
        scope["attributes"]["consent.screen.text"] = name
        new_scopes.append(scope)
    result["clientScopes"] = [deepcopy(by_name["basic"]), *new_scopes]
    # No login client, redirect, user, grant, signing material or credential.
    if (len(result["clients"]) != 1 or
            tuple(x["name"] for x in result["clientScopes"][1:]) != READ_SCOPES):
        raise ValueError("REVIEW_REALM_SCOPE_INVARIANT_FAILED")
    return result
