#!/usr/bin/env python3
"""Signed Keycloak + browser-shaped PKCE for opt-in review/video MCP reads.

Only an ephemeral GitHub runner, synthetic identities, a fresh MySQL DB and
a throwaway exact-client RSA assertion. Never log OAuth tokens or private rows.
"""
import json
import os
import ssl
import subprocess
import sys
import uuid

import ci_pkce_browser as flow
from ci_static_client_jwt import ASSERTION_TYPE, assertion
from oauth_token_check import _b64url, check_token
from pathlib import Path

SCOPES = ("prp.reviews.read", "prp.video.read")
TOOLS = {"prp_reviews_list", "prp_video_folders", "prp_video_progress"}
PRP = "https://prp-e2e.localhost"


def require(condition, name):
    if not condition:
        raise RuntimeError(name)


def ensure_disposable():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_TEMP")
            and os.environ.get("MCP_E2E_REVIEW_VIDEO") == "true"
            and os.environ.get("MCP_E2E_FIRST_PARTY") == "true"
            and os.environ.get("MCP_E2E_EXACT_CHATGPT") == "true"
            and os.environ.get("MCP_E2E_CRUD") != "true"
            and flow.EXACT_CHATGPT_CI
            and flow.CLIENT == "https://chatgpt.com/oauth/client.json"
            and flow.ISSUER == "https://auth-e2e.localhost/realms/prp-mcp"
            and flow.RESOURCE == PRP + "/api/mcp", "REVIEW_VIDEO_DISPOSABLE_ONLY")
    key = os.environ.get("MCP_E2E_EXACT_CLIENT_KEY", "")
    require(key and os.path.isfile(key)
            and os.path.realpath(key).startswith(
                os.path.realpath(os.environ["RUNNER_TEMP"]) + os.sep),
            "DISPOSABLE_EXACT_CLIENT_KEY_REQUIRED")
    return Path(key)


def issue_token(opener, user_password, key, required_scopes):
    code, verifier = flow.code_pkce(
        opener, "e2e-keycloak-owner", user_password,
        requested_scopes="openid " + " ".join(required_scopes))
    token_request = {
        "grant_type": "authorization_code", "client_id": flow.CLIENT,
        "code": code, "redirect_uri": flow.CALLBACK,
        "code_verifier": verifier, "resource": flow.RESOURCE,
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion(
            key, issuer=flow.CLIENT, subject=flow.CLIENT,
            aud=flow.ISSUER + "/protocol/openid-connect/token"),
    }
    issued = flow.json_response(flow.request(
        opener, flow.ISSUER + "/protocol/openid-connect/token",
        data=token_request, form=True), "Keycloak signed review/video token exchange")
    bearer = issued.get("access_token")
    require(isinstance(bearer, str), "REVIEW_VIDEO_ACCESS_TOKEN_MISSING")
    jwks = flow.json_response(flow.request(
        opener, flow.ISSUER + "/protocol/openid-connect/certs"), "Keycloak RSA JWKS")
    for scope in required_scopes:
        check_token(bearer, jwks, issuer=flow.ISSUER,
                    resource=flow.RESOURCE, client_id=flow.CLIENT,
                    required_scope=scope)
    # The scope claims are trustworthy only after complete cryptographic check.
    claims = json.loads(_b64url(bearer.split(".")[1]))
    actual = set(claims.get("scope", "").split())
    require(all(scope in actual for scope in required_scopes),
            "SIGNED_TOKEN_SCOPE_MISSING")
    require("prp.tasks.read" not in actual and "prp.write.create" not in actual,
            "UNREQUESTED_TASK_OR_WRITE_SCOPE_GRANTED")
    if "prp.video.read" not in required_scopes:
        require("prp.video.read" not in actual,
                "UNREQUESTED_VIDEO_SCOPE_GRANTED")
    return bearer


