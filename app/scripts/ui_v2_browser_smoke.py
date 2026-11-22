#!/usr/bin/env python3
"""UI V2 browser smoke against a local Vue preview and synthetic API only.

No real user, network backend, OAuth grant, production service or writable DB.
Chromium viewport emulation is not a substitute for a physical iPhone/Safari QA.
"""
import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PRP_UI_SMOKE_URL", "http://127.0.0.1:4173/prp/")
ARTIFACTS = Path(os.environ.get("PRP_UI_SMOKE_DIR", "/tmp/prp-ui-v2-smoke"))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()

USER = {"id": 7, "username": "ui_smoke", "displayName": "模拟用户", "administrator": False}
TASK = {
    "id": 71, "moduleCode": "life", "title": "完成一项模拟任务",
    "description": "Only synthetic test data", "priority": "MEDIUM",
    "status": "todo", "dueDate": TODAY, "createdAt": TODAY + "T08:00:00Z",
}
DAILY = {
    "date": TODAY, "calories": None, "proteinG": None, "carbsG": None,
    "fatG": None, "mealCount": 0, "exerciseMinutes": 0,
    "exerciseEstimatedKcal": None, "latestWeightKg": None,
    "goal": None, "recordedMealTypes": [],
}


def reply(route, payload, status=200):
    route.fulfill(
        status=status, content_type="application/json; charset=utf-8",
        body=json.dumps({"code": "SUCCESS", "message": "synthetic", "data": payload}, ensure_ascii=False),
    )


def mock_api(route, state):
    request = route.request
    url = urlsplit(request.url)
    if "/api/" not in url.path:
        route.abort()
        return
    path = "/" + url.path.split("/api/", 1)[1]
    method = request.method
    # Record only synthetic request paths; this test never reaches real services.
    state.setdefault("api_calls", []).append(method + " " + path)

    if path == "/users/me":
        reply(route, USER)
    elif path == "/dashboard/summary":
        active = [] if state["completed"] else [TASK]
        reply(route, {
            "date": TODAY, "todayTaskCount": len(active), "overdueTaskCount": 0,
            "unscheduledTaskCount": 0, "recentRecordCount": 0,
            "monthlyIncome": "0", "monthlyExpense": "0", "monthlyBalance": "0",
            "todayTasks": active, "overdueTasks": [], "unscheduledTasks": [],
            "highPriorityTasks": [], "recentRecords": [], "modules": [],
        })
    elif path == "/tasks/71/status" and method == "PATCH":
        assert parse_qs(url.query).get("status") == ["done"], "Incorrect task status update"
        state["writes"] += 1
        state["completed"] = True
        reply(route, {**TASK, "status": "done"})
    elif path == "/wellness/summary/daily":
        reply(route, DAILY)
    elif path == "/wellness/profile":
        reply(route, {"heightCm": None, "timezone": "Asia/Shanghai"})
    elif path == "/wellness/foods/usda/status":
        reply(route, {"configured": False})
    elif path.startswith("/wellness/"):
        reply(route, [])
    elif path == "/ai/conversations/page":
        reply(route, {"items": [], "nextCursor": None, "hasMore": False})
    elif path == "/ai/usage":
        reply(route, {
            "month": TODAY[:7], "requests": 0, "reservedTokens": 0,
            "inputTokens": 0, "outputTokens": 0,
            "maxRequests": 50, "maxReservedTokens": 100000,
        })
    elif path == "/ai/settings":
        reply(route, {
            "selectedProvider": "deepseek", "selectedModel": "deepseek-chat",
            "providers": [{"id": "deepseek", "name": "DeepSeek", "models": ["deepseek-chat"],
                           "defaultModel": "deepseek-chat", "configured": True,
                           "personalKey": False}],
        })
    else:
        # This test is read-only apart from one explicitly synthetic task PATCH.
        # Unknown operations fail closed; unknown GETs are empty fixture collections.
        if method != "GET":
            raise AssertionError("Unexpected API write in UI smoke: " + method + " " + path)
        reply(route, [])


