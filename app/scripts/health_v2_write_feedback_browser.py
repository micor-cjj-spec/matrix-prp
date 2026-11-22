#!/usr/bin/env python3
"""Synthetic Health V2 write/readback browser fault injection.

Mocks *all* API calls inside a loopback-only Playwright browser. No real PRP
HTTP server, credentials, health records, OAuth writes or real user data.
Distinct from the strict read-only smoke in health_v2_browser_smoke.py.
"""
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

import health_v2_browser_smoke as base

CASES = (
    "metric-committed-readback-failed",
    "exercise-committed-readback-failed",
    "goal-committed-readback-failed",
    "metric-ambiguous-response",
)
WRITE_PATHS = {
    "metric": "/wellness/body-metrics",
    "exercise": "/wellness/exercises",
    "goal": "/wellness/goals",
}
FAIL_MESSAGES = {
    "metric": "身体数据已保存，但页面刷新失败",
    "exercise": "运动记录已保存，但页面刷新失败",
    "goal": "健康目标已保存，但页面刷新失败",
}
UNCERTAIN_MESSAGE = "身体数据保存请求未确认"


def handle(route, state):
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
    target = WRITE_PATHS[state["kind"]]
    if path == target:
        state["requests"].append((method, path, parse_qs(url.query)))
        if method == "POST" and state["writes"] == 0:
            body = route.request.post_data_json
            if not isinstance(body, dict):
                state["unexpected_writes"].append("invalid synthetic body")
                route.fulfill(status=400, body="synthetic request only")
                return
            state["writes"] += 1
            if state["kind"] == "metric":
                item = {"id": 901, "measuredOn": body["measuredOn"],
                        "weightKg": str(body["weightKg"]),
                        "bodyFatPct": None, "waistCm": None}
            elif state["kind"] == "exercise":
                item = {"id": 902, "performedOn": body["performedOn"],
                        "name": body["name"], "durationMinutes": body["durationMinutes"],
                        "estimatedKcal": None, "note": ""}
            else:
                item = {"id": 903, "effectiveFrom": body["effectiveFrom"],
                        "dailyCalories": str(body["dailyCalories"]),
                        "dailyProteinG": None, "weeklyActivityMinutes": None}
            state["rows"].append(item)
            if state["case"].endswith("ambiguous-response"):
                # Simulate server commit then lost/5xx acknowledgement.
                route.fulfill(status=503, content_type="application/json",
                              body='{"code":"FAIL","message":"synthetic lost ack"}')
            else:
                state["fail_get_once"] = True
                base.send(route, item)
            return
        if method == "GET":
            if state["fail_get_once"]:
                state["fail_get_once"] = False
                state["get_failed"] += 1
                route.fulfill(status=503, content_type="application/json",
                              body='{"code":"FAIL","message":"synthetic readback unavailable"}')
                return
            base.send(route, state["rows"])
            return
        state["unexpected_writes"].append(method + " " + path)
        route.fulfill(status=405, body="not an allowed synthetic mutation")
        return

    # Reuse the original fail-closed GET-only interceptor for all other paths.
    base.intercept(route, state)


def check_row(page, case):
    if case.startswith("metric"):
        page.get_by_role("tab", name="身体指标").click()
        page.get_by_text("82.5 kg", exact=False).wait_for(timeout=12000)
    elif case.startswith("exercise"):
        page.get_by_role("tab", name="运动").click()
        page.get_by_text("模拟步行 · 30 分钟", exact=False).wait_for(timeout=12000)
    else:
        page.get_by_role("tab", name="目标设置").click()
        page.get_by_text("1900 kcal/天", exact=False).wait_for(timeout=12000)