def seed_fixtures(opener, prp_jwt):
    review = flow.json_response(flow.request(
        opener, PRP + "/api/reviews", bearer=prp_jwt,
        data={"reviewType": "weekly", "moduleCode": "learning",
              "title": "CI_RV_OWNER_REVIEW", "summary": "CI_RV_OWNER_PREVIEW",
              "highlights": "CI_RV_PRIVATE_HIGHLIGHTS",
              "problems": "CI_RV_PRIVATE_PROBLEMS",
              "nextActions": "CI_RV_PRIVATE_ACTION",
              "periodStart": "2026-11-01", "periodEnd": "2026-11-21"}),
        "Disposable owner creates one review")
    require(isinstance(review.get("data", {}).get("id"), int),
            "CI_REVIEW_OWNER_SEED_FAILED")
    folder = flow.json_response(flow.request(
        opener, PRP + "/api/video/folders", bearer=prp_jwt,
        data={"name": "CI_RV_OWNER_FOLDER", "parentId": None}),
        "Disposable owner creates one video folder")
    folder_id = folder.get("data", {}).get("id")
    require(isinstance(folder_id, int) and folder_id > 0,
            "CI_VIDEO_OWNER_FOLDER_SEED_FAILED")
    # All SQL runs inside the NEW, disposable MySQL container only.
    # A foreign account is seeded to prove that MCP cannot cross user_id.
    query = (
        "INSERT INTO prp_users "
        "(username,display_name,password_hash,is_admin,enabled) "
        "VALUES ('ci_rv_foreign','CI synthetic foreign','NO_LOGIN',0,1);"
        "INSERT INTO prp_reviews "
        "(user_id,review_type,module_code,title,summary,highlights,problems,"
        "next_actions,period_start,period_end,created_at,updated_at,deleted) "
        "SELECT id,'weekly','learning','CI_RV_FOREIGN_REVIEW',"
        "'CI_RV_FOREIGN_SUMMARY','PRIVATE_FOREIGN_HIGHLIGHTS',"
        "'PRIVATE_FOREIGN_PROBLEMS','PRIVATE_FOREIGN_ACTION',"
        "'2026-11-01','2026-11-21',NOW(6),NOW(6),0 "
        "FROM prp_users WHERE username='ci_rv_foreign';"
        "INSERT INTO prp_video_folders (user_id,parent_id,name,sort_order) "
        "SELECT id,NULL,'CI_RV_FOREIGN_FOLDER',0 "
        "FROM prp_users WHERE username='ci_rv_foreign';"
        "INSERT INTO prp_video_assets (user_id,folder_id,title,storage_key,size_bytes) "
        "SELECT user_id,id,'CI_RV_FOREIGN_VIDEO',UUID(),16 "
        "FROM prp_video_folders WHERE name='CI_RV_FOREIGN_FOLDER';"
        "INSERT INTO prp_video_assets (user_id,folder_id,title,storage_key,size_bytes) "
        "SELECT id," + str(folder_id) + ",'CI_RV_OWNER_VIDEO',UUID(),32 "
        "FROM prp_users WHERE username='stage_admin';"
        "INSERT INTO prp_video_progress "
        "(user_id,video_id,position_seconds,duration_seconds) "
        "SELECT user_id,id,40,200 FROM prp_video_assets "
        "WHERE title='CI_RV_OWNER_VIDEO';"
        "SELECT id FROM prp_video_folders WHERE name='CI_RV_FOREIGN_FOLDER';"
    )
    result = subprocess.run([
        "docker", "exec", "prp-ci-real-mysql", "sh", "-c",
        'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --protocol=TCP '
        '-h 127.0.0.1 -u prp_e2e -D matrix_prp_mcp_e2e '
        '--batch --skip-column-names -e "$1"',
        "_", query], capture_output=True, text=True, check=False, timeout=20)
    require(result.returncode == 0, "CI_REVIEW_VIDEO_FOREIGN_SEED_FAILED")
    rows = result.stdout.strip().splitlines()
    require(len(rows) == 1 and rows[0].isdigit(),
            "CI_REVIEW_VIDEO_FOREIGN_FOLDER_ID_MISSING")
    print("CI_REVIEW_VIDEO_SYNTHETIC_TWO_OWNERS_SEEDED=YES")
    return int(rows[0])


