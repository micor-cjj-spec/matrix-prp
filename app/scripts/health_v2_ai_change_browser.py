#!/usr/bin/env python3
"""Synthetic lost-response AI delete confirmation, Chromium/WebKit, loopback only.

No real PRP backend, user data, authorization grant, OAuth or SSH. This tests
client acknowledgement semantics; actual transactional/owner security is
separately verified by Java tests and isolated staging UAT.
"""
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import health_v2_browser_smoke as base

DRAFT_ID = "123e4567-e89b-12d3-a456-426614174000"
BEFORE = {
    "date": "2026-11-22", "mealType": "LUNCH", "note": "仅合成数据",
    "items": [{"foodId": 0, "name": "模拟午餐", "grams": 0, "calories": 345}],
}
DRAFT = {
    "draftId": DRAFT_ID, "action": "meal.delete",
    "description": "模拟删除目标", "before": BEFORE, "after": BEFORE,
    "expiresAt": "2026-11-22T12:30:00",
}

def intercept(route, state):
    url = urlsplit(route.request.url)
    if url.hostname not in ("127.0.0.1", "localhost"):
        state["external"].append(url.hostname or "unknown")
        route.abort()
        return
    if "/api/" not in url.path:
        route.continue_()
        return
    path = "/" + url.path.split("/api/", 1)[1]
    method = route.request.method
    state["requests"].append((method, path, {}))
    if method == "GET" and path == "/wellness/meals":
        base.send(route, [] if state["deleted"] else [base.MEAL])
        return
    if method == "POST" and path == "/wellness/ai/changes/prepare":
        body = route.request.post_data_json
        base.check(body["kind"] == "meal" and body["recordId"] == 70
                   and body["operation"] == "delete",
                   "Wrong synthetic delete preview selection")
        state["prepare_posts"] += 1
        base.send(route, DRAFT)
        return
    if method == "POST" and path == "/wellness/ai/changes/" + DRAFT_ID + "/confirm":
        state["confirm_posts"] += 1
        state["deleted"] = True
        # The fake backend commits, but the browser receives an HTTP error.
        route.fulfill(status=503, content_type="application/json",
                      body='{"code":"FAIL","message":"synthetic lost confirm acknowledgement"}')
        return
    if method == "GET" and path == "/wellness/ai/changes/" + DRAFT_ID + "/status":
        state["status_reads"] += 1
        if state["case"] == "confirmed":
            base.send(route, {"status": "CONSUMED"})
        else:
            route.fulfill(status=503, content_type="application/json",
                          body='{"code":"FAIL","message":"synthetic status read unavailable"}')
        return
    if method != "GET":
        state["unexpected_writes"].append(method + " " + path)
        route.fulfill(status=405, body="no unrelated synthetic writes allowed")
        return
    base.intercept(route, state)

def run_case(browser, case):
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2, is_mobile=True, has_touch=True,
        locale="zh-CN", timezone_id="America/Los_Angeles",
        service_workers="block", reduced_motion="reduce",
    )
    context.add_init_script(
        "localStorage.setItem('matrix-prp-token', 'synthetic-browser-only')"
    )
    state = {
        "case": case, "deleted": False, "prepare_posts": 0,
        "confirm_posts": 0, "status_reads": 0, "requests": [],
        "external": [], "unknown_endpoints": [],
        "unexpected_writes": [], "pageerrors": [],
    }
    context.route("**/*", lambda route: intercept(route, state))
    page = context.new_page()
    page.on("pageerror", lambda error: state["pageerrors"].append(str(error)[:300]))
    page.clock.set_fixed_time(datetime(2026, 11, 22, 0, 30, tzinfo=timezone.utc))
    label = base.ENGINE + "-390-ai-delete-lost-ack-" + case
    try:
        page.goto(base.BASE + "wellness", wait_until="domcontentloaded", timeout=30000)
        page.get_by_role("heading", name="健康中心").wait_for(timeout=20000)
        page.get_by_role("tab", name="AI 快速记录").click()
        page.get_by_role("button", name="修改 / 删除已有记录").click()
        panel = page.locator(".wellness-change")
        panel.locator('input[type="date"]').fill("2026-11-22")
        panel.locator("select").nth(1).select_option("70")
        panel.locator("select").nth(2).select_option("delete")
        panel.get_by_role("button", name="预览删除目标").click()
        panel.get_by_text("操作预览 · meal.delete", exact=False).wait_for(timeout=12000)
        panel.locator('input[type="checkbox"]').check()
        panel.get_by_role("button", name="确认删除").click()
        if case == "confirmed":
            page.get_by_text("已核实记录删除成功", exact=False).wait_for(timeout=12000)
        else:
            panel.get_by_text("修改或删除确认请求结果未核实", exact=False).wait_for(timeout=12000)
            base.check(panel.get_by_role("button", name="确认删除").is_disabled(),
                       "Uncertain result allowed a repeated confirm POST")
            panel.get_by_role("button", name="重新读取记录后解锁新草稿").click()
            panel.get_by_text("列表已重新读取", exact=False).wait_for(timeout=12000)
        base.check(state["prepare_posts"] == 1, "Expected one preview")
        base.check(state["confirm_posts"] == 1, "Unexpected confirmation replay")
        base.check(state["status_reads"] == 1, "Expected exactly one owner status GET")
        base.check(state["deleted"], "Synthetic backend did not commit")
        base.check(not state["unexpected_writes"], repr(state["unexpected_writes"]))
        base.check(not state["unknown_endpoints"], repr(state["unknown_endpoints"]))
        base.check(not state["external"], "External request attempted")
        base.check(not state["pageerrors"], repr(state["pageerrors"]))
        print("PASS", label, "one confirm POST, one status GET, no replay", flush=True)
    except Exception:
        page.screenshot(path=str(base.OUTPUT / ("failure-" + label + ".png")),
                        full_page=True)
        print("DIAG", label, "prepare", state["prepare_posts"],
              "confirm", state["confirm_posts"], "status", state["status_reads"],
              "requests", [x[0] + " " + x[1] for x in state["requests"]][-35:],
              "unexpected", state["unexpected_writes"],
              "unknown", state["unknown_endpoints"], flush=True)
        raise
    finally:
        context.close()

def main():
    if base.ENGINE not in ("chromium", "webkit"):
        raise ValueError("Only Chromium/WebKit synthetic browsers supported")
    with sync_playwright() as playwright:
        browser_type = getattr(playwright, base.ENGINE)
        options = {"headless": True}
        if base.ENGINE == "chromium":
            options["args"] = ["--no-sandbox"]
        browser = browser_type.launch(**options)
        try:
            for case in ("confirmed", "unknown"):
                run_case(browser, case)
        finally:
            browser.close()
    print("AI_CHANGE_LOST_ACK_SYNTHETIC=PASS; REAL_STAGE_AND_IPHONE=NOT_TESTED",
          flush=True)

if __name__ == "__main__":
    main()
