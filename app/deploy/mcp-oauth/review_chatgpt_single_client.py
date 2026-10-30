#!/usr/bin/env python3
"""Owner-scoped, non-deployable review of ONE exact ChatGPT OAuth client.

Never contacts Keycloak or emits a Keycloak import / Admin REST request.
The two-client legacy review is intentionally NOT a deployment payload.
"""
import json
from copy import deepcopy
from review_exact_client_registrations import (
    CHATGPT, CHATGPT_CALLBACK, CHATGPT_JWKS, RESOURCE, client_proposals
)

EXPECTED = next(c for c in client_proposals() if c["clientId"] == CHATGPT)

def review_single_client(candidate=None):
    candidate = deepcopy(EXPECTED) if candidate is None else candidate
    if type(candidate) is not dict or candidate != EXPECTED:
        raise ValueError("OWNER_SCOPE_OR_CLIENT_SHAPE_CHANGED")
    if candidate["clientId"] != "https://chatgpt.com/oauth/client.json":
        raise ValueError("UNAUTHORIZED_CLIENT_ID")
    if candidate["redirectUris"] != [CHATGPT_CALLBACK]:
        raise ValueError("UNAUTHORIZED_CALLBACK")
    if candidate["attributes"].get("jwks.url") != CHATGPT_JWKS:
        raise ValueError("UNAUTHORIZED_JWKS")
    if candidate["protocolMappers"][0]["config"]["included.custom.audience"] != RESOURCE:
        raise ValueError("UNAUTHORIZED_AUDIENCE")
    return {
        "realm": "prp-mcp",
        "status": "NO_GO_B2_INDEPENDENT_APPROVAL_REQUIRED",
        "deployable": False,
        "not_a_keycloak_import": True,
        "not_an_admin_api_request": True,
        "not_a_release_receipt": True,
        "proposed_client_count": 1,
        "proposed_client": candidate,
        "explicitly_excluded": ["prp-first-party-link", "existing clients",
                                "realm-wide policies", "Nginx", "production database"],
    }

if __name__ == "__main__":
    print(json.dumps(review_single_client(), indent=2, ensure_ascii=False))
