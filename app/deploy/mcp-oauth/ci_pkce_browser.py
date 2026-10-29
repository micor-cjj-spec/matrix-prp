#!/usr/bin/env python3
"""Real ephemeral Keycloak auth-code PKCE -> PRP owner link -> MCP HTTP.

DISPOSABLE GitHub runner only. Uses a temporary realm user, temporary PRP
bootstrap owner and isolated MySQL. No production DNS/credentials or user data.
Access tokens, passwords, cookies, authorization codes, tickets, JSON-RPC
content and user data are NEVER written to stdout or logs.
"""
import base64
import hashlib
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
import os
import secrets
import ssl
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPSHandler, HTTPCookieProcessor, HTTPRedirectHandler

from oauth_token_check import check_token

ISSUER = "https://auth-e2e.localhost/realms/prp-mcp"
RESOURCE = "https://prp-e2e.localhost/api/mcp"
EXACT_CHATGPT_CI = os.environ.get("MCP_E2E_EXACT_CHATGPT") == "true"
CLIENT = ("https://chatgpt.com/oauth/client.json"
          if EXACT_CHATGPT_CI else "prp-pkce-probe")
CALLBACK = ("https://chatgpt.com/connector_platform_oauth_redirect"
            if EXACT_CHATGPT_CI else "http://127.0.0.1:8765/callback")
PROTOCOL = "2025-06-18"
ADMIN = "http://127.0.0.1:18080"


class CallbackReceived(Exception):
    def __init__(self, url):
        self.url = url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        target = urlsplit(url)
        if url.startswith(CALLBACK + "?"):
            raise CallbackReceived(url)
        if (target.scheme != "https" or target.hostname != urlsplit(ISSUER).hostname
                or target.port is not None):
            raise RuntimeError("OAuth attempted an unexpected cross-origin redirect")
        return super().redirect_request(request, fp, code, msg, headers, url)


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.current = {"action": values.get("action"), "id": values.get("id", ""),
                            "inputs": {}, "buttons": set()}
        elif self.current is not None and tag == "input" and values.get("name"):
            self.current["inputs"][values["name"]] = values.get("value", "")
        elif self.current is not None and tag == "button" and values.get("name"):
            self.current["buttons"].add(values["name"])

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def request(opener, url, *, data=None, bearer=None, form=False, method=None):
    headers = {"Accept": "application/json" if not form else "text/html"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    if data is not None:
        if form:
            payload = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            payload = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    else:
        payload = None
    req = Request(url, data=payload, headers=headers, method=method)
    try:
        with opener.open(req, timeout=15) as response:
            raw = response.read(250_001)
            if len(raw) > 250_000:
                raise RuntimeError("Oversized test response")
            return response.status, response.headers.get("Content-Type", ""), raw.decode("utf-8")
    except HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), ""


def expect(response, wanted, stage):
    if response[0] != wanted:
        raise RuntimeError(stage + ": unexpected HTTP " + str(response[0]))


def json_response(response, stage):
    expect(response, 200, stage)
    try:
        result = json.loads(response[2])
    except (ValueError, TypeError):
        raise RuntimeError(stage + ": response is not JSON") from None
    if not isinstance(result, dict):
        raise RuntimeError(stage + ": malformed JSON")
    return result


def wait_ready(opener, url, max_seconds=150):
    until = time.monotonic() + max_seconds
    while time.monotonic() < until:
        try:
            if request(opener, url)[0] == 200:
                return
        except (OSError, ValueError, ssl.SSLError):
            pass
        time.sleep(3)
    raise RuntimeError("Temporary environment not healthy: " + ("Keycloak" if "auth-" in url else "PRP"))


