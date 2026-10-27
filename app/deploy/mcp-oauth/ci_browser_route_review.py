#!/usr/bin/env python3
"""Compare disposable Chromium PRP requests to the *review-only* route plan.

No HTTP interception, no Keycloak admin access, and no route deployment.
Collect only (method, URL path) for the PRP *origin* in browser memory:
never collect state/code query values, authorization headers, PRP bearer,
post bodies, JWTs, cookies or Keycloak requests.
"""
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

STAGING = Path(__file__).resolve().parents[1] / "mcp-staging"
if str(STAGING) not in sys.path:
    sys.path.insert(0, str(STAGING))
from approval_routes_pending import READONLY_LINK_EXACT, READONLY_LINK_REGEX  # noqa: E402

PRP_ORIGIN = "https://prp-e2e.localhost"


def classify(method, url):
    """Return None for external origin, True for allowlisted, False otherwise."""
    parsed = urlsplit(url)
    if parsed.scheme + "://" + parsed.netloc != PRP_ORIGIN:
        return None
    path = parsed.path
    method = method.upper()
    # Do not normalize path aliases or decoded percent encodings in test.
    if "%" in path or "\\" in path or "//" in path:
        return False
    if method in READONLY_LINK_EXACT.get(path, "").split():
        return True
    return any(method in verbs.split() and re.fullmatch(pattern, path)
               for pattern, verbs in READONLY_LINK_REGEX.items())


def path_class(method, url):
    """Only bounded diagnostic categories, no untrusted path or query emitted."""
    parsed = urlsplit(url)
    p = parsed.path
    if p.startswith("/api/"):
        if p.startswith("/api/mcp/identity/oidc/"):
            return "API_OIDC"
        if p.startswith("/api/mcp/"):
            return "API_MCP"
        if p.startswith("/api/auth/"):
            return "API_AUTH"
        if p.startswith("/api/users/"):
            return "API_USERS"
        return "API_OTHER"
    if p.startswith("/prp/assets/"):
        return "SPA_ASSETS"
    if p.startswith("/prp/"):
        return "SPA_OTHER"
    return "OTHER_PRP_ORIGIN"


class Audit:
    def __init__(self):
        self.seen = set()

    def record(self, method, url):
        # Store ONLY method/path; never retain URL query or credentials.
        if classify(method, url) is None:
            return
        self.seen.add((method.upper(), urlsplit(url).path))

    def unexpected(self):
        # Restore a query-free synthetic URL to apply the static allowlist.
        return sorted((method, path) for method, path in self.seen
                      if classify(method, PRP_ORIGIN + path) is not True)

    def summary(self):
        bad = self.unexpected()
        categories = sorted(set(path_class(method, PRP_ORIGIN + path)
                                for method, path in bad))
        return {
            "checked_unique_method_paths": len(self.seen),
            "unreviewed_unique_method_paths": len(bad),
            "unreviewed_path_classes": categories,
        }


def require_review_coverage(audit):
    bad = audit.summary()
    if bad["unreviewed_unique_method_paths"]:
        # No OAuth code/state and no full URL/path in CI output.
        print("FAIL E2E BROWSER ROUTE REVIEW: unseen PRP request categories="
              + ",".join(bad["unreviewed_path_classes"])
              + "; count=" + str(bad["unreviewed_unique_method_paths"]))
        raise RuntimeError("CHROMIUM_BROWSING_ROUTES_NOT_COVERED_BY_G0_CANDIDATE")
    print("PASS E2E BROWSER ROUTE REVIEW: observed browser method/path "
          "requests covered by review-only exact/asset allowlist ("
          + str(bad["checked_unique_method_paths"]) + " unique). "
          "Not an approval, install, or public TLS/raw-URI acceptance.")