def must(condition, message):
    if not condition:
        raise AssertionError(message)


def open_tab(page, target, mobile):
    nav = page.locator("nav.prp-mobile-tabs" if mobile else "nav.prp-main-nav")
    must(nav.is_visible(), "Expected navigation not visible")
    nav.locator('a[href="/prp/' + target + '"]').click()
    page.wait_for_url("**/prp/" + target)


def check_viewport(browser, width, height):
    mobile = width <= 860
    context = browser.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=2 if mobile else 1,
        is_mobile=mobile, has_touch=mobile, locale="zh-CN", reduced_motion="reduce",
        service_workers="block",
    )
    # Keep requests deterministic across engines: broadly intercept all requests,
    # then only fulfill the synthetic /api/ URLs. Asset requests are continued.
    # Do not allow an installed PWA worker to bypass test-only API interception.
    context.add_init_script("localStorage.setItem('matrix-prp-token', 'synthetic-ui-smoke-only')")
    state = {"completed": False, "writes": 0, "api_calls": [], "seen_api": []}
    def intercept(route):
        url = urlsplit(route.request.url)
        if "/api/" in url.path:
            state["seen_api"].append(route.request.method + " " + url.path)
            mock_api(route, state)
        else:
            route.continue_()
    context.route("**/*", intercept)
    page = context.new_page()
    exceptions = []
    console_errors = []
    failed_requests = []
    bad_responses = []
    page.on("pageerror", lambda error: exceptions.append(str(error)[:600]))
    page.on("console", lambda msg: console_errors.append(msg.text[:450]) if msg.type == "error" else None)
    page.on("requestfailed", lambda req: failed_requests.append(
        (req.method + " " + req.url.split("?", 1)[0])[-240:]
    ))
    page.on("response", lambda res: bad_responses.append(
        str(res.status) + " " + res.url.split("?", 1)[0][-200:]
    ) if res.status >= 400 else None)

    try:
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        try:
            page.locator(".home-v2-focus").wait_for(timeout=12000)
        except Exception:
            print("BOOT_DIAG viewport=" + str(width)
                  + " url=" + page.url
                  + " title=" + page.title()
                  + " ready=" + str(page.evaluate("document.readyState"))
                  + " app_text=" + repr(page.locator("#app").inner_text(timeout=1500)[:350])
                  + " html_len=" + str(page.evaluate("document.documentElement.outerHTML.length"))
                  + " errors=" + repr(exceptions[:5])
                  + " console_errors=" + repr(console_errors[:5])
                  + " request_failed=" + repr(failed_requests[:8])
                  + " http_errors=" + repr(bad_responses[:8]), flush=True)
            raise
        must(page.locator("nav.prp-main-nav a").count() == 4, "Desktop nav != 4")
        must(page.locator("nav.prp-mobile-tabs a").count() == 4, "Mobile nav != 4")
        must(page.locator("nav.prp-mobile-tabs").is_visible() == mobile, "Responsive tabbar visibility")

        button = page.locator(".home-v2-complete-button")
        button.wait_for(timeout=15000)
        # Preserve a clean before-action homepage screenshot in each viewport.
        # All visible content and authentication data are synthetic fixtures.
        page.screenshot(path=str(ARTIFACTS / f"home-{width}.png"), full_page=True)
        button.click()
        # Use actual DOM detachment, not RAF-based page.wait_for_function,
        # whose browser-engine scheduling may vary on hosted runners.
        try:
            button.wait_for(state="detached", timeout=10000)
        except Exception:
            print("TASK_DIAG viewport=" + str(width)
                  + " browser=" + os.environ.get("PRP_UI_BROWSER", "chromium")
                  + " writes=" + str(state["writes"])
                  + " completed=" + str(state["completed"])
                  + " api_calls=" + repr(state["api_calls"][-25:])
                  + " intercepted=" + repr(state["seen_api"][-25:])
                  + " button_count=" + str(button.count())
                  + " button_disabled=" + str(button.is_disabled())
                  + " button_text=" + repr(button.inner_text()[:100])
                  + " page_errors=" + repr(exceptions[-4:])
                  + " console_errors=" + repr(console_errors[-4:])
                  + " bad_responses=" + repr(bad_responses[-4:]), flush=True)
            raise
        must(state["writes"] == 1, "Task completion should make exactly one synthetic PATCH")
        print(f"PASS {width}px homepage, focus task update, four responsive tabs", flush=True)

        # Element Plus success toast from the synthetic task action must not
        # contaminate subsequent visual review evidence.
        page.locator(".el-message").wait_for(state="hidden", timeout=8000)
        open_tab(page, "apps", mobile)
        # The previous artifact only captured the 学习-filtered state. Capture
        # every registered group before search/favorites mutate the catalog.
        groups = page.locator(".prp-apps-group")
        group_filters = page.locator(".prp-app-filters button")
        must(group_filters.count() >= 2, "No registered app categories")
        must(groups.count() == group_filters.count() - 1,
             "Unfiltered app groups must match registered category filters")
        must(page.locator(".prp-apps-group-list a.prp-app-card").count() >= groups.count(),
             "Every unfiltered group should contain a registered app entry")
        page.screenshot(path=str(ARTIFACTS / f"apps-all-{width}.png"), full_page=True)
        print(f"PASS {width}px complete unfiltered app catalog visual capture", flush=True)
        page.get_by_placeholder("搜索应用名称或分类").fill("视频")
        must(page.locator(".prp-apps-group-list a.prp-app-card").count() >= 1,
             "Searching 视频 should show registered video app")
        page.get_by_placeholder("搜索应用名称或分类").fill("")
        page.locator(".prp-app-filters button").filter(has_text="学习").first.click()
        must(page.locator(".prp-apps-group").count() == 1, "Learning filter should show one group")
        before = page.evaluate("localStorage.getItem('matrix-prp:favorite-apps:7')")
        page.locator(".prp-apps-group .prp-favorite-button").first.click()
        after = page.evaluate("localStorage.getItem('matrix-prp:favorite-apps:7')")
        must(before != after, "Favorite toggle did not persist for synthetic user")
        page.screenshot(path=str(ARTIFACTS / f"apps-{width}.png"), full_page=True)
        print(f"PASS {width}px app catalog search, category, favorite persistence", flush=True)

        open_tab(page, "chat", mobile)
        textarea = page.locator(".chat-input textarea")
        textarea.wait_for(timeout=20000)
        textarea.fill("仅用于布局测试，不发送")
        must(page.locator(".chat-send").is_visible(), "Chat send control not visible")
        bounds = textarea.bounding_box()
        must(bounds is not None and bounds["y"] >= 0 and
             bounds["y"] + bounds["height"] <= height + 5,
             "Chat composer is outside the browser viewport")
        if mobile:
            must(page.locator("nav.prp-mobile-tabs").is_visible(),
                 "Mobile tabs disappeared without a virtual keyboard")
        page.screenshot(path=str(ARTIFACTS / f"chat-{width}.png"), full_page=False)
        print(f"PASS {width}px chat composer, responsive navigation (no virtual keyboard)", flush=True)

        if mobile:
            # Headless Chromium/WebKit do not open the iOS system keyboard.
            # Emulate only the visualViewport geometry and resize event to
            # exercise the actual Vue/CSS keyboard-aware layout state.
            geometry = page.evaluate("""() => {
                const vv = window.visualViewport
                if (!vv) return null
                const originalHeight = Object.getOwnPropertyDescriptor(vv, 'height')
                const originalOffset = Object.getOwnPropertyDescriptor(vv, 'offsetTop')
                const emulatedHeight = Math.max(220, window.innerHeight - 320)
                Object.defineProperty(vv, 'height', { configurable: true, value: emulatedHeight })
                Object.defineProperty(vv, 'offsetTop', { configurable: true, value: 0 })
                window.__restoreSmokeViewport = () => {
                    if (originalHeight) Object.defineProperty(vv, 'height', originalHeight)
                    else delete vv.height
                    if (originalOffset) Object.defineProperty(vv, 'offsetTop', originalOffset)
                    else delete vv.offsetTop
                    vv.dispatchEvent(new Event('resize'))
                }
                vv.dispatchEvent(new Event('resize'))
                return { expectedHeight: Math.round(emulatedHeight) }
            }""")
            must(geometry is not None, "visualViewport unavailable for synthetic keyboard check")
            shell = page.locator(".prp-shell-chat.prp-keyboard-open")
            try:
                shell.wait_for(timeout=5000)
                must(not page.locator("nav.prp-mobile-tabs").is_visible(),
                     "Bottom navigation must hide when the synthetic keyboard occupies the viewport")
                actual_height = shell.evaluate(
                    "(node) => node.style.getPropertyValue('--prp-chat-viewport-height').trim()"
                )
                must(actual_height == str(geometry["expectedHeight"]) + "px",
                     "Chat shell must use the visible synthetic viewport height: " + actual_height)
                page.screenshot(path=str(ARTIFACTS / f"chat-keyboard-simulated-{width}.png"),
                                full_page=False)
            finally:
                page.evaluate("() => window.__restoreSmokeViewport?.()")
            shell.wait_for(state="detached", timeout=5000)
            must(page.locator("nav.prp-mobile-tabs").is_visible(),
                 "Mobile navigation must return after synthetic keyboard closes")
            restored_height = page.locator(".prp-shell-chat").evaluate(
                "(node) => node.style.getPropertyValue('--prp-chat-viewport-height').trim()"
            )
            must(restored_height == "100dvh",
                 "Chat viewport should restore 100dvh after synthetic keyboard closes")
            print(f"PASS {width}px synthetic keyboard geometry, tab hiding and restoration", flush=True)

        open_tab(page, "me", mobile)
        if mobile:
            must(page.evaluate("document.activeElement?.tagName !== 'TEXTAREA'"),
                 "Navigation should blur the previously focused chat composer")
        page.locator(".prp-profile-card").wait_for()
        must(page.locator(".prp-me-admin").count() == 0, "Admin tools exposed to non-admin")
        print(f"PASS {width}px Me page and admin-only visibility", flush=True)

        page.goto(BASE + "wellness", wait_until="domcontentloaded")
        page.locator(".wellness-v2-intro").wait_for(timeout=20000)
        expected_tabs = ["AI 快速记录", "今日概览", "饮食", "运动", "身体指标", "目标设置"]
        for label in expected_tabs:
            must(page.get_by_role("tab", name=label).count() == 1,
                 "Missing health workflow tab: " + label)
        must(page.locator(".prp-back-to-apps").count() == 1,
             "Missing return-to-apps link from module page")
        page.screenshot(path=str(ARTIFACTS / f"wellness-{width}.png"), full_page=True)
        print(f"PASS {width}px six wellness workflows and app breadcrumb", flush=True)

        must(not exceptions, "Uncaught browser exceptions: " + "; ".join(exceptions[:4]))
    except Exception:
        try:
            page.screenshot(path=str(ARTIFACTS / f"failure-{width}.png"), full_page=True)
        except Exception:
            pass
        raise
    finally:
        context.close()


def main():
    engine = os.environ.get("PRP_UI_BROWSER", "chromium").lower()
    if engine not in {"chromium", "webkit"}:
        raise ValueError("Browser engine must be chromium or webkit")
    with sync_playwright() as p:
        browser_type = getattr(p, engine)
        # WebKit runs with its native Playwright sandbox. The Chromium runner
        # uses a disposable GitHub-hosted CI container with no privileged access.
        launch_options = {"headless": True}
        if engine == "chromium":
            launch_options["args"] = ["--no-sandbox"]
        browser = browser_type.launch(**launch_options)
        try:
            for width, height in [(1280, 900), (768, 900), (390, 844)]:
                check_viewport(browser, width, height)
        finally:
            browser.close()
    print(f"PASS UI V2 synthetic {engine} smoke on all three viewports.", flush=True)


if __name__ == "__main__":
    main()
