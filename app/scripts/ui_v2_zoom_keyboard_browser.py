#!/usr/bin/env python3
"""Browser integration test for real UI V2 chat layout with synthetic viewport/API.
Linux Chromium/WebKit are NOT physical iPhone Safari or a real on-screen keyboard.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

BASE = os.getenv("PRP_UI_SMOKE_URL", "http://127.0.0.1:4173/prp/")
ARTIFACTS = Path(os.getenv("PRP_UI_SMOKE_DIR", "/tmp/prp-ui-v2-zoom"))
ARTIFACTS.mkdir(parents=True, exist_ok=True)

def test(browser, width, height):
    context = browser.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=2,
        is_mobile=True, has_touch=True, locale="zh-CN",
        reduced_motion="reduce", service_workers="block",
    )
    context.add_init_script("localStorage.setItem('matrix-prp-token', 'synthetic-zoom-only')")
    unexpected = []
    errors = []

    def intercept(route):
        url = urlsplit(route.request.url)
        if "/api/" in url.path:
            path = "/" + url.path.split("/api/", 1)[1]
            if route.request.method != "GET":
                unexpected.append(f"{route.request.method} {path}")
                route.abort()
                return
            if path == "/users/me":
                data = {"id": 7, "username": "zoom_test", "displayName": "合成用户",
                        "administrator": False}
            elif path == "/ai/conversations/page":
                data = {"items": [], "nextCursor": None, "hasMore": False}
            elif path == "/ai/usage":
                data = {"month": "2026-11", "requests": 0, "reservedTokens": 0,
                        "inputTokens": 0, "outputTokens": 0,
                        "maxRequests": 50, "maxReservedTokens": 100000}
            elif path == "/ai/settings":
                data = {"selectedProvider": "deepseek", "selectedModel": "deepseek-chat",
                        "providers": [{"id": "deepseek", "name": "DeepSeek",
                                       "models": ["deepseek-chat"],
                                       "defaultModel": "deepseek-chat",
                                       "configured": True, "personalKey": False}]}
            else:
                data = []
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"code": "SUCCESS", "message": "synthetic",
                                           "data": data}, ensure_ascii=False))
        elif url.hostname in ("127.0.0.1", "localhost"):
            route.continue_()
        else:
            unexpected.append("EXTERNAL " + url.hostname)
            route.abort()

    context.route("**/*", intercept)
    page = context.new_page()
    console_errors = []
    failed_requests = []
    bad_responses = []
    page.on("pageerror", lambda e: errors.append(str(e)[:400]))
    page.on("console", lambda m: console_errors.append(m.text[:400]) if m.type == "error" else None)
    page.on("requestfailed", lambda r: failed_requests.append(r.method + " " + urlsplit(r.url).path[:180]))
    page.on("response", lambda r: bad_responses.append(str(r.status) + " " + urlsplit(r.url).path[:180])
            if r.status >= 400 else None)
    try:
        page.goto(BASE + "chat", wait_until="domcontentloaded", timeout=30000)
        textarea = page.locator(".chat-input textarea")
        try:
            textarea.wait_for(timeout=11000)
        except Exception:
            # Diagnose direct-link navigation without weakening the browser assertion.
            details = page.evaluate("""() => ({
                url: location.href,
                title: document.title,
                readyState: document.readyState,
                hasSyntheticToken: Boolean(localStorage.getItem('matrix-prp-token')),
                appText: document.querySelector('#app')?.innerText?.slice(0, 1100) ?? '',
                chatElements: document.querySelectorAll('.chat-input').length,
                loginInputs: document.querySelectorAll('input[type=password]').length,
                routeLinks: [...document.querySelectorAll('nav a')].slice(0, 8).map(x => x.href),
            })""")
            print("BOOT_DIAG " + json.dumps({
                "viewport": [width, height],
                "engine": os.getenv("PRP_UI_BROWSER"),
                "details": details, "exceptions": errors[:8],
                "console_errors": console_errors[:8],
                "failed_requests": failed_requests[:8],
                "bad_responses": bad_responses[:8],
                "unexpected_requests": unexpected[:8],
            }, ensure_ascii=False), flush=True)
            page.screenshot(path=str(ARTIFACTS / f"chat-init-failure-{width}.png"), full_page=False)
            raise
        nav = page.locator("nav.prp-mobile-tabs")
        expect(nav).to_be_visible()
        assert nav.locator("a").count() == 4, "The four primary tabs must remain"
        layout_height = page.evaluate("window.innerHeight")
        assert layout_height > 300, f"Unexpected layout viewport {layout_height}"

        def geometry(scale, visual_height, top=0):
            return page.evaluate("""({scale, visualHeight, top}) => {
                const vv = window.visualViewport;
                if (!vv) throw new Error('VisualViewport unavailable');
                if (!window.__zoomTestOriginals) {
                    window.__zoomTestOriginals = Object.fromEntries(
                        ['scale','height','offsetTop'].map(key =>
                            [key, Object.getOwnPropertyDescriptor(vv, key)]));
                }
                for (const [key,value] of Object.entries({
                    scale, height:visualHeight, offsetTop:top
                })) Object.defineProperty(vv, key,
                    {configurable:true, value});
                vv.dispatchEvent(new Event('resize'));
                return {scale:vv.scale, height:vv.height, offsetTop:vv.offsetTop};
            }""", {"scale": scale, "visualHeight": visual_height, "top": top})

        def assert_no_keyboard(label):
            expect(page.locator(".prp-shell-chat.prp-keyboard-open")).to_have_count(0)
            expect(nav).to_be_visible()
            expected = page.locator(".prp-shell-chat").evaluate(
                "(el) => el.style.getPropertyValue('--prp-chat-viewport-height').trim()")
            assert expected == "100dvh", f"{label}: unexpected chat height {expected}"

        # Browser zoom changes VisualViewport but does NOT imply a software keyboard.
        geometry(2, layout_height / 2)
        assert_no_keyboard("200% pinch-only")
        page.screenshot(path=str(ARTIFACTS / f"pinch-no-keyboard-{width}.png"))

        # Pan inside the zoomed viewport should not be mistaken for keyboard.
        geometry(2, (layout_height - 48) / 2, 24)
        assert_no_keyboard("200% pinch with visual viewport offset")

        # At normal magnification, the keyboard occludes ~280 CSS px.
        normal_keyboard_height = layout_height - 280
        geometry(1, normal_keyboard_height)
        expect(page.locator(".prp-shell-chat.prp-keyboard-open")).to_have_count(1)
        expect(nav).to_be_hidden()
        actual = page.locator(".prp-shell-chat").evaluate(
            "(el) => el.style.getPropertyValue('--prp-chat-viewport-height').trim()")
        assert actual == f"{round(normal_keyboard_height)}px", actual

        # At 200% magnification, the keyboard *adds* occlusion beyond zoom.
        zoom_keyboard_height = layout_height / 2 - 120
        geometry(2, zoom_keyboard_height)
        expect(page.locator(".prp-shell-chat.prp-keyboard-open")).to_have_count(1)
        expect(nav).to_be_hidden()
        page.screenshot(path=str(ARTIFACTS / f"zoom-with-keyboard-{width}.png"))

        # Reset viewport properties to the engine's original native getters.
        page.evaluate("""() => {
            const vv = window.visualViewport;
            for (const [key,descriptor] of Object.entries(window.__zoomTestOriginals)) {
                if (descriptor) Object.defineProperty(vv,key,descriptor);
                else delete vv[key];
            }
            vv.dispatchEvent(new Event('resize'));
        }""")
        assert_no_keyboard("restored")
        assert not unexpected, f"Unexpected writes/external requests: {unexpected}"
        assert not errors, f"Browser JS errors: {errors}"
        print(f"PASS {width}x{height} {os.getenv('PRP_UI_BROWSER')} zoom/keyboard/navigation", flush=True)
    finally:
        context.close()

def main():
    engine = os.getenv("PRP_UI_BROWSER", "chromium")
    if engine not in ("chromium", "webkit"):
        raise ValueError("Browser engine must be chromium or webkit")
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(headless=True)
        try:
            for width, height in ((390, 844), (844, 390)):
                test(browser, width, height)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