def rpc(opener, bearer, name, args=None):
    return flow.jsonrpc(opener, bearer, 100, "tools/call",
                        {"name": name, "arguments": args or {}})


def assert_read(opener, bearer, tool, owner_marker, foreign_marker):
    status, body = rpc(opener, bearer, tool)
    require(status == 200 and not body.get("error")
            and body.get("result", {}).get("isError") is not True,
            "REVIEW_VIDEO_SIGNED_MCP_READ_FAILED_" + tool)
    serialized = json.dumps(body, ensure_ascii=False)
    require(owner_marker in serialized and foreign_marker not in serialized,
            "REVIEW_VIDEO_CROSS_OWNER_DATA_LEAK_" + tool)
    for restricted in ("CI_RV_PRIVATE_", "PRIVATE_FOREIGN_",
                       "storageKey", "playbackUrl", "ticket", "sizeBytes"):
        require(restricted not in serialized,
                "REVIEW_VIDEO_SENSITIVE_FIELD_LEAK_" + tool)


def assert_denied(response, name):
    status, body = response
    denied = status in (400, 401, 403, 404) or (
        status == 200 and (bool(body.get("error")) or
                           body.get("result", {}).get("isError") is True))
    require(denied, name)


def run():
    key = ensure_disposable()
    context = ssl.create_default_context(cafile=os.environ["MCP_E2E_CA_CERT"])
    opener = flow.build_opener(
        flow.HTTPSHandler(context=context),
        flow.HTTPCookieProcessor(flow.CookieJar()), flow.SafeRedirect())
    flow.wait_ready(opener, flow.ISSUER + "/.well-known/openid-configuration")
    flow.wait_ready(opener, PRP + "/api/health")
    flow.add_user(opener, os.environ["MCP_E2E_KC_ADMIN_PASSWORD"],
                  "e2e-keycloak-owner", os.environ["MCP_E2E_KC_USER_PASSWORD"])
    bearer = issue_token(opener, os.environ["MCP_E2E_KC_USER_PASSWORD"], key, SCOPES)
    print("PASS CI REVIEW VIDEO: real Keycloak PKCE, RSA JWKS, issuer, aud, client, both scopes.")
    require(flow.jsonrpc(opener, bearer, 1, "tools/list")[0] == 401,
            "REVIEW_VIDEO_UNLINKED_SUBJECT_WAS_ACCEPTED")
    owner = flow.json_response(flow.request(opener, PRP + "/api/auth/login",
        data={"username": "stage_admin",
              "password": os.environ["MCP_E2E_PRP_PASSWORD"]}), "PRP owner login")
    prp_jwt = owner.get("data", {}).get("token")
    require(isinstance(prp_jwt, str), "REVIEW_VIDEO_PRP_LOGIN_FAILED")
    foreign_folder = seed_fixtures(opener, prp_jwt)
    grant_url = PRP + "/api/mcp/clients"
    def grant(scopes):
        reply = flow.json_response(flow.request(
            opener, grant_url, bearer=prp_jwt,
            data={"clientId": flow.CLIENT, "scopes": list(scopes),
                  "password": os.environ["MCP_E2E_PRP_PASSWORD"]}),
            "PRP owner opts into new read scopes")
        require(reply.get("data", {}).get("status") == "ACTIVE",
                "REVIEW_VIDEO_OWNER_CONSENT_FAILED")
    grant(SCOPES)
    ticket = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/identity/tickets", bearer=prp_jwt,
        data={"clientId": flow.CLIENT,
              "password": os.environ["MCP_E2E_PRP_PASSWORD"]}),
        "PRP independent owner ticket").get("data", {}).get("code")
    require(isinstance(ticket, str) and len(ticket) == 43,
            "REVIEW_VIDEO_IDENTITY_TICKET_MISSING")
    linked = flow.json_response(flow.request(
        opener, flow.RESOURCE + "/link", bearer=bearer,
        data={"ticket": ticket}), "Real JWT-to-PRP owner identity link")
    require(linked.get("data", {}).get("newlyLinked") is True,
            "REVIEW_VIDEO_IDENTITY_LINK_FAILED")
    require(flow.request(opener, flow.RESOURCE + "/link", bearer=bearer,
                         data={"ticket": ticket})[0] == 409,
            "REVIEW_VIDEO_TICKET_REPLAY_ACCEPTED")
    listing = flow.jsonrpc(opener, bearer, 2, "tools/list", {})
    tools = listing[1].get("result", {}).get("tools", [])
    require(listing[0] == 200 and
            {tool.get("name") for tool in tools} == TOOLS,
            "REVIEW_VIDEO_MANIFEST_NOT_EXACTLY_READ_ONLY")
    for tool in tools:
        require(tool.get("annotations", {}).get("readOnlyHint") is True,
                "REVIEW_VIDEO_TOOL_NOT_MARKED_READ_ONLY")
    assert_read(opener, bearer, "prp_reviews_list",
                "CI_RV_OWNER_REVIEW", "CI_RV_FOREIGN_REVIEW")
    assert_read(opener, bearer, "prp_video_folders",
                "CI_RV_OWNER_FOLDER", "CI_RV_FOREIGN_FOLDER")
    assert_read(opener, bearer, "prp_video_progress",
                "CI_RV_OWNER_VIDEO", "CI_RV_FOREIGN_VIDEO")
    progress = json.dumps(rpc(opener, bearer, "prp_video_progress")[1])
    require("positionSeconds" in progress and "durationSeconds" in progress,
            "REVIEW_VIDEO_PROGRESS_METADATA_MISSING")
    assert_denied(rpc(opener, bearer, "prp_video_progress",
                      {"folderId": foreign_folder}),
                  "REVIEW_VIDEO_FOREIGN_FOLDER_NOT_DENIED")
    assert_denied(rpc(opener, bearer, "prp_reviews_list", {"limit": 21}),
                  "REVIEW_VIDEO_BOUND_NOT_ENFORCED")
    assert_denied(rpc(opener, bearer, "prp_prepare_task"),
                  "REVIEW_VIDEO_WRITE_TOOL_EXPOSED")
    print("PASS CI REVIEW VIDEO: 3 signed MCP reads, two-owner isolation, hidden private fields and bounds.")

    reviews_only = issue_token(
        opener, os.environ["MCP_E2E_KC_USER_PASSWORD"], key,
        ("prp.reviews.read",))
    assert_read(opener, reviews_only, "prp_reviews_list",
                "CI_RV_OWNER_REVIEW", "CI_RV_FOREIGN_REVIEW")
    assert_denied(rpc(opener, reviews_only, "prp_video_folders"),
                  "REVIEW_VIDEO_SIGNED_MISSING_SCOPE_NOT_DENIED")
    # The still-valid BOTH-scope JWT loses access on the very next request
    # once the owner reduces actual PRP server-side consent.
    grant(("prp.reviews.read",))
    assert_denied(rpc(opener, bearer, "prp_video_progress"),
                  "REVIEW_VIDEO_REDUCED_OWNER_CONSENT_IGNORED")
    grant(SCOPES)
    assert_read(opener, bearer, "prp_video_folders",
                "CI_RV_OWNER_FOLDER", "CI_RV_FOREIGN_FOLDER")
    flow.json_response(flow.request(
        opener, PRP + "/api/mcp/clients/revoke",
        bearer=prp_jwt, data={"clientId": flow.CLIENT}), "PRP revoke signed client")
    require(flow.jsonrpc(opener, bearer, 6, "tools/list", {})[0] == 401,
            "REVIEW_VIDEO_REVOKED_SIGNED_JWT_STILL_AUTHORIZED")
    print("PASS CI REVIEW VIDEO: missing signed scope, reduced consent and immediate revocation.")


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        # Diagnostics never include bearer tokens, codes or personal content.
        message = str(error)
        if any(s in message for s in ("?", "Bearer ", "password=", "token=")):
            message = "Sensitive OAuth request failure"
        print("FAIL CI REVIEW VIDEO: " + message, file=sys.stderr)
        raise SystemExit(1)
