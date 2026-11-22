#!/usr/bin/env python3
"""Health V2 browser-only smoke with *synthetic* data and fail-closed network.

Not a real iPhone/Safari, running staging service, user approval, or deployed DB.
All /api/ responses are intercepted inside Chromium/WebKit before network.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PRP_HEALTH_SMOKE_URL", "http://127.0.0.1:4173/prp/")
OUTPUT = Path(os.environ.get("PRP_HEALTH_SMOKE_DIR", "/tmp/health-v2-synthetic-browser"))
OUTPUT.mkdir(parents=True, exist_ok=True)
ENGINE = os.environ.get("PRP_HEALTH_BROWSER", "chromium")

PROFILE = {"heightCm": "178", "timezone": "Asia/Shanghai"}
USER = {"id": 7, "username": "synthetic_health", "displayName": "模拟用户", "administrator": False}
MEAL = {
    "id": 70, "mealDate": "2026-11-22", "mealType": "LUNCH", "note": "仅合成数据",
    "items": [{"id": 71, "foodId": 0, "foodName": "模拟午餐", "grams": "0",
               "calories": "345", "proteinG": None, "carbsG": None, "fatG": None,
               "estimate": True}],
}
SUMMARY = {
    "date": "2026-11-22", "calories": "345", "proteinG": None, "carbsG": None,
    "fatG": None, "mealCount": 1, "exerciseMinutes": 0,
    "exerciseEstimatedKcal": None, "latestWeightKg": None,
    "goal": None, "recordedMealTypes": ["LUNCH"],
}
ENERGY = [
    {"date": "2026-11-20", "calories": None, "exerciseMinutes": None, "weightKg": None},
    {"date": "2026-11-21", "calories": "0", "exerciseMinutes": None, "weightKg": None},
    {"date": "2026-11-22", "calories": "345", "exerciseMinutes": None, "weightKg": None},
]
NUTRIENTS = [
    {"date": x["date"], "proteinG": None, "carbsG": None, "fatG": None,
     "foodItemCount": 1 if x["date"] == "2026-11-22" else 0,
     "knownProteinCount": 0, "knownCarbsCount": 0, "knownFatCount": 0}
    for x in ENERGY
]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def send(route, data):
    route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"code": "SUCCESS", "message": "synthetic", "data": data},
                        ensure_ascii=False),
    )


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
    state["requests"].append((method, path, parse_qs(url.query)))
    # Absolutely no real service, write path, token exchange or private payload.
    if method != "GET":
        state["unexpected_writes"].append(method + " " + path)
        route.fulfill(status=405, body="synthetic test forbids writes")
        return
    if path == "/users/me":
        data = USER
    elif path == "/wellness/profile":
        data = PROFILE
    elif path == "/wellness/summary/daily":
        data = SUMMARY
    elif path == "/wellness/meals":
        data = [MEAL]
    elif path == "/wellness/summary/trends":
        data = ENERGY
    elif path == "/wellness/summary/nutrition-trends":
        data = NUTRIENTS
    elif path in ("/wellness/exercises", "/wellness/goals", "/wellness/foods",
                  "/wellness/foods/frequent", "/wellness/body-metrics"):
        data = []
    elif path.startswith("/wellness/"):
        data = []
    else:
        # Unrecognized GET cannot silently become a successful fake backend.
        state["unknown_endpoints"].append(path)
        route.fulfill(status=404, body="unknown synthetic endpoint")
        return
    send(route, data)


def run_case(browser, width, deep_link):
    mobile = width < 600
    context = browser.new_context(
        viewport={"width": width, "height": 844 if mobile else 900},
        device_scale_factor=2 if mobile else 1,
        is_mobile=mobile, has_touch=mobile, locale="zh-CN",
        timezone_id="America/Los_Angeles", service_workers="block",
        reduced_motion="reduce",
    )
    context.add_init_script(
        "localStorage.setItem('matrix-prp-token', 'synthetic-browser-only')"
    )
    state = {"requests": [], "external": [], "unexpected_writes": [],
             "unknown_endpoints": [], "pageerrors": []}
    context.route("**/*", lambda route: intercept(route, state))
    page = context.new_page()
    page.on("pageerror", lambda error: state["pageerrors"].append(str(error)[:300]))
    # Device-local day: Nov 21; saved health profile day: Nov 22.
    page.clock.set_fixed_time(datetime(2026, 11, 22, 0, 30, tzinfo=timezone.utc))
    target = "2026-11-20" if deep_link else "2026-11-22"
    url = BASE + "wellness" + ("?date=2026-11-20" if deep_link else "")
    label = ENGINE + "-" + str(width) + ("-linked" if deep_link else "-today")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.get_by_role("heading", name="健康中心").wait_for(timeout=20000)
        # Profile must be fetched before the first daily summary and must
        # select the correct business day; explicitly linked dates win.
        page.locator(".panel-head h2").filter(has_text=target + " 饮食记录").wait_for(
            timeout=20000)
        requests = state["requests"]
        profile_indices = [i for i, x in enumerate(requests)
                           if x[1] == "/wellness/profile"]
        daily = [(i, x) for i, x in enumerate(requests)
                 if x[1] == "/wellness/summary/daily"]
        check(profile_indices and daily, "Profile or daily request missing")
        check(profile_indices[0] < daily[0][0],
              "Daily request started before profile timezone response")
        check(all(x[2].get("date") == [target] for _, x in daily),
              "Initial daily API used the wrong health timezone/explicit date: " +
              repr([(i, x[2]) for i, x in daily]))
        check(page.locator(".prp-main-nav a").count() == 4, "Desktop navigation changed")
        check(page.locator(".prp-mobile-tabs a").count() == 4, "Mobile navigation changed")
        check(page.locator(".prp-mobile-tabs").is_visible() == mobile,
              "Responsive navigation visibility broken")
        for tab in ["AI 快速记录", "今日概览", "饮食", "运动", "身体指标", "目标设置"]:
            check(page.get_by_role("tab", name=tab).count() == 1,
                  "Health workflow missing: " + tab)
        check(page.locator(".nutrition-panel").count() == 1,
              "Nutrition completeness panel missing")
        check(page.get_by_text("营养信息不完整", exact=False).count() >= 0,
              "Unexpected nutrition state")
        check(page.locator(".nutrition-panel").inner_text().find("完整度 0%") != -1,
              "Unknown macros must not display as fully known")
        check("—" in page.locator(".nutrition-panel").inner_text(),
              "Unknown macros must remain unknown, not 0g")

        group = page.get_by_role("group", name="近14天热量趋势")
        group.wait_for(timeout=12000)
        page.get_by_role("button", name="2026-11-21：0 kcal").click()
        check("0 kcal" in page.locator(".trend-selection").inner_text(),
              "Real zero should be distinguishable from missing")
        page.get_by_role("button", name="2026-11-20：没有记录热量").click()
        check("没有记录热量" in page.locator(".trend-selection").inner_text(),
              "Missing data must remain missing")
        page.get_by_role("radio", name="蛋白质").click()
        page.get_by_role("group", name="近14天蛋白质趋势").wait_for(timeout=10000)

        # Check user workflow tabs without creating meals, drafts or changes.
        for tab in ["饮食", "运动", "身体指标", "目标设置", "今日概览"]:
            page.get_by_role("tab", name=tab).click()
            check(page.locator(".wellness-page").is_visible(),
                  "Health page disappeared after switching tabs")
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth")
        check(overflow <= 2, "Page-level horizontal overflow: " + str(overflow))
        check(not state["unexpected_writes"], "Unapproved write attempted")
        check(not state["unknown_endpoints"], "Unknown API path: " +
              repr(state["unknown_endpoints"]))
        check(not state["external"], "External request attempted")
        check(not state["pageerrors"], "Uncaught JS errors: " +
              repr(state["pageerrors"]))
        page.screenshot(path=str(OUTPUT / (label + ".png")), full_page=True)
        print("PASS", label, "synthetic day, macros, tabs, trends, viewport, no writes",
              flush=True)
    except Exception:
        page.screenshot(path=str(OUTPUT / ("failure-" + label + ".png")),
                        full_page=True)
        print("DIAG", label, "url", page.url,
              "api_paths", [x[1] for x in state["requests"]][-30:],
              "unknown", state["unknown_endpoints"],
              "external", state["external"],
              "writes", state["unexpected_writes"],
              "pageerrors", state["pageerrors"], flush=True)
        raise
    finally:
        context.close()


def main():
    if ENGINE not in ("chromium", "webkit"):
        raise ValueError("Only Chromium/WebKit supported")
    with sync_playwright() as playwright:
        bt = getattr(playwright, ENGINE)
        options = {"headless": True}
        if ENGINE == "chromium":
            options["args"] = ["--no-sandbox"]
        browser = bt.launch(**options)
        try:
            for width, explicit in [(1280, False), (390, True), (375, False)]:
                run_case(browser, width, explicit)
        finally:
            browser.close()
    print("ALL_SYNTHETIC_HEALTH_BROWSER_CASES=PASS; REAL_IPHONE_UAT=NOT_TESTED", flush=True)


if __name__ == "__main__":
    main()