def add_user(opener, admin_password, username, password):
    admin_token = json_response(request(opener, ADMIN + "/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": "prp-ci-admin", "password": admin_password}, form=True),
        "Keycloak admin authentication").get("access_token")
    if not admin_token:
        raise RuntimeError("Keycloak CI admin token unavailable")
    # Only ephemeral realm user. No password grant on the public PKCE client.
    user = {"username": username, "enabled": True, "emailVerified": True,
            "firstName": "E2E", "lastName": "Test", "email": "ci-oauth-user@example.invalid",
            "requiredActions": [],
            "credentials": [{"type": "password", "value": password, "temporary": False}]}
    expect(request(opener, ADMIN + "/admin/realms/prp-mcp/users",
                   data=user, bearer=admin_token), 201, "Temporary Keycloak user creation")


def code_pkce(opener, login_user, login_password, requested_scopes="openid prp.tasks.read",
              *, authorization_url=None):
    if authorization_url is None:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()
                                              ).rstrip(b"=").decode()
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        params = {
            "client_id": CLIENT, "response_type": "code", "redirect_uri": CALLBACK,
            "scope": requested_scopes, "code_challenge_method": "S256",
            "code_challenge": challenge, "state": state, "nonce": nonce,
            "resource": RESOURCE,
        }
        url = ISSUER + "/protocol/openid-connect/auth?" + urlencode(params)
    else:
        # Exact URL was generated by the REAL PRP backend. The PKCE verifier
        # stays server-side; never replace the issued challenge with a fixture.
        parsed = urlsplit(authorization_url)
        if (parsed.scheme != "https" or parsed.netloc != urlsplit(ISSUER).netloc
                or parsed.path != urlsplit(ISSUER).path + "/protocol/openid-connect/auth"
                or parsed.fragment):
            raise RuntimeError("UNTRUSTED_FIRST_PARTY_AUTHORIZE_URL")
        params = parse_qs(parsed.query, keep_blank_values=True)
        if (params.get("redirect_uri") != [CALLBACK]
                or params.get("scope") != ["openid"]
                or params.get("client_id") != ["prp-first-party-link"]
                or params.get("response_type") != ["code"]
                or params.get("code_challenge_method") != ["S256"]
                or len(params.get("code_challenge", [])) != 1
                or len(params.get("state", [])) != 1
                or len(params.get("nonce", [])) != 1):
            raise RuntimeError("FIRST_PARTY_PKCE_PARAMETERS_MISMATCH")
        state = params["state"][0]
        verifier = None
        url = authorization_url
    try:
        current = request(opener, url, form=True)
    except CallbackReceived as cb:
        return parse_callback(cb.url, state), verifier
    expect(current, 200, "Keycloak browser authorization page")
    parser = Forms()
    parser.feed(current[2])
    logins = [f for f in parser.forms
              if {"username", "password"}.issubset(f["inputs"])]
    if len(logins) > 1:
        raise RuntimeError("Ambiguous Keycloak login forms")
    if logins:
        login_form = logins[0]
        if not login_form["action"]:
            raise RuntimeError("Keycloak login form action is missing")
        target = urljoin(ISSUER, login_form["action"])
        if urlsplit(target).hostname != urlsplit(ISSUER).hostname:
            raise RuntimeError("Untrusted Keycloak login action")
        data = dict(login_form["inputs"])
        data.update({"username": login_user, "password": login_password})
        try:
            current = request(opener, target, data=data, form=True)
        except CallbackReceived as cb:
            return parse_callback(cb.url, state), verifier
    expect(current, 200, "Keycloak OAuth consent screen")
    consent = Forms()
    consent.feed(current[2])
    approved = False
    for f in consent.forms:
        if not f["action"] or (not "accept" in f["buttons"] and
                               "accept" not in f["inputs"] and
                               "kc-consent" not in (f["id"] or "")):
            continue
        action = urljoin(ISSUER, f["action"])
        if urlsplit(action).hostname != urlsplit(ISSUER).hostname:
            raise RuntimeError("Untrusted OAuth consent action")
        payload = dict(f["inputs"])
        payload["accept"] = "Yes"
        try:
            after = request(opener, action, data=payload, form=True)
        except CallbackReceived as cb:
            approved = True
            code = parse_callback(cb.url, state)
            break
        if after[0] != 200:
            raise RuntimeError("OAuth consent POST rejected (HTTP " + str(after[0]) + ")")
        next_forms = Forms()
        next_forms.feed(after[2])
        safe_names = ",".join(x["id"] or "unnamed" for x in next_forms.forms[:5])
        raise RuntimeError("OAuth consent reached another page; next form ids=" +
                           (safe_names or "none"))
    if not approved:
        summary = ",".join(
            (f["id"] or "unnamed") + ":" + ",".join(sorted(f["buttons"]))
            for f in consent.forms[:5])
        # Only structural form identifiers and submit-button names, never
        # login HTML, fields, codes, cookies, secrets, or auth URLs.
        raise RuntimeError(
            "OAuth post-login page did not reach callback; form ids/buttons=" +
            (summary or "none") + "; status=" + str(current[0]))
    return code, verifier