def run_case(browser, case):
    kind = case.split("-", 1)[0]
    mobile = True
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=2,
        is_mobile=mobile, has_touch=mobile, locale="zh-CN",
        timezone_id="America/Los_Angeles", service_workers="block",
        reduced_motion="reduce",
    )
    context.add_init_script(
        "localStorage.setItem('matrix-prp-token', 'synthetic-browser-only')"
    )
    state = {"case": case, "kind": kind, "rows": [], "writes": 0,
             "fail_get_once": False, "get_failed": 0, "requests": [],
             "unknown_endpoints": [], "unexpected_writes": [],
             "external": [], "pageerrors": []}
    context.route("**/*", lambda route: handle(route, state))
    page = context.new_page()
    page.on("pageerror", lambda error: state["pageerrors"].append(str(error)[:300]))
    page.clock.set_fixed_time(datetime(2026, 11, 22, 0, 30, tzinfo=timezone.utc))
    label = base.ENGINE + "-390-" + case
    try:
        page.goto(base.BASE + "wellness", wait_until="domcontentloaded", timeout=30000)
        page.locator(".panel-head h2").filter(
            has_text="2026-11-22 饮食记录").wait_for(timeout=20000)
        if kind == "metric":
            page.get_by_role("tab", name="身体指标").click()
            page.get_by_role("button", name="新增测量").click()
            dialog = page.get_by_role("dialog", name="记录身体指标")
            field = dialog.locator(".el-input-number input").first
            field.fill("82.5")
            field.press("Tab")
            dialog.get_by_role("button", name="保存", exact=True).click()
        elif kind == "exercise":
            page.get_by_role("tab", name="运动").click()
            page.get_by_role("button", name="添加运动").click()
            dialog = page.get_by_role("dialog", name="添加运动")
            dialog.get_by_placeholder("步行、跑步、力量训练等").fill("模拟步行")
            dialog.get_by_role("button", name="保存", exact=True).click()
        else:
            page.get_by_role("tab", name="目标设置").click()
            field = page.locator(".form-panel .el-input-number input").first
            field.fill("1900")
            field.press("Tab")
            page.get_by_role("button", name="保存健康目标").click()

        if case.endswith("ambiguous-response"):
            page.get_by_text(UNCERTAIN_MESSAGE, exact=False).wait_for(timeout=12000)
            base.check(state["get_failed"] == 0,
                       "Ambiguous POST must not trigger a success readback")
        else:
            page.get_by_text(FAIL_MESSAGES[kind], exact=False).wait_for(timeout=12000)
            base.check(state["get_failed"] == 1,
                       "Expected exactly one injected post-write GET failure")
            base.check(not page.get_by_text(UNCERTAIN_MESSAGE, exact=False).is_visible(),
                       "Committed write wrongly described as unconfirmed")
        base.check(state["writes"] == 1 and len(state["rows"]) == 1,
                   "Synthetic mutation was lost or duplicated")
        # Reload is read-only. Verify persisted fake row and no implicit replay.
        page.reload(wait_until="domcontentloaded")
        page.get_by_role("heading", name="健康中心").wait_for(timeout=12000)
        check_row(page, case)
        base.check(state["writes"] == 1, "Page reload replayed the POST")
        base.check(not state["unexpected_writes"],
                   "Unexpected API write: " + repr(state["unexpected_writes"]))
        base.check(not state["unknown_endpoints"],
                   "Unknown API path: " + repr(state["unknown_endpoints"]))
        base.check(not state["external"], "External request attempted")
        base.check(not state["pageerrors"], "Uncaught browser JS exception")
        print("PASS", label, "synthetic one write, failure feedback and reload",
              flush=True)
    except Exception:
        page.screenshot(path=str(base.OUTPUT / ("failure-" + label + ".png")),
                        full_page=True)
        print("DIAG", label, "writes", state["writes"],
              "get_failed", state["get_failed"],
              "api_paths", [x[1] for x in state["requests"]][-30:],
              "unknown", state["unknown_endpoints"],
              "external", state["external"],
              "pageerrors", state["pageerrors"], flush=True)
        raise
    finally:
        context.close()


def main():
    if base.ENGINE not in ("chromium", "webkit"):
        raise ValueError("Only Chromium/WebKit synthetic browsers supported")
    with sync_playwright() as playwright:
        bt = getattr(playwright, base.ENGINE)
        options = {"headless": True}
        if base.ENGINE == "chromium":
            options["args"] = ["--no-sandbox"]
        browser = bt.launch(**options)
        try:
            for case in CASES:
                run_case(browser, case)
        finally:
            browser.close()
    print("ALL_SYNTHETIC_WRITE_FEEDBACK_CASES=PASS; REAL_STAGE_AND_IPHONE=NOT_TESTED",
          flush=True)


if __name__ == "__main__":
    main()
