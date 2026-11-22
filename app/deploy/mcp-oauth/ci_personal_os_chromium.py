#!/usr/bin/env python3
"""Synthetic Personal OS browser review on the existing disposable PRP Chromium stack.

Only enabled by the stacked T-004 CI workflow. No real user data, passwords,
URLs with OAuth codes, or personal memory contents are logged.
"""
import json
import os
import time
from urllib.parse import urlsplit


def run(page, origin):
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_CHROMIUM") != "true"
            or os.environ.get("MCP_E2E_PERSONAL_OS") != "true"
            or origin != "https://prp-e2e.localhost"):
        raise RuntimeError("PERSONAL_OS_BROWSER_DISPOSABLE_CI_ONLY")

    # Count paths only. Never log memory values or authentication headers.
    private_requests = []
    routine_memory_requests = []
    normal_history_requests = []
    def observe(req):
        # Vue is deployed under /prp/; do not assume the backend-local /api/ prefix.
        path = urlsplit(req.url).path
        if path.endswith("/api/memory/private"):
            private_requests.append(1)
        elif path.endswith("/api/memory/history/normal"):
            normal_history_requests.append(1)
        elif path.endswith("/api/memory") or path.endswith("/api/memory/candidates"):
            routine_memory_requests.append(1)
    page.on("request", observe)

    # Start with real authenticated first-party Vue UI and fresh isolated MySQL.
    page.goto(origin + "/prp/personal-os", wait_until="domcontentloaded",
              timeout=30000)
    page.locator(".os-hero h1").wait_for(state="visible", timeout=20000)
    if page.locator(".os-alert").is_visible():
        raise RuntimeError("PERSONAL_OS_BACKEND_NOT_AVAILABLE")
    if private_requests or routine_memory_requests or normal_history_requests:
        raise RuntimeError("PERSONAL_OS_MEMORY_FETCH_BEFORE_OWNER_OPENS_TAB")

    # The only way to create a goal here is an explicit first-party form submit.
    page.get_by_placeholder("例如：完成一个阶段性学习计划").fill(
        "CI-only first-party goal")
    page.get_by_role("button", name="创建目标").click()
    page.locator(".os-goal-card").filter(
        has_text="CI-only first-party goal").wait_for(
            state="visible", timeout=15000)

    page.locator(".el-segmented").get_by_text(
        "个人记忆", exact=True).click()
    page.get_by_text("补充个人事实", exact=True).wait_for(
        state="visible", timeout=15000)
    page.locator(".os-panel textarea").fill(
        "CI-only private fact for browser approval")
    page.get_by_role("button", name="保存为待确认候选").click()
    pending = page.locator(".os-list-panel article.os-memory-card").filter(
        has_text="CI-only private fact for browser approval")
    pending.wait_for(state="visible", timeout=15000)
    if not routine_memory_requests:
        raise RuntimeError("PERSONAL_OS_MEMORY_TAB_DID_NOT_LOAD")
    if private_requests:
        raise RuntimeError("PERSONAL_OS_PRIVATE_MEMORY_FETCH_BEFORE_CLICK")
    if normal_history_requests:
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_FETCH_BEFORE_CLICK")

    # The candidate must require the owner's separate confirmation dialogue.
    pending.get_by_role("button", name="确认事实").click()
    page.locator(".el-message-box").get_by_role(
        "button", name="我已核对，确认").click()
    pending.wait_for(state="detached", timeout=15000)
    if page.get_by_text("CI-only private fact for browser approval").count() != 0:
        raise RuntimeError("PERSONAL_OS_RESTRICTED_FACT_VISIBLE_BY_DEFAULT")

    # Only an explicit click may read SENSITIVE/RESTRICTED material.
    page.get_by_role("button", name="主动查看并管理").click()
    private = page.locator(".os-private article.os-memory-card").filter(
        has_text="CI-only private fact for browser approval")
    private.wait_for(state="visible", timeout=15000)
    if len(private_requests) != 1:
        raise RuntimeError("PERSONAL_OS_PRIVATE_FETCH_COUNT_INVALID")

    # Leaving the memory tab clears the sensitive panel and its visible text.
    page.locator(".el-segmented").get_by_text(
        "我的目标", exact=True).click()
    if page.get_by_text("CI-only private fact for browser approval").count() != 0:
        raise RuntimeError("PERSONAL_OS_PRIVATE_FACT_PERSISTS_ON_TAB_SWITCH")
    page.locator(".el-segmented").get_by_text(
        "个人记忆", exact=True).click()
    if page.get_by_text("CI-only private fact for browser approval").count() != 0:
        raise RuntimeError("PERSONAL_OS_PRIVATE_FACT_REOPENED_AUTOMATICALLY")

    page.get_by_role("button", name="主动查看并管理").click()
    private = page.locator(".os-private article.os-memory-card").filter(
        has_text="CI-only private fact for browser approval")
    private.wait_for(state="visible", timeout=15000)
    # Invalidation must suppress normal retrieval without losing the
    # owner's ability to find and permanently erase historical private data.
    private.get_by_role("button", name="作废").click()
    page.locator(".el-message-box").get_by_role(
        "button", name="作废").click()
    private.locator("small").filter(has_text="已作废").wait_for(
        state="visible", timeout=15000)
    if private.get_by_role("button", name="更正").count() != 0:
        raise RuntimeError("PERSONAL_OS_ARCHIVED_MEMORY_STILL_EDITABLE")
    private.get_by_role("button", name="永久删除").click()
    page.locator(".el-message-box").get_by_role(
        "button", name="永久删除").click()
    private.wait_for(state="detached", timeout=15000)

    # Management fetch is still opt-in, and successful deletion is permanent.
    page.get_by_role("button", name="收起并清除本页内容").click()
    page.get_by_role("button", name="主动查看并管理").click()
    page.locator(".os-private .el-empty").wait_for(
        state="visible", timeout=15000)
    if page.get_by_text("CI-only private fact for browser approval").count() != 0:
        raise RuntimeError("PERSONAL_OS_PRIVATE_FACT_NOT_ERASED")

    # T-008c: NORMAL history is a separate, owner-click-only endpoint even
    # though an explicitly NORMAL confirmed fact may appear in the normal list.
    # Use only a synthetic fact; never log its text or any response bodies.
    normal_text = "CI-only ordinary memory history for browser review"
    page.locator(".os-panel textarea").fill(normal_text)
    page.locator(".os-panel .el-radio").filter(has_text="普通").click()
    page.get_by_role("button", name="保存为待确认候选").click()
    normal_candidate = page.locator(".os-list-panel > article.os-memory-card").filter(
        has_text=normal_text).filter(has=page.get_by_role("button", name="确认事实"))
    normal_candidate.wait_for(state="visible", timeout=15000)
    normal_candidate.get_by_role("button", name="确认事实").click()
    page.locator(".el-message-box").get_by_role(
        "button", name="我已核对，确认").click()
    normal_candidate.wait_for(state="detached", timeout=15000)
    normal_section = page.locator('section[aria-label="普通记忆历史管理"]')
    if normal_history_requests or normal_section.locator("article.os-memory-card").count():
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_EAGERLY_VISIBLE")
    normal_section.get_by_role("button", name="主动查看历史").click()
    historical = normal_section.locator("article.os-memory-card").filter(
        has_text=normal_text)
    historical.wait_for(state="visible", timeout=15000)
    if len(normal_history_requests) != 1:
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_NOT_CLICK_ONLY")
    normal_section.get_by_role("button", name="收起并清除本页历史").click()
    if normal_section.locator("article.os-memory-card").count():
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_NOT_CLEARED_ON_CLOSE")
    page.locator(".el-segmented").get_by_text(
        "我的目标", exact=True).click()
    page.locator(".el-segmented").get_by_text(
        "个人记忆", exact=True).click()
    page.get_by_text("补充个人事实", exact=True).wait_for(
        state="visible", timeout=15000)
    if normal_section.locator("article.os-memory-card").count():
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_REOPENED_AFTER_TAB_SWITCH")
    if len(normal_history_requests) != 1:
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_REFETCHED_WITHOUT_OWNER_CLICK")
    # Explicit owner re-open is allowed; removal from owner history must work.
    normal_section.get_by_role("button", name="主动查看历史").click()
    historical = normal_section.locator("article.os-memory-card").filter(
        has_text=normal_text)
    historical.wait_for(state="visible", timeout=15000)
    if len(normal_history_requests) != 2:
        raise RuntimeError("PERSONAL_OS_NORMAL_HISTORY_EXPLICIT_REOPEN_NOT_FETCHED")
    historical.get_by_role("button", name="永久删除").click()
    page.locator(".el-message-box").get_by_role(
        "button", name="永久删除").click()
    historical.wait_for(state="detached", timeout=15000)
    print("CI_PERSONAL_OS_CHROMIUM_NORMAL_HISTORY_OWNER_CLICK_ERASE=PASS")

    # T-005: first-party model workflow with synthetic responses ONLY. The
    # model endpoints are intercepted; CI never calls a real provider.
    # This tests user-visible review, cancel, confirm, and no implicit reads.
    page.locator(".el-segmented").get_by_text("我的目标", exact=True).click()
    goal_card = page.locator(".os-goal-card").filter(
        has_text="CI-only first-party goal")
    goal_card.locator(".os-goal-select").click()
    page.get_by_text("AI 职业规划 · 单次授权").wait_for(
        state="visible", timeout=15000)

    model_calls = []
    task_writes = []
    task_post_response_classes = []
    def observe_task_write(req):
        path = urlsplit(req.url).path
        if req.method in ("POST", "PATCH", "DELETE") and path.endswith("/api/tasks"):
            task_writes.append(1)
    def observe_task_response(resp):
        if (resp.request.method == "POST"
                and urlsplit(resp.url).path.endswith("/api/tasks")):
            status = resp.status
            task_post_response_classes.append(
                "2XX" if 200 <= status < 300 else
                "4XX" if 400 <= status < 500 else
                "5XX" if 500 <= status < 600 else "OTHER")
    page.on("request", observe_task_write)
    page.on("response", observe_task_response)

    def mock_model(route):
        path = urlsplit(route.request.url).path
        model_calls.append(path.rsplit("/", 1)[-1])
        payload = route.request.post_data_json
        goal = path.split("/goals/", 1)[1].split("/", 1)[0]
        snapshot = {
            "goalId": int(goal), "title": "CI-only first-party goal",
            "status": "PLANNED", "successCriteria": None,
            "evidence": [{
                "reference": "goal:" + goal, "relation": "GOAL",
                "statement": "CI-only first-party goal",
                "evidenceClass": "USER_GOAL"
            }],
            "gaps": [{"code": "SKILL_REQUIREMENTS_UNRECORDED",
                      "explanation": "Unknown skills"}],
            "taskDrafts": [], "modelInvoked": False, "dataWritten": False,
            "limitation": "Synthetic preview only"
        }
        if path.endswith("/model/preview"):
            if payload != {"includePersonalFacts": False}:
                raise RuntimeError("PERSONAL_OS_MODEL_DEFAULT_SCOPE_NOT_OFF")
            data = {
                "previewId": "ci-preview-once", "goalId": int(goal),
                "provider": "ci-synthetic-provider", "model": "ci-synthetic-model",
                "snapshot": snapshot,
                "expiresAtMillis": int(time.time() * 1000) + 120000
            }
        elif path.endswith("/model/confirm"):
            if payload != {"previewId": "ci-preview-once"}:
                raise RuntimeError("PERSONAL_OS_MODEL_CONFIRM_WRONG_PREVIEW")
            data = {"modelToken": "ci-model-once"}
        elif path.endswith("/model/suggest"):
            if payload != {"modelToken": "ci-model-once"}:
                raise RuntimeError("PERSONAL_OS_MODEL_SUGGEST_WRONG_TOKEN")
            data = {
                "goalId": int(goal), "provider": "ci-synthetic-provider",
                "model": "ci-synthetic-model",
                "proposals": [{
                    "title": "CI-only evidence-reviewed action",
                    "rationale": "Synthetic test with one valid citation",
                    "evidenceRefs": ["goal:" + goal], "assumptions": ["Skills unknown"]
                }],
                "evidence": snapshot["evidence"], "gaps": snapshot["gaps"],
                "dataWritten": False, "limitation": "Synthetic advice; no task write"
            }
        else:
            raise RuntimeError("PERSONAL_OS_MODEL_UNEXPECTED_ROUTE")
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"code": "OK", "message": "success",
                                       "data": data}))

    page.route("**/ai/personal-os/goals/*/model/*", mock_model)
    if model_calls:
        raise RuntimeError("PERSONAL_OS_MODEL_CALLED_WITHOUT_OPT_IN")
    page.get_by_role("button", name="预览将共享的内容").click()
    page.locator(".os-model-json").wait_for(state="visible", timeout=15000)
    if model_calls != ["preview"]:
        raise RuntimeError("PERSONAL_OS_MODEL_CALLED_BEFORE_CONFIRM")
    if "CI-only first-party goal" not in page.locator(".os-model-json").inner_text():
        raise RuntimeError("PERSONAL_OS_MODEL_PREVIEW_NOT_INSPECTABLE")
    page.get_by_role("button", name="核对完成，确认仅本次发送").click()
    dialog = page.locator(".el-message-box")
    dialog.get_by_role("button", name="取消").click()
    if model_calls != ["preview"]:
        raise RuntimeError("PERSONAL_OS_MODEL_CANCEL_SENT_CONTEXT")

    page.get_by_role("button", name="核对完成，确认仅本次发送").click()
    dialog.get_by_role("button", name="确认仅本次发送").click()
    page.get_by_text("CI-only evidence-reviewed action", exact=True).wait_for(
        state="visible", timeout=15000)
    if model_calls != ["preview", "confirm", "suggest"]:
        raise RuntimeError("PERSONAL_OS_MODEL_REVIEW_CONSENT_SEQUENCE_INVALID")
    if task_writes:
        raise RuntimeError("PERSONAL_OS_MODEL_ADVICE_AUTO_WROTE_TASK")
    print("CI_T007_STAGE_MODEL_ADVICE_VISIBLE=PASS")

    # A model suggestion is untrusted review text, never an automatic task.
    # Opening and canceling the owner draft must not write anything.
    page.get_by_role("button", name="采纳为任务（先审核）").click()
    draft_dialog = page.locator(".el-dialog").filter(
        has=page.get_by_text("采纳 AI 建议为任务", exact=True))
    draft_dialog.wait_for(state="visible", timeout=15000)
    print("CI_T007_STAGE_TASK_REVIEW_OPENED=PASS")
    if task_writes:
        raise RuntimeError("PERSONAL_OS_TASK_DRAFT_OPEN_AUTO_WROTE")
    draft_dialog.get_by_role("button", name="取消", exact=True).click()
    draft_dialog.wait_for(state="hidden", timeout=15000)
    print("CI_T007_STAGE_TASK_REVIEW_CANCELED=PASS")
    if task_writes:
        raise RuntimeError("PERSONAL_OS_TASK_DRAFT_CANCEL_WROTE")

    # Only a distinct explicit save click may persist one synthetic task via
    # the regular first-party task API. We delete the CI-owned task afterward.
    created_task_id = None
    try:
        page.get_by_role("button", name="采纳为任务（先审核）").click()
        draft_dialog.wait_for(state="visible", timeout=15000)
        print("CI_T007_STAGE_TASK_REVIEW_REOPENED=PASS")
        if "CI-only evidence-reviewed action" not in draft_dialog.inner_text():
            raise RuntimeError("PERSONAL_OS_TASK_DRAFT_TITLE_NOT_REVIEWABLE")
        save_button = draft_dialog.get_by_role("button", name="确认创建任务")
        if not save_button.is_enabled():
            print("CI_T007_STAGE_TASK_SAVE_BUTTON_DISABLED=YES")
            raise RuntimeError("PERSONAL_OS_OWNER_TASK_SAVE_BUTTON_DISABLED")
        print("CI_T007_STAGE_TASK_SAVE_BUTTON_ENABLED=PASS")
        before_write_count = len(task_writes)
        try:
            with page.expect_response(lambda r:
                    urlsplit(r.url).path == "/api/tasks"
                    and r.request.method == "POST", timeout=20000) as saved_response:
                save_button.click()
                print("CI_T007_STAGE_TASK_SAVE_CLICK_RETURNED=PASS")
            response = saved_response.value
        except Exception:
            # Fixed, non-sensitive diagnostics only; never log task text,
            # request URL, response body, headers, tokens or browser state.
            print("CI_T007_STAGE_TASK_POST_REQUEST_OBSERVED="
                  + ("YES" if len(task_writes) > before_write_count else "NO"))
            print("CI_T007_STAGE_TASK_POST_RESPONSE_CLASS="
                  + (task_post_response_classes[-1]
                     if task_post_response_classes else "NOT_SEEN"))
            raise
        print("CI_T007_STAGE_TASK_SAVE_RESPONSE_SEEN=PASS")
        if response.status != 200:
            raise RuntimeError("PERSONAL_OS_OWNER_TASK_SAVE_FAILED")
        body = response.json()
        created_task_id = body.get("data", {}).get("id")
        if not isinstance(created_task_id, int) or created_task_id <= 0:
            raise RuntimeError("PERSONAL_OS_TASK_SAVE_ID_INVALID")
        if len(task_writes) != 1:
            raise RuntimeError("PERSONAL_OS_TASK_WRITE_NOT_EXACTLY_ONE")
        draft_dialog.wait_for(state="hidden", timeout=15000)
        persisted = page.evaluate("""async taskId => {
          const token = localStorage.getItem('matrix-prp-token');
          const response = await fetch('/api/tasks', {
            headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store',
            credentials: 'omit'
          });
          if (!response.ok) return false;
          const tasks = (await response.json()).data;
          return Array.isArray(tasks) && tasks.some(t =>
            t.id === taskId && t.title === 'CI-only evidence-reviewed action'
            && t.moduleCode === 'learning');
        }""", created_task_id)
        if not persisted:
            raise RuntimeError("PERSONAL_OS_OWNER_TASK_NOT_PERSISTED")
        print("CI_T007_STAGE_TASK_PERSISTED=PASS")
    finally:
        if created_task_id is not None:
            status = page.evaluate("""async taskId => {
              const token = localStorage.getItem('matrix-prp-token');
              const response = await fetch('/api/tasks/' + taskId, {
                method: 'DELETE', headers: {'Authorization': 'Bearer ' + token},
                cache: 'no-store', credentials: 'omit'
              });
              return response.status;
            }""", created_task_id)
            if status != 200:
                raise RuntimeError("PERSONAL_OS_CI_TASK_CLEANUP_FAILED")
    print("CI_PERSONAL_OS_T007_OWNER_REVIEWED_TASK_ADOPTION=PASS")
    page.locator(".el-segmented").get_by_text("个人记忆", exact=True).click()
    if page.locator(".os-model-results").count():
        raise RuntimeError("PERSONAL_OS_MODEL_ADVICE_PERSISTED_AFTER_TAB_CHANGE")
    print("CI_PERSONAL_OS_CHROMIUM_MODEL_REVIEW_SINGLE_USE_UI=PASS")

    # U10 partial mobile consent acceptance. Use the SAME first-party Vue
    # controls, on a phone-size Chromium viewport, with the intercepted model
    # still restricted to synthetic responses. This does not exercise a live
    # provider or the separately disabled chat-message extraction feature.
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator(".el-segmented").get_by_text("我的目标", exact=True).click()
    page.locator(".os-goal-card").filter(
        has_text="CI-only first-party goal").locator(".os-goal-select").click()
    page.get_by_text("AI 职业规划 · 单次授权").wait_for(
        state="visible", timeout=15000)
    if page.locator(".os-model-json").count():
        raise RuntimeError("PERSONAL_OS_MOBILE_PREVIEW_RESTORED_WITHOUT_APPROVAL")
    before_mobile_calls = len(model_calls)
    before_mobile_task_writes = len(task_writes)
    page.get_by_role("button", name="预览将共享的内容").click()
    page.locator(".os-model-json").wait_for(state="visible", timeout=15000)
    if len(model_calls) != before_mobile_calls + 1 or model_calls[-1] != "preview":
        raise RuntimeError("PERSONAL_OS_MOBILE_PREVIEW_SENT_TO_MODEL")
    reviewed = page.locator(".os-model-review")
    if ("ci-synthetic-provider / ci-synthetic-model" not in reviewed.inner_text()
            or "CI-only first-party goal" not in page.locator(".os-model-json").inner_text()):
        raise RuntimeError("PERSONAL_OS_MOBILE_PROVIDER_OR_SNAPSHOT_HIDDEN")
    panel = page.locator(".os-model-panel")
    bounds = panel.evaluate("""element => {
        const p = element.getBoundingClientRect();
        const review = element.querySelector('.os-model-review').getBoundingClientRect();
        return {
          viewport: window.innerWidth,
          panelLeft: p.left,
          panelRight: p.right,
          reviewRight: review.right,
          documentWidth: document.documentElement.scrollWidth
        };
    }""")
    if (bounds["viewport"] != 390 or bounds["panelLeft"] < -2
            or bounds["panelRight"] > 392 or bounds["reviewRight"] > 392
            or bounds["documentWidth"] > 392):
        raise RuntimeError("PERSONAL_OS_MOBILE_CONSENT_HORIZONTAL_OVERFLOW")
    page.get_by_role("button", name="核对完成，确认仅本次发送").click()
    page.locator(".el-message-box").get_by_role("button", name="取消").click()
    if (len(model_calls) != before_mobile_calls + 1
            or len(task_writes) != before_mobile_task_writes):
        raise RuntimeError("PERSONAL_OS_MOBILE_CANCEL_INVOKED_MODEL_OR_TASK")
    page.locator(".el-segmented").get_by_text("个人记忆", exact=True).click()
    if page.locator(".os-model-review").count():
        raise RuntimeError("PERSONAL_OS_MOBILE_REVIEW_PERSISTED_AFTER_TAB_EXIT")
    page.set_viewport_size({"width": 1280, "height": 800})
    print("CI_PERSONAL_OS_T007_MOBILE_MODEL_CONSENT_CANCEL=PASS")

    # T-007: separate HTTP-level owner acceptance against the same temporary
    # PRP session and real MySQL. No model, real account or extra OAuth scopes.
    from ci_personal_os_memory_acceptance import run as run_memory_acceptance
    run_memory_acceptance(page)

    print("CI_PERSONAL_OS_CHROMIUM_FIRST_PARTY_GOAL_MEMORY_PRIVACY=PASS")
