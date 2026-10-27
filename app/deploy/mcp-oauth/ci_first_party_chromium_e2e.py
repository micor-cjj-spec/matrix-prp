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
    import ci_first_party_link_e2e as first
    grant = flow.json_response(flow.request(
        opener, PRP + "/api/mcp/clients", bearer=prp_bearer,
        data={"clientId": CHATGPT, "scopes": ["prp.tasks.read"],
              "password": prp_password}), "Grant task read to exact ChatGPT client ID")
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
        start_statuses = []
        page.on("request", lambda req: seen_origins.add(
            urlsplit(req.url).scheme + "://" + urlsplit(req.url).netloc))
        # Status-only diagnostic; never capture request/response body or URI
        # query because authorization codes and states are sensitive.
        page.on("response", lambda response: start_statuses.append(response.status)
                if urlsplit(response.url).path == "/api/mcp/identity/oidc/start"
                else None)
        try:
            stage = "OPEN_PRP_MCP_GRANTS"
            page.goto(PRP + "/prp/me/mcp-clients",
                      wait_until="domcontentloaded", timeout=30000)
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
    result = flow.jsonrpc(opener, oauth_bearer, 73, "tools/call",
                          {"name": "prp_tasks_list", "arguments": {}})
    if result[0] != 200 or result[1].get("error") or             result[1].get("result", {}).get("isError"):
        raise RuntimeError("BROWSER_LINKED_MCP_TASK_READ_FAILED")
    print("PASS E2E CHROMIUM: actual PRP Vue page, pinned Keycloak login, server-side " +
          "PKCE callback, query scrub, identity link and separate bearer tasks read.")