def parse_callback(url, state):
    parsed = urlsplit(url)
    if parsed._replace(query="").geturl() != CALLBACK:
        raise RuntimeError("Untrusted OAuth callback")
    query = parse_qs(parsed.query)
    if query.get("state") != [state] or len(query.get("code", [])) != 1:
        raise RuntimeError("OAuth state/code verification failed")
    if query.get("iss") != [ISSUER]:
        raise RuntimeError("OAuth callback issuer mismatch")
    return query["code"][0]


def jsonrpc(opener, token, id, method, params=None):
    body = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        body["params"] = params
    req = Request(RESOURCE, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
    })
    try:
        with opener.open(req, timeout=30) as res:
            raw = res.read(250_001)
            if len(raw) > 250_000:
                raise RuntimeError("Oversized MCP response")
            media = res.headers.get("Content-Type", "")
            payload = raw.decode()
            if "text/event-stream" in media:
                events = [line[5:].strip() for line in payload.splitlines() if line.startswith("data:")]
                if not events:
                    raise RuntimeError("MCP SSE response empty")
                payload = events[-1]
            return res.status, json.loads(payload)
    except HTTPError as error:
        return error.code, {}


def seed_exact_client_owner_limit_fixture(opener, prp_jwt):
    """Disposable-only: 24 owned tasks + one foreign-owner task in CI MySQL."""
    if not EXACT_CHATGPT_CI:
        return
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_FIRST_PARTY") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or ISSUER != "https://auth-e2e.localhost/realms/prp-mcp"
            or RESOURCE != "https://prp-e2e.localhost/api/mcp"):
        raise RuntimeError("TASK_COUNT_FIXTURE_DISPOSABLE_ONLY")
    for i in range(24):
        response = json_response(request(
            opener, "https://prp-e2e.localhost/api/tasks",
            bearer=prp_jwt,
            data={"moduleCode": "work", "title": "ci-exact-owned-task-" + str(i),
                  "description": "CI synthetic fixture only", "priority": "low"}),
            "Create scoped synthetic CI task")
        if not isinstance(response.get("data", {}).get("id"), int):
            raise RuntimeError("CI_OWNER_TASK_SEED_FAILED")
    # A deliberately unrelated owner is inserted using ONLY the
    # throwaway MySQL container's own password environment variable.
    # The SQL contains no real credentials; neither data nor user IDs
    # are copied from the user's PRP server.
    import subprocess
    query = (
        "INSERT INTO prp_users "
        "(username,display_name,password_hash,is_admin,enabled) "
        "VALUES ('ci_exact_other_owner','CI foreign synthetic',"
        "'CI_NO_LOGIN',0,1);"
        "INSERT INTO prp_tasks "
        "(id,user_id,module_code,title,description,priority,status,"
        "created_at,updated_at,deleted) "
        "SELECT 987654321,id,'work','ci-exact-FOREIGN-owner-task',"
        "'CI foreign-only','low','todo',NOW(6),NOW(6),0 "
        "FROM prp_users WHERE username='ci_exact_other_owner';"
    )
    result = subprocess.run([
        "docker", "exec", "prp-ci-real-mysql", "sh", "-c",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --protocol=TCP '
        '-h 127.0.0.1 -uroot -D matrix_prp_mcp_e2e -e "$1"',
        "_", query,
    ], capture_output=True, check=False, timeout=15)
    if result.returncode:
        raise RuntimeError("CI_FOREIGN_OWNER_TASK_SEED_FAILED")
    print("CI_EXACT_CLIENT_SYNTHETIC_24_OWNED_1_FOREIGN_TASKS_SEEDED=YES")


