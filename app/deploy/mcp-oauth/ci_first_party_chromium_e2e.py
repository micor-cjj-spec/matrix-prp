#!/usr/bin/env python3
"""Real Chromium UI walkthrough against the disposable PRP HTTPS/Keycloak/MySQL stack.

The browser receives the synthetic PRP session only on the PRP origin.
The signer, PKCE verifier, ID token, code and cookies never reach CI output.
Chromium allows the CI-generated TLS certificate; the separate Python
E2E verifies the CA chain, not this browser automation.
"""
import json
import os
from urllib.parse import urlsplit
from oauth_token_check import _b64url
from ci_browser_route_review import Audit, require_review_coverage

from playwright.sync_api import sync_playwright

PRP = "https://prp-e2e.localhost"
ISSUER_ORIGIN = "https://auth-e2e.localhost"
CHATGPT = "https://chatgpt.com/oauth/client.json"


def run(flow, opener, oauth_bearer, prp_bearer, prp_password, keycloak_password):
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_CHROMIUM") != "true"
            or os.environ.get("MCP_E2E_FIRST_PARTY") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or flow.ISSUER != ISSUER_ORIGIN + "/realms/prp-mcp"):
        raise RuntimeError("FIRST_PARTY_BROWSER_DISPOSABLE_CI_ONLY")
    review_video = os.environ.get("MCP_E2E_REVIEW_VIDEO") == "true"
    if review_video:
        # Only a throwaway test may unlink the ticket-linked synthetic subject.
        # Rebind via real browser PKCE after an explicit review/video-only grant.
        if (os.environ.get("MCP_E2E_EXACT_CHATGPT") != "true"
                or os.environ.get("MCP_E2E_CRUD") == "true"):
            raise RuntimeError("BROWSER_REVIEW_VIDEO_EXACT_READONLY_CI_REQUIRED")
        flow.json_response(flow.request(
            opener, PRP + "/api/mcp/identity/unlink", bearer=prp_bearer,
            data={"password": prp_password}), "Unlink synthetic ticket pairing")
    if not review_video:
        # Keep the existing task-only E2E behavior unchanged. Review/video
        # intentionally exercises owner scope selection via the actual SPA.
        grant = flow.json_response(flow.request(
            opener, PRP + "/api/mcp/clients", bearer=prp_bearer,
            data={"clientId": CHATGPT, "scopes": ["prp.tasks.read"],
                  "password": prp_password}), "Grant task read to CI client")
        if grant.get("data", {}).get("status") != "ACTIVE":
            raise RuntimeError("BROWSER_CHATGPT_TASK_SCOPE_NOT_GRANTED")
    stage = "CHROMIUM_START"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"])
        # CI-only certificate trust exception; never use this with live PRP.
        context = browser.new_context(ignore_https_errors=True,
                                      service_workers="block")
        # Restrict synthetic PRP JWT to its own origin, not Keycloak; do not
        # pass the OAuth bearer or temporary code to the page.
        context.add_init_script("""(() => {
          if (location.origin === 'https://prp-e2e.localhost') {
            localStorage.setItem('matrix-prp-token', %s)
          }
        })();""" % json.dumps(prp_bearer))
        page = context.new_page()
        seen_origins = set()
        route_audit = Audit()
        start_statuses = []
        page.on("request", lambda req: seen_origins.add(
            urlsplit(req.url).scheme + "://" + urlsplit(req.url).netloc))
        page.on("request", lambda req: route_audit.record(req.method, req.url))
        # Status-only diagnostic; never capture request/response body or URI
        # query because authorization codes and states are sensitive.
        page.on("response", lambda response: start_statuses.append(response.status)
                if urlsplit(response.url).path == "/api/mcp/identity/oidc/start"
                else None)
        try:
            stage = "OPEN_PRP_MCP_GRANTS"
            page.goto(PRP + "/prp/me/mcp-clients",
                      wait_until="domcontentloaded", timeout=30000)
            stage = "EXACT_RESOURCE_SCOPE_DISCOVERY"
            if review_video:
                page.locator(".scope-option").filter(
                    has_text="读取复盘摘要").wait_for(state="visible", timeout=20000)
                page.locator(".scope-option").filter(
                    has_text="读取视频目录和学习进度").wait_for(
                        state="visible", timeout=20000)
                if (page.locator(".scope-option").count() != 2
                        or page.locator('.scope-option input[type="checkbox"]:checked').count() != 0):
                    raise RuntimeError("BROWSER_REVIEW_VIDEO_SCOPE_DEFAULT_NOT_EMPTY")
                page.get_by_text("身份绑定本身不会新增数据读取授权",
                                 exact=False).wait_for(state="visible", timeout=20000)
                if page.get_by_text("读取任务", exact=True).count() != 0:
                    raise RuntimeError("BROWSER_REVIEW_VIDEO_TASK_SCOPE_MISADVERTISED")
                stage = "BROWSER_EXPLICIT_REVIEW_VIDEO_OWNER_GRANT"
                for label in ("读取复盘摘要", "读取视频目录和学习进度"):
                    page.locator(".scope-option").filter(
                        has_text=label).locator("label").click(timeout=15000)
                if page.locator('.scope-option input[type="checkbox"]:checked').count() != 2:
                    raise RuntimeError("BROWSER_OWNER_REVIEW_VIDEO_CHECKBOXES_NOT_SELECTED")
                page.get_by_placeholder("OAuth client_id").fill(CHATGPT)
                page.get_by_placeholder(
                    "密码只发送给 PRP，不提供给 AI 客户端").fill(prp_password)
                page.get_by_role("button", name="批准此客户端").click()
                page.locator(".client-row").filter(
                    has_text=CHATGPT).get_by_text(
                        "已授权", exact=True).wait_for(state="visible", timeout=30000)
            else:
                page.locator(".scope-option").filter(has_text="读取任务").wait_for(
                    state="visible", timeout=20000)
                if (page.locator(".scope-option").count() != 1
                        or not page.locator('.scope-option input[type="checkbox"]').is_checked()):
                    raise RuntimeError("BROWSER_SCOPE_DISCOVERY_OR_READ_DEFAULT_INVALID")
            panel = page.locator(".el-card").filter(
                has=page.get_by_text("推荐：在 PRP 中通过 Keycloak 安全绑定账号"))
            panel.locator('input[type="password"]').fill(prp_password, timeout=20000)
            stage = "PRP_BUTTON_TO_KEYCLOAK"
            panel.get_by_role("button", name="使用 Keycloak 验证并绑定").click()
            page.wait_for_url(ISSUER_ORIGIN + "/realms/prp-mcp/**",
                              timeout=30000)
            if urlsplit(page.url).netloc != "auth-e2e.localhost":
                raise RuntimeError("BROWSER_UNTRUSTED_OIDC_REDIRECT")
            stage = "KEYCLOAK_LOGIN"
            page.locator('input[name="username"]').fill(
                "e2e-keycloak-owner", timeout=20000)
            page.locator('input[name="password"]').fill(
                keycloak_password, timeout=20000)
            page.locator("#kc-login").click()
            stage = "KEYCLOAK_CONSENT_OR_CALLBACK"
            # The one-scope OIDC client may display a consent page or skip it.
            # Never click arbitrary buttons on a page at an untrusted origin.
            try:
                page.get_by_role("button", name="Accept").click(timeout=3000)
            except Exception:
                try:
                    page.locator('input[name="accept"], button[name="accept"], #kc-accept').first.click(timeout=1000)
                except Exception:
                    pass
            stage = "PRP_CALLBACK_SUCCESS"
            page.get_by_text("身份验证和绑定成功").wait_for(
                state="visible", timeout=30000)
            if (page.url != PRP + "/prp/me/mcp-link/callback"
                    or any(k in page.url for k in ("?code=", "?state=", "?iss="))):
                raise RuntimeError("BROWSER_OAUTH_CALLBACK_URL_NOT_SCRUBBED")
            if seen_origins.difference({PRP, ISSUER_ORIGIN}):
                raise RuntimeError("BROWSER_UNEXPECTED_THIRD_PARTY_REQUEST")
            stage = "EXPIRED_PRP_SESSION_CALLBACK_SANITIZATION"
            # Two real Chromium loads with fake test-only callback parameters:
            # absent and deliberately invalid PRP sessions. Startup 401
            # handling must never redirect to /login?redirect=...code/state.
            for stored in (None, "ci-invalid-prp-session"):
                expired = browser.new_context(ignore_https_errors=True,
                                              service_workers="block")
                try:
                    if stored is not None:
                        expired.add_init_script(
                            """localStorage.setItem('matrix-prp-token',
                               'ci-invalid-prp-session')""")
                    negative_page = expired.new_page()
                    negative_page.on("request", lambda req:
                                     route_audit.record(req.method, req.url))
                    navs = []
                    negative_page.on("framenavigated", lambda frame:
                        navs.append(frame.url) if frame == negative_page.main_frame
                        else None)
                    synthetic = (
                        PRP + "/prp/me/mcp-link/callback?code=ci-code"
                        + "&state=" + "S" * 43
                        + "&iss=" + flow.ISSUER)
                    negative_page.goto(synthetic, wait_until="domcontentloaded",
                                       timeout=30000)
                    negative_page.wait_for_function(
                        "() => location.search === ''", timeout=15000)
                    # Give the profile lookup its chance to fire 401.
                    negative_page.wait_for_timeout(1200)
                    if negative_page.url != PRP + "/prp/me/mcp-link/callback":
                        raise RuntimeError("EXPIRED_SESSION_CALLBACK_REDIRECTED")
                    if any(
                        ("/login" in url and ("code=" in url or "state=" in url))
                        for url in navs
                    ):
                        raise RuntimeError("EXPIRED_SESSION_REDIRECT_LEAK")
                finally:
                    expired.close()
            stage = "G0_BROWSER_REQUEST_ALLOWLIST"
            require_review_coverage(route_audit)
        except Exception:
            # Never log the raw browser URL or OAuth requests. Report only
            # static stage, first-party start response class and current host.
            current = urlsplit(page.url).hostname
            current_class = ("KEYCLOAK" if current == "auth-e2e.localhost"
                else "PRP" if current == "prp-e2e.localhost"
                else "OTHER")
            start_class = ("NONE" if not start_statuses else
                "_".join(str(x) for x in start_statuses[-2:]))
            print("BROWSER_CI_DIAGNOSTIC=" + stage
                  + "_START_STATUS_" + start_class
                  + "_PAGE_" + current_class)
            raise RuntimeError("FIRST_PARTY_BROWSER_E2E_FAILED_AT_" + stage) from None
        finally:
            context.close()
            browser.close()

    links = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/identity", bearer=prp_bearer),
        "Account mapping after Chromium callback").get("data")
    signed_mcp_subject = json.loads(_b64url(
        oauth_bearer.split(".")[1])).get("sub")
    if (not isinstance(links, list) or len(links) != 1
            or links[0].get("issuer") != flow.ISSUER
            or links[0].get("subject") != signed_mcp_subject):
        raise RuntimeError("BROWSER_OIDC_SUBJECT_NOT_LINKED_TO_MCP_IDENTITY")
    if review_video:
        manifest = flow.jsonrpc(opener, oauth_bearer, 72, "tools/list", {})
        offered = {tool.get("name") for tool in
                   manifest[1].get("result", {}).get("tools", [])}
        if (manifest[0] != 200 or offered != {
                "prp_reviews_list", "prp_video_folders", "prp_video_progress"}):
            raise RuntimeError("BROWSER_REVIEW_VIDEO_TOOL_CATALOG_NOT_EXACT")
        for name in sorted(offered):
            result = flow.jsonrpc(opener, oauth_bearer, 73, "tools/call",
                                  {"name": name, "arguments": {}})
            if (result[0] != 200 or result[1].get("error")
                    or result[1].get("result", {}).get("isError")):
                raise RuntimeError("BROWSER_LINKED_READ_FAILED_" + name)
        unwanted = flow.jsonrpc(opener, oauth_bearer, 74, "tools/call",
                                {"name": "prp_tasks_list", "arguments": {}})
        if (unwanted[0] == 200 and not unwanted[1].get("error")
                and not unwanted[1].get("result", {}).get("isError")):
            raise RuntimeError("BROWSER_REVIEW_VIDEO_TASK_ACCESS_UNEXPECTEDLY_ALLOWED")
        print("PASS E2E CHROMIUM REVIEW VIDEO: real Vue read-scope UI defaults empty, "
              "Keycloak browser PKCE/callback, query scrub, linked three readonly tools; "
              "task scope denied.")
    else:
        result = flow.jsonrpc(opener, oauth_bearer, 73, "tools/call",
                              {"name": "prp_tasks_list", "arguments": {}})
        if (result[0] != 200 or result[1].get("error")
                or result[1].get("result", {}).get("isError")):
            raise RuntimeError("BROWSER_LINKED_MCP_TASK_READ_FAILED")
        print("PASS E2E CHROMIUM: actual PRP Vue page, pinned Keycloak login, server-side " +
              "PKCE callback, query scrub, identity link and separate bearer tasks read.")
