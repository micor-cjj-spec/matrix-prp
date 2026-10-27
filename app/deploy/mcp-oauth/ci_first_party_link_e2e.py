#!/usr/bin/env python3
"""PRP first-party PKCE account linking with REAL throwaway Keycloak and MySQL.

Called only by ci_pkce_browser.py after a disposable PRP session and a
separately signed/read-only resource bearer exist. Runs on CI loopback HTTPS,
never visits production, never prints passwords, codes, state or OAuth tokens.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from oauth_token_check import _b64url

PRP = "https://prp-e2e.localhost"
FIRST_CALLBACK = PRP + "/prp/me/mcp-link/callback"
CHATGPT = "https://chatgpt.com/oauth/client.json"


def run(flow, opener, oauth_bearer, prp_bearer, prp_password, keycloak_password):
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_FIRST_PARTY") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or flow.ISSUER != "https://auth-e2e.localhost/realms/prp-mcp"):
        raise RuntimeError("FIRST_PARTY_DISPOSABLE_CI_ONLY")
    owner = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/clients", bearer=prp_bearer,
        data={"clientId": CHATGPT, "scopes": ["prp.tasks.read"],
              "password": prp_password}), "First-party owner approves exact ChatGPT ID")
    if owner.get("data", {}).get("status") != "ACTIVE":
        raise RuntimeError("FIRST_PARTY_CHATGPT_TASK_GRANT_NOT_ACTIVE")
    endpoint = PRP + "/api/mcp/identity/oidc"
    refused = flow.request(opener, endpoint + "/start",
                           bearer=prp_bearer, data={"password": "wrong-password"})
    if refused[0] != 403:
        raise RuntimeError("FIRST_PARTY_BAD_PRP_PASSWORD_NOT_DENIED")
    created = flow.json_response(flow.request(
        opener, endpoint + "/start", bearer=prp_bearer,
        data={"password": prp_password}), "PRP first-party PKCE state creation")
    authorize = created.get("data", {}).get("authorizeUrl")
    if not isinstance(authorize, str):
        raise RuntimeError("FIRST_PARTY_AUTHORIZE_URL_MISSING")
    params = parse_qs(urlsplit(authorize).query)
    state = params.get("state", [None])[0]
    if not isinstance(state, str) or len(state) != 43:
        raise RuntimeError("FIRST_PARTY_PKCE_STATE_INVALID")
    # Wrong issuer must be denied BEFORE any token exchange/state consumption.
    wrong = flow.request(opener, endpoint + "/finish", bearer=prp_bearer,
                         data={"state": state, "code": "synthetic-error",
                               "iss": "https://untrusted.invalid/realms/prp-mcp"})
    if wrong[0] != 400:
        raise RuntimeError("FIRST_PARTY_WRONG_ISSUER_NOT_DENIED")
    original_callback = flow.CALLBACK
    try:
        flow.CALLBACK = FIRST_CALLBACK
        code, verifier = flow.code_pkce(
            opener, "e2e-keycloak-owner", keycloak_password,
            authorization_url=authorize)
        if verifier is not None:
            raise RuntimeError("FIRST_PARTY_VERIFIER_LEFT_THE_PRP_SERVER")
    finally:
        flow.CALLBACK = original_callback

    done = flow.json_response(flow.request(
        opener, endpoint + "/finish", bearer=prp_bearer,
        data={"state": state, "code": code, "iss": flow.ISSUER}),
        "PRP completes real ID-token-validated first-party OIDC account link")
    if done.get("data", {}).get("issuer") != flow.ISSUER or             done.get("data", {}).get("newlyLinked") is not True:
        raise RuntimeError("FIRST_PARTY_LINK_MISSING")
    replay = flow.request(opener, endpoint + "/finish", bearer=prp_bearer,
                          data={"state": state, "code": code, "iss": flow.ISSUER})
    if replay[0] != 409:
        raise RuntimeError("FIRST_PARTY_PKCE_STATE_REPLAY_ACCEPTED")

    links = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/identity", bearer=prp_bearer),
        "PRP first-party linked Keycloak subject").get("data")
    signed_bearer_subject = json.loads(_b64url(oauth_bearer.split(".")[1])).get("sub")
    if (not isinstance(links, list) or len(links) != 1
            or links[0].get("subject") != signed_bearer_subject
            or links[0].get("issuer") != flow.ISSUER):
        raise RuntimeError("FIRST_PARTY_AND_MCP_SUBJECT_DIFFER_OR_UNVERIFIED")

    result = flow.jsonrpc(opener, oauth_bearer, 70, "tools/call",
                          {"name": "prp_tasks_list", "arguments": {}})
    if result[0] != 200 or result[1].get("error") or             result[1].get("result", {}).get("isError"):
        raise RuntimeError("FIRST_PARTY_BOUND_TASK_READ_FAILED")
    print("PASS E2E FIRST-PARTY: real HTTPS PRP /start -> Keycloak login/PKCE -> /finish, " +
          "ID-token subject matches separate MCP bearer, task-read allowed, " +
          "wrong password/issuer and replay rejected; no access tokens printed.")


def verify_unlink_invalidates_pending(flow, opener, prp_bearer, oauth_bearer,
                                      prp_password):
    """Real MySQL check: unlink cannot leave a pending OIDC replay path open."""
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_FIRST_PARTY") != "true"):
        raise RuntimeError("FIRST_PARTY_DISPOSABLE_CI_ONLY")
    endpoint = PRP + "/api/mcp/identity/oidc"
    pending = flow.json_response(flow.request(
        opener, endpoint + "/start", bearer=prp_bearer,
        data={"password": prp_password}), "Second, pending PKCE request")
    auth = pending.get("data", {}).get("authorizeUrl")
    if not isinstance(auth, str):
        raise RuntimeError("FIRST_PARTY_PENDING_AUTHORIZATION_MISSING")
    state = parse_qs(urlsplit(auth).query).get("state", [None])[0]
    if not isinstance(state, str) or len(state) != 43:
        raise RuntimeError("FIRST_PARTY_PENDING_STATE_MISSING")
    flow.json_response(flow.request(
        opener, PRP + "/api/mcp/identity/unlink", bearer=prp_bearer,
        data={"password": prp_password}), "Owner unlinks mapped OIDC identity")
    stale = flow.request(opener, endpoint + "/finish", bearer=prp_bearer,
                         data={"state": state, "code": "not-an-issued-code",
                               "iss": flow.ISSUER})
    if stale[0] != 409:
        raise RuntimeError("FIRST_PARTY_PENDING_STATE_SURVIVED_UNLINK")
    links = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/identity", bearer=prp_bearer),
        "Owner identity list after unlink").get("data")
    if links != []:
        raise RuntimeError("FIRST_PARTY_IDENTITY_REMAINS_AFTER_UNLINK")
    after = flow.jsonrpc(opener, oauth_bearer, 71, "tools/list", {})
    if after[0] != 401:
        raise RuntimeError("FIRST_PARTY_UNLINK_DID_NOT_REVOKE_MCP_ACCESS")
    print("PASS E2E FIRST-PARTY UNLINK: pending state rejected, DB owner link gone, " +
          "previously valid signed MCP bearer denied on next request.")


def verify_concurrent_flow_limit(flow, prp_bearer, prp_password):
    """Real InnoDB locking proof: 6 simultaneous starts may create only 3 flows."""
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_FIRST_PARTY") != "true"
            or not os.environ.get("RUNNER_TEMP")):
        raise RuntimeError("PARALLEL_PKCE_DISPOSABLE_ONLY")
    ready = Barrier(6)
    url = PRP + "/api/mcp/identity/oidc/start"

    def one_request(_):
        # Match ci_pkce_browser.main()'s disposable TLS+CookieJar transport.
        # Give every thread its OWN HTTP opener and cookie jar.
        context = flow.ssl.create_default_context(
            cafile=os.environ["MCP_E2E_CA_CERT"])
        local_opener = flow.build_opener(
            flow.HTTPSHandler(context=context),
            flow.HTTPCookieProcessor(flow.CookieJar()), flow.SafeRedirect())
        ready.wait(timeout=10)
        result = flow.request(local_opener, url, bearer=prp_bearer,
                              data={"password": prp_password})
        # Only status leaves the thread. No state/nonce/verifier or response
        # body is retained, printed or passed to another test.
        return result[0]

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(one_request, range(6)))
    if statuses.count(200) != 3 or statuses.count(429) != 3:
        # HTTP status-count diagnostics only. No OAuth code, token, state,
        # response body, request identifier or PRP user ID is logged.
        counts = ",".join(
            str(status) + "x" + str(statuses.count(status))
            for status in sorted(set(statuses)))
        raise RuntimeError("CONCURRENT_PKCE_CAP_FAILED_HTTP_" + counts)
    print("PASS E2E FIRST-PARTY CONCURRENCY: exactly 3 accepted, 3 rate-limited " +
          "among 6 same-owner simultaneous requests; no OAuth material logged.")