def check_exact_client_task_result(opener, oauth_bearer, read):
    """Enforce actual JSON task records, max 20 and foreign owner denial."""
    if not EXACT_CHATGPT_CI:
        return
    result = read[1].get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise RuntimeError("CI_EXACT_TASK_RESULT_NOT_SUCCESS")
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise RuntimeError("CI_EXACT_TASK_CONTENT_FORMAT_CHANGED")
    part = content[0]
    if (not isinstance(part, dict) or part.get("type") != "text"
            or not isinstance(part.get("text"), str)):
        raise RuntimeError("CI_EXACT_TASK_CONTENT_NOT_TEXT")
    try:
        tasks = json.loads(part["text"])
    except ValueError:
        raise RuntimeError("CI_EXACT_TASK_CONTENT_NOT_JSON") from None
    if (not isinstance(tasks, list) or len(tasks) != 20
            or not all(isinstance(row, dict)
                       and isinstance(row.get("id"), int)
                       and isinstance(row.get("title"), str)
                       and row["title"].startswith("ci-exact-owned-task-")
                       for row in tasks)):
        raise RuntimeError("CI_EXACT_TASK_LIMIT_OR_OWNER_SCOPE_FAILURE")
    foreign = jsonrpc(opener, oauth_bearer, 81, "tools/call", {
        "name": "prp_task_get", "arguments": {"taskId": 987654321}})
    if (foreign[0] == 200 and not foreign[1].get("error")
            and foreign[1].get("result", {}).get("isError") is not True):
        raise RuntimeError("CI_EXACT_FOREIGN_TASK_ACCESS_ACCEPTED")
    print("CI_EXACT_CLIENT_REAL_MCP_20_TASK_LIMIT_AND_CROSS_OWNER_DENIAL=PASS")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("This test requires an isolated GitHub Actions runner")
    ca = os.environ["MCP_E2E_CA_CERT"]
    context = ssl.create_default_context(cafile=ca)
    # Authenticate against the actual HTTPS staging-style proxy and retain
    # browser cookies for the Keycloak login/consent pages.
    opener = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(CookieJar()), SafeRedirect())
    admin_pass = os.environ["MCP_E2E_KC_ADMIN_PASSWORD"]
    user_password = os.environ["MCP_E2E_KC_USER_PASSWORD"]
    prp_password = os.environ["MCP_E2E_PRP_PASSWORD"]
    wait_ready(opener, ISSUER + "/.well-known/openid-configuration")
    wait_ready(opener, "https://prp-e2e.localhost/api/health")
    print("PASS E2E: isolated Keycloak HTTPS and PRP Java/MySQL healthy.")
    add_user(opener, admin_pass, "e2e-keycloak-owner", user_password)
    code, verifier = code_pkce(opener, "e2e-keycloak-owner", user_password)
    print("PASS E2E: real browser-shaped OAuth login, consent, authorization code + PKCE S256.")
    token_form = {"grant_type": "authorization_code", "client_id": CLIENT,
                  "code": code, "redirect_uri": CALLBACK,
                  "code_verifier": verifier, "resource": RESOURCE}
    if EXACT_CHATGPT_CI:
        # The exact official client ID is deliberately authenticated by
        # a disposable CI RSA key, NOT by ChatGPT/OpenAI's private key.
        # This proves Keycloak->PRP wire compatibility, not real OpenAI auth.
        from pathlib import Path
        from ci_static_client_jwt import assertion, ASSERTION_TYPE
        key = os.environ.get("MCP_E2E_EXACT_CLIENT_KEY")
        if (os.environ.get("MCP_E2E_FIRST_PARTY") != "true"
                or not key or not os.path.isfile(key)
                or not os.path.realpath(key).startswith(
                    os.path.realpath(os.environ["RUNNER_TEMP"]) + os.sep)):
            raise RuntimeError("EXACT_CHATGPT_DISPOSABLE_PRIVATE_KEY_REQUIRED")
        token_form["client_assertion_type"] = ASSERTION_TYPE
        token_form["client_assertion"] = assertion(
            Path(key), issuer=CLIENT, subject=CLIENT,
            aud=ISSUER + "/protocol/openid-connect/token")
    exchanged = json_response(request(
        opener, ISSUER + "/protocol/openid-connect/token",
        data=token_form, form=True), "PKCE code exchange")
    bearer = exchanged.get("access_token")
    if not isinstance(bearer, str):
        raise RuntimeError("Keycloak did not issue an access token")
    jwks = json_response(request(opener, ISSUER + "/protocol/openid-connect/certs"), "JWKS")
    check_token(bearer, jwks, issuer=ISSUER, resource=RESOURCE, client_id=CLIENT)
    print("PASS E2E: real browser grant token RSA JWKS, aud, azp, task scope verified.")
    if EXACT_CHATGPT_CI:
        print("CI_EXACT_CHATGPT_ID_PRIVATE_KEY_JWT_DISPOSABLE_ASSERTION_AND_REAL_RESOURCE_TOKEN=PASS")

    unauth = jsonrpc(opener, bearer, 1, "tools/list")
    if unauth[0] != 401:
        raise RuntimeError("Unlinked OAuth identity must be rejected (HTTP 401)")
    owner = json_response(request(opener, "https://prp-e2e.localhost/api/auth/login",
        data={"username": "stage_admin", "password": prp_password}), "PRP owner login")
    prp_jwt = owner.get("data", {}).get("token")
    if not prp_jwt:
        raise RuntimeError("PRP test owner login returned no session token")
    seed_exact_client_owner_limit_fixture(opener, prp_jwt)
    grant = json_response(request(opener, "https://prp-e2e.localhost/api/mcp/clients",
        bearer=prp_jwt, data={"clientId": CLIENT, "scopes": ["prp.tasks.read"],
                              "password": prp_password}), "Owner client consent")
    if grant.get("data", {}).get("status") != "ACTIVE":
        raise RuntimeError("PRP owner did not authorize read-only OAuth client")
    if os.environ.get("MCP_E2E_FIRST_PARTY") == "true":
        import ci_first_party_link_e2e
        if os.environ.get("MCP_E2E_CHROMIUM") == "true":
            import ci_first_party_chromium_e2e
            ci_first_party_chromium_e2e.run(
                sys.modules[__name__], opener, bearer, prp_jwt,
                prp_password, user_password)
        else:
            ci_first_party_link_e2e.run(
                sys.modules[__name__], opener, bearer, prp_jwt, prp_password, user_password)
    else:
        ticket = json_response(request(opener, "https://prp-e2e.localhost/api/mcp/identity/tickets",
            bearer=prp_jwt, data={"clientId": CLIENT, "password": prp_password}),
            "Owner one-use link ticket").get("data", {}).get("code")
        if not isinstance(ticket, str) or len(ticket) != 43:
            raise RuntimeError("PRP owner linking ticket invalid")
        linked = json_response(request(opener, RESOURCE + "/link", bearer=bearer,
            data={"ticket": ticket}), "Verified OAuth identity link")
        if not linked.get("data", {}).get("newlyLinked"):
            raise RuntimeError("OAuth issuer/subject link did not complete")
        replay = request(opener, RESOURCE + "/link", bearer=bearer, data={"ticket": ticket})
        if replay[0] not in (409,):
            raise RuntimeError("One-time identity ticket replay was not rejected")
        print("PASS E2E: owner password reauthentication, client grant, one-time account link + replay block.")

    init = jsonrpc(opener, bearer, 2, "initialize", {
        "protocolVersion": PROTOCOL, "capabilities": {},
        "clientInfo": {"name": "ci-keycloak-pkce", "version": "1.0"}
    })
    if init[0] != 200 or not init[1].get("result", {}).get("serverInfo"):
        raise RuntimeError("OAuth-authenticated MCP initialize failed")
    listing = jsonrpc(opener, bearer, 3, "tools/list", {})
    exposed = {tool.get("name") for tool in
               listing[1].get("result", {}).get("tools", [])}
    if listing[0] != 200 or "prp_tasks_list" not in exposed:
        raise RuntimeError("Authenticated MCP tools/list unavailable")
    if os.environ.get("MCP_E2E_CRUD") != "true":
        # A scoped task-only server must not even ADVERTISE finance
        # or write tools. The old test looked only at tools/call errors.
        if exposed != {"prp_tasks_list", "prp_task_get"}:
            raise RuntimeError("TASK_ONLY_MCP_TOOL_CATALOG_SCOPE_BYPASS")
    read = jsonrpc(opener, bearer, 4, "tools/call",
                   {"name": "prp_tasks_list", "arguments": {}})
    if read[0] != 200 or read[1].get("error") or read[1].get("result", {}).get("isError"):
        raise RuntimeError("Authenticated task-read MCP tool failed")
    check_exact_client_task_result(opener, bearer, read)
    denied = jsonrpc(opener, bearer, 5, "tools/call",
                     {"name": "prp_finance_month", "arguments": {}})
    # In a task-only tool registry this is an UNKNOWN TOOL JSON-RPC
    # error, not a per-tool authorization isError result. Both forms
    # must be denied; a successful finance result is always failure.
    forbidden = (denied[0] in (400, 403, 404) or
                 (denied[0] == 200 and
                  (bool(denied[1].get("error")) or
                   denied[1].get("result", {}).get("isError") is True)))
    if not forbidden:
        raise RuntimeError("FINANCE_TOOL_ACCESS_WAS_NOT_DENIED")
    print("PASS E2E: MCP initialize, tools/list, tasks read, finance permission denied.")
    if EXACT_CHATGPT_CI:
        print("CI_EXACT_CHATGPT_ID_TO_FIRST_PARTY_LINKED_PRP_TASK_TOOL=PASS")
        print("ACTUAL_OPENAI_PRIVATE_KEY_JWT_VERIFIED=NO")
    if os.environ.get("MCP_E2E_FIRST_PARTY") == "true":
        ci_first_party_link_e2e.verify_unlink_invalidates_pending(
            sys.modules[__name__], opener, prp_jwt, bearer, prp_password)
        ci_first_party_link_e2e.verify_concurrent_flow_limit(
            sys.modules[__name__], prp_jwt, prp_password)
    if os.environ.get('MCP_E2E_CRUD') == 'true':
        import ci_crud_flow
        ci_crud_flow.run(sys.modules[__name__], opener, prp_jwt, prp_password, user_password)
    revoke = json_response(request(opener, "https://prp-e2e.localhost/api/mcp/clients/revoke",
        bearer=prp_jwt, data={"clientId": CLIENT}), "PRP client revocation")
    after = jsonrpc(opener, bearer, 6, "tools/list", {})
    if after[0] != 401:
        raise RuntimeError("Revoked client retained access with still-valid OAuth bearer")
    print("PASS E2E: immediate OAuth client revocation; all real PRP rows isolated to disposable MySQL.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not leak URLs with query parameters, bearer tokens, cookies, user
        # payloads or secrets into public GitHub logs.
        message = str(error)
        if any(x in message for x in ("?", "Bearer ", "password=", "token=")):
            message = "Sensitive external/OAuth request failure"
        print("FAIL E2E: " + message, file=sys.stderr)
        raise SystemExit(1)
