#!/usr/bin/env python3
"""Personal OS owner-reviewed goal relations, mobile Chromium/WebKit, synthetic only.

All /api requests are intercepted; no real identity, model, OAuth, host or DB.
Headless WebKit is NOT physical iPhone Safari or a real on-screen keyboard.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

BASE = os.getenv("PRP_OS_MOBILE_URL", "http://127.0.0.1:4173/prp/personal-os")
SHOTS = Path(os.getenv("PRP_OS_MOBILE_SHOTS", "/tmp/prp-os-mobile-synthetic"))
SHOTS.mkdir(parents=True, exist_ok=True)
ENGINE = os.getenv("PRP_OS_BROWSER", "webkit")
GOAL = {
    "id": 31, "title": "CI 手机端目标", "description": "仅合成测试",
    "domain": "career", "status": "ACTIVE", "priority": "medium",
    "successCriteria": "检查二次确认", "targetDate": None,
    "createdAt": "2026-11-22T08:00:00", "updatedAt": "2026-11-22T08:00:00"
}
TASK = {
    "id": 91, "moduleCode": "learning", "title": "CI 已有任务",
    "description": "Synthetic only", "priority": "medium", "status": "todo",
    "createdAt": "2026-11-22T08:00:00", "dueDate": None,
}
REVIEW = {
    "id": 42, "reviewType": "weekly", "moduleCode": "life",
    "title": "CI 已有复盘", "summary": "Synthetic only",
    "highlights": "", "problems": "", "nextActions": "",
    "periodStart": "2026-11-01", "periodEnd": "2026-11-08",
    "createdAt": "2026-11-22T08:00:00",
}
USER = {
    "id": 7, "username": "ci_mobile_owner",
    "displayName": "合成测试账号", "administrator": False
}


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def result(route, value, status=200):
    route.fulfill(
        status=status, content_type="application/json; charset=utf-8",
        body=json.dumps({"code": "SUCCESS", "message": "synthetic", "data": value},
                        ensure_ascii=False),
    )


def intercept_api(route, state):
    req = route.request
    url = urlsplit(req.url)
    if url.hostname not in ("127.0.0.1", "localhost") or "/api/" not in url.path:
        raise AssertionError("Non-local API request was attempted")
    path = "/" + url.path.split("/api/", 1)[1]
    method = req.method
    state["calls"].append((method, path))
    check(req.headers.get("authorization") == "Bearer synthetic-personal-os",
          "Missing synthetic owner authorization header")
    if method == "GET":
        if path == "/users/me":
            result(route, USER)
        elif path == "/goals":
            result(route, [GOAL])
        elif path == "/goals/31/context":
            result(route, list(state["links"]))
        elif path == "/tasks":
            result(route, [TASK])
        elif path == "/reviews":
            result(route, [REVIEW])
        elif path in ("/memory/candidates", "/memory"):
            result(route, [])
        else:
            # AppLayout may request read-only features unrelated to Personal OS.
            # Never return real user data; unexpected mutations remain forbidden.
            result(route, [])
        return
    if method == "POST" and path == "/memory/candidates":
        payload = req.post_data_json
        subject = payload.get("subjectType")
        expected = {"TASK": (91, "ADVANCES"), "REVIEW": (42, "EVALUATES")}
        check(subject in expected, "Unexpected candidate subject")
        sid, predicate = expected[subject]
        check(payload.get("predicate") == predicate
              and payload.get("subjectRef") == str(sid)
              and payload.get("objectType") == "GOAL"
              and payload.get("objectRef") == "31"
              and payload.get("sourceType") == subject
              and payload.get("sourceRef") == str(sid)
              and payload.get("sensitivity") == "NORMAL",
              "Invalid owner-reviewed ontology candidate")
        same = [m for m in state["facts"].values()
                if m["subjectType"] == subject and m["subjectRef"] == str(sid)]
        if same:
            record = same[0]
        else:
            number = 100 + len(state["facts"])
            record = {"id": number, "subjectType": subject,
                      "subjectRef": str(sid), "predicate": predicate,
                      "objectType": "GOAL", "objectRef": "31",
                      "objectValue": None, "sourceType": subject,
                      "sourceRef": str(sid), "status": "PENDING",
                      "sensitivity": "NORMAL"}
            state["facts"][number] = record
        state["candidate_posts"] += 1
        result(route, record)
        return
    if method == "POST" and path.startswith("/memory/") and path.endswith("/confirm"):
        number = int(path.split("/")[2])
        check(number in state["facts"], "Cannot confirm unknown relation")
        record = state["facts"][number]
        record["status"] = "CONFIRMED"
        state["links"] = [
            {k: v for k, v in m.items() if k not in
             ("id", "status", "sourceType", "sourceRef", "sensitivity")}
            | {"assertionId": m["id"]}
            for m in state["facts"].values() if m["status"] == "CONFIRMED"
        ]
        state["confirmation_posts"] += 1
        result(route, record)
        return
    raise AssertionError("Unexpected first-party API mutation: "
                         + method + " " + path)


def picker(page, kind, item):
    task = kind == "task"
    title = "选择已有任务关联目标" if task else "选择已有复盘关联目标"
    open_label = "关联已有任务（先选择）" if task else "关联已有复盘（先选择）"
    submit = "审核关联" if task else "审核复盘关联"
    page.get_by_role("button", name=open_label).click()
    dialog = page.locator(".el-dialog").filter(
        has=page.get_by_text(title, exact=True))
    dialog.wait_for(state="visible", timeout=15000)
    dialog.locator(".el-select").click()
    # Click the real rendered option. Never force a disabled review button:
    # the owner must have a selected item, valid goal and matching identity.
    page.get_by_text(item, exact=True).click()
    submit_button = dialog.get_by_role("button", name=submit)
    try:
        submit_button.click(timeout=8000)
    except PlaywrightTimeoutError:
        # A prior WebKit 390px job intermittently clicked a dropdown item but
        # kept the owner-review button disabled. Log ONLY synthetic DOM state,
        # not auth tokens, API bodies, personal messages or browser storage.
        diagnosis = dialog.evaluate("""(root, label) => {
          const select = root.querySelector('.el-select');
          const buttons = Array.from(root.querySelectorAll('button'));
          const submit = buttons.find(b => b.textContent.trim() === label);
          const options = Array.from(document.querySelectorAll(
            '.el-select-dropdown__item')).filter(el => el.getClientRects().length > 0);
          return {
            buttonDisabled: submit ? submit.disabled : null,
            selectDisabled: select ? select.classList.contains('is-disabled') : null,
            selectText: (select?.innerText || '').trim().slice(0, 100),
            selectInputValue: select?.querySelector('input')?.value?.slice(0, 100) || '',
            openOptions: options.length,
            selectedOptions: options.filter(el => el.classList.contains('is-selected'))
              .map(el => (el.innerText || '').trim().slice(0, 100)),
            visibleDialog: root.getClientRects().length > 0
          };
        }""", submit)
        print("CI_PERSONAL_OS_PICKER_STATE=" +
              json.dumps({"browser": ENGINE, "width": page.viewport_size["width"],
                          "kind": kind, **diagnosis}, ensure_ascii=False),
              flush=True)
        raise
    label = "确认关联到此目标" if task else "确认复盘关联到此目标"
    page.get_by_role("button", name=label).wait_for(
        state="visible", timeout=15000)


def smoke(browser, width, height):
    context = browser.new_context(
        viewport={"width": width, "height": height},
        is_mobile=width <= 430, has_touch=width <= 430,
        device_scale_factor=2 if width <= 430 else 1,
        locale="zh-CN", reduced_motion="reduce", service_workers="block",
    )
    context.add_init_script(
        "localStorage.setItem('matrix-prp-token', 'synthetic-personal-os')")
    state = {"calls": [], "facts": {}, "links": [], "candidate_posts": 0,
             "confirmation_posts": 0}
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    context.route("**/api/**", lambda route: intercept_api(route, state))
    # Never accidentally send requests to remote services.
    context.route("https://**/*", lambda route: route.abort())
    try:
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        page.get_by_text("CI 手机端目标", exact=True).first.wait_for(timeout=20000)
        check(not [c for c in state["calls"] if c[1] in ("/tasks", "/reviews")],
              "Private task/review titles fetched without an owner click")
        check(not [c for c in state["calls"] if c[1].startswith("/memory/private")],
              "Restricted memories fetched by default")
        page.locator(".os-goal-card .os-goal-select").first.click()
        page.get_by_role("button", name="关联已有任务（先选择）").wait_for()
        check(state["candidate_posts"] == 0 and state["confirmation_posts"] == 0,
              "Opened goal already wrote an assertion")
        print(f"PASS {ENGINE} {width}: personal goal initial privacy", flush=True)

        picker(page, "task", "CI 已有任务 (#91)")
        check(state["candidate_posts"] == 0, "Selecting task wrote relation")
        page.get_by_role("button", name="暂不关联", exact=True).click()
        check(state["candidate_posts"] == 0 and state["confirmation_posts"] == 0,
              "Canceling task still wrote relation")
        picker(page, "task", "CI 已有任务 (#91)")
        page.get_by_role("button", name="确认关联到此目标", exact=True).click()
        page.locator(".os-context .os-evidence span").filter(
            has_text="任务 #91").wait_for(timeout=15000)
        check(state["candidate_posts"] == 1 and state["confirmation_posts"] == 1,
              "Task relation requires exactly one proposal and confirmation")
        print(f"PASS {ENGINE} {width}: task select/cancel/explicit confirm", flush=True)

        picker(page, "review", "CI 已有复盘 (#42)")
        page.get_by_role("button", name="暂不关联复盘", exact=True).click()
        check(state["candidate_posts"] == 1 and state["confirmation_posts"] == 1,
              "Canceling review still wrote relation")
        picker(page, "review", "CI 已有复盘 (#42)")
        page.get_by_role("button", name="确认复盘关联到此目标", exact=True).click()
        page.locator(".os-context .os-evidence span").filter(
            has_text="复盘 #42").wait_for(timeout=15000)
        check(state["candidate_posts"] == 2 and state["confirmation_posts"] == 2,
              "Review relation requires exactly one proposal and confirmation")
        check(not [c for c in state["calls"] if c[1].startswith("/ai/")],
              "Preview test must not invoke any AI endpoint")
        check(not errors, "Browser runtime exception: " + str(errors[:3]))
        print(f"PASS {ENGINE} {width}: review select/cancel/explicit confirm", flush=True)

        bounds = page.evaluate("""() => ({
          viewport: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          appWidth: document.querySelector('.personal-os-page')?.getBoundingClientRect().width
        })""")
        check(bounds["documentWidth"] <= bounds["viewport"] + 4,
              "Unexpected horizontal page scrolling on mobile: " + str(bounds))
        page.screenshot(path=str(SHOTS / f"{ENGINE}-{width}.png"), full_page=True)
        page.locator(".el-segmented").get_by_text("个人记忆", exact=True).click()
        page.get_by_text("补充个人事实", exact=True).wait_for(timeout=12000)
        check(not [c for c in state["calls"] if c[1] in
                   ("/memory/private", "/memory/history/normal")],
              "Private/normal history loaded without owner action")
        print(f"PASS {ENGINE} {width}: responsive layout, private history opt-in", flush=True)
    except Exception:
        page.screenshot(path=str(SHOTS / f"failure-{ENGINE}-{width}.png"),
                        full_page=True)
        raise
    finally:
        context.close()


def main():
    check(ENGINE in ("chromium", "webkit"), "Unsupported engine")
    with sync_playwright() as playwright:
        engine = getattr(playwright, ENGINE)
        opts = {"headless": True}
        if ENGINE == "chromium":
            opts["args"] = ["--no-sandbox"]
        browser = engine.launch(**opts)
        try:
            # More attempts on WebKit surface intermittent event/selection
            # errors; every attempt executes the full cancel/no-write path.
            repeats = 3 if ENGINE == "webkit" else 1
            for width, height in ((390, 844), (768, 900)):
                for attempt in range(1, repeats + 1):
                    smoke(browser, width, height)
                    print(f"CI_PERSONAL_OS_{ENGINE.upper()}_{width}_REPEAT={attempt}/{repeats}:PASS",
                          flush=True)
        finally:
            browser.close()
    print("PASS all Personal OS synthetic mobile cross-engine checks", flush=True)


if __name__ == "__main__":
    main()
