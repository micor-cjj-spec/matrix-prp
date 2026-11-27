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
    created_link_id = None
    goal_link_id = None
    try:
        page.get_by_role("button", name="采纳为任务（先审核）").click()
        draft_dialog.wait_for(state="visible", timeout=15000)
        print("CI_T007_STAGE_TASK_REVIEW_REOPENED=PASS")
        # Element Plus el-input stores its editable title in input.value,
        # which is deliberately absent from the dialog's inner_text().
        # Inspect the actual owner-review field instead of its text nodes.
        title_input = draft_dialog.locator('input[aria-label="任务标题"]')
        if title_input.input_value() != "CI-only evidence-reviewed action":
            raise RuntimeError("PERSONAL_OS_TASK_DRAFT_TITLE_NOT_REVIEWABLE")
        print("CI_T007_STAGE_TASK_TITLE_INPUT_REVIEWABLE=PASS")
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

        # The task exists; until a SECOND explicit owner click there must be
        # no TASK -> ADVANCES -> GOAL relationship. Query real isolated MySQL
        # through the authenticated first-party API, not Vue component state.
        goal_link_id = page.evaluate("""async () => {
          const token = localStorage.getItem('matrix-prp-token');
          const response = await fetch('/api/goals', {
            headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store'
          });
          if (!response.ok) return null;
          const goals = (await response.json()).data;
          const goal = goals.find(g => g.title === 'CI-only first-party goal');
          return goal ? goal.id : null;
        }""")
        if not isinstance(goal_link_id, int) or goal_link_id <= 0:
            raise RuntimeError("PERSONAL_OS_GOAL_FOR_TASK_LINK_MISSING")

        def read_task_links():
            return page.evaluate("""async ({goalId, taskId}) => {
              const token = localStorage.getItem('matrix-prp-token');
              const response = await fetch('/api/goals/' + goalId + '/context', {
                headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store'
              });
              if (!response.ok) return null;
              const links = (await response.json()).data;
              return links.filter(x => x.predicate === 'ADVANCES'
                && x.subjectType === 'TASK' && x.subjectRef === String(taskId)
                && x.objectType === 'GOAL' && x.objectRef === String(goalId));
            }""", {"goalId": goal_link_id, "taskId": created_task_id})

        if read_task_links() != []:
            raise RuntimeError("PERSONAL_OS_TASK_AUTO_LINKED_WITHOUT_APPROVAL")
        link_requests = []
        link_payloads = []
        confirmation_requests = []
        def observe_owner_link(req):
            path = urlsplit(req.url).path
            if req.method == "POST" and path == "/api/memory/candidates":
                link_requests.append(1)
                # Only synthetic test-generated payloads exist in this CI.
                # Keep the retry key in process memory, never print contents.
                link_payloads.append(req.post_data_json)
            if (req.method == "POST" and path.startswith("/api/memory/")
                    and path.endswith("/confirm")):
                confirmation_requests.append(1)
        page.on("request", observe_owner_link)
        page.get_by_role("button", name="确认关联到此目标").wait_for(
            state="visible", timeout=15000)
        if link_requests or confirmation_requests:
            raise RuntimeError("PERSONAL_OS_TASK_LINK_WROTE_BEFORE_OWNER_CLICK")
        with page.expect_response(
            lambda resp: resp.request.method == "POST"
            and urlsplit(resp.url).path.startswith("/api/memory/")
            and urlsplit(resp.url).path.endswith("/confirm"),
            timeout=20000
        ) as link_confirmed:
            page.get_by_role("button", name="确认关联到此目标").click()
        confirmed = link_confirmed.value
        if confirmed.status != 200:
            raise RuntimeError("PERSONAL_OS_TASK_LINK_CONFIRM_NOT_SUCCESS")
        fact = confirmed.json().get("data", {})
        created_link_id = fact.get("id")
        if (not isinstance(created_link_id, int) or created_link_id <= 0
                or fact.get("predicate") != "ADVANCES"
                or fact.get("subjectType") != "TASK"
                or fact.get("subjectRef") != str(created_task_id)
                or fact.get("objectType") != "GOAL"
                or fact.get("objectRef") != str(goal_link_id)
                or fact.get("status") != "CONFIRMED"):
            raise RuntimeError("PERSONAL_OS_TASK_LINK_INCORRECT_RELATION")
        if len(link_requests) != 1 or len(confirmation_requests) != 1:
            raise RuntimeError("PERSONAL_OS_TASK_LINK_NOT_EXACTLY_ONE_REVIEW")
        page.locator(".os-context .os-evidence span").filter(
            has_text="任务 #" + str(created_task_id)).wait_for(
                state="visible", timeout=15000)
        links = read_task_links()
        if not isinstance(links, list) or len(links) != 1:
            raise RuntimeError("PERSONAL_OS_TASK_LINK_NOT_READABLE_AFTER_CONFIRM")
        if len(link_payloads) != 1 or not isinstance(link_payloads[0], dict):
            raise RuntimeError("PERSONAL_OS_TASK_LINK_REPLAY_PAYLOAD_MISSING")
        # Simulate replay after a lost HTTP response. The same server-side
        # request key must return the same confirmed assertion ID, not insert
        # a second relationship. This replay does not call the task API.
        replayed_link_id = page.evaluate("""async payload => {
          const token = localStorage.getItem('matrix-prp-token');
          const response = await fetch('/api/memory/candidates', {
            method: 'POST', headers: {
              'Authorization': 'Bearer ' + token,
              'Content-Type': 'application/json'
            }, body: JSON.stringify(payload), cache: 'no-store'
          });
          if (response.status !== 200) return null;
          return (await response.json()).data?.id ?? null;
        }""", link_payloads[0])
        if replayed_link_id != created_link_id or len(read_task_links()) != 1:
            raise RuntimeError("PERSONAL_OS_TASK_LINK_REPLAY_CREATED_DUPLICATE")
        print("CI_PERSONAL_OS_T007_LINK_REPLAY_IDEMPOTENT=PASS")
        print("CI_PERSONAL_OS_T007_OWNER_CONFIRMED_GOAL_TASK_LINK=PASS")
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
            # Revoking a referenced task must make the confirmed association
            # disappear from the goal's default context, not leak a stale ID.
            if created_link_id is not None and goal_link_id is not None:
                stale = page.evaluate("""async ({goalId, taskId}) => {
                  const token = localStorage.getItem('matrix-prp-token');
                  const response = await fetch('/api/goals/' + goalId + '/context', {
                    headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store'
                  });
                  if (!response.ok) return null;
                  const links = (await response.json()).data;
                  return links.filter(x => x.predicate === 'ADVANCES'
                    && x.subjectType === 'TASK' && x.subjectRef === String(taskId));
                }""", {"goalId": goal_link_id, "taskId": created_task_id})
                if stale != []:
                    raise RuntimeError("PERSONAL_OS_REVOKED_TASK_STILL_IN_GOAL_CONTEXT")
                erased = page.evaluate("""async memoryId => {
                  const token = localStorage.getItem('matrix-prp-token');
                  const response = await fetch('/api/memory/' + memoryId, {
                    method: 'DELETE', headers: {'Authorization': 'Bearer ' + token},
                    cache: 'no-store'
                  });
                  return response.status;
                }""", created_link_id)
                if erased != 200:
                    raise RuntimeError("PERSONAL_OS_CI_TASK_LINK_ERASURE_FAILED")
                print("CI_PERSONAL_OS_T007_REVOKED_TASK_LINK_EXCLUDED=PASS")
    print("CI_PERSONAL_OS_T007_OWNER_REVIEWED_TASK_ADOPTION=PASS")

    # An existing task must also be linkable after leaving and reopening
    # the Personal OS goal page. Creating the disposable task here is fixture
    # setup, not a model action or a production task write.
    manual_task_id = None
    manual_link_id = None
    try:
        manual_task_id = page.evaluate("""async () => {
          const token = localStorage.getItem('matrix-prp-token');
          const response = await fetch('/api/tasks', {
            method: 'POST', headers: {
              'Authorization': 'Bearer ' + token,
              'Content-Type': 'application/json'
            }, body: JSON.stringify({
              moduleCode: 'learning', title: 'CI-only existing task',
              description: 'CI fixture only', priority: 'medium', dueDate: null
            }), cache: 'no-store'
          });
          if (response.status !== 200) return null;
          return (await response.json()).data?.id ?? null;
        }""")
        if not isinstance(manual_task_id, int) or manual_task_id <= 0:
            raise RuntimeError("PERSONAL_OS_MANUAL_TASK_FIXTURE_NOT_CREATED")
        # Reenter the goal after discarding in-memory advice and draft state.
        page.locator(".el-segmented").get_by_text("个人记忆", exact=True).click()
        page.locator(".el-segmented").get_by_text("我的目标", exact=True).click()
        page.locator(".os-goal-card").filter(
            has_text="CI-only first-party goal").locator(".os-goal-select").click()
        if page.get_by_role("button", name="确认关联到此目标").count():
            raise RuntimeError("PERSONAL_OS_MANUAL_LINK_CREATED_WITHOUT_OWNER_SELECTION")

        def choose_existing_task():
            page.get_by_role("button", name="关联已有任务（先选择）").click()
            dialog = page.locator(".el-dialog").filter(
                has=page.get_by_text("选择已有任务关联目标", exact=True))
            dialog.wait_for(state="visible", timeout=15000)
            dialog.locator(".el-select").click()
            page.get_by_text(
                "CI-only existing task (#" + str(manual_task_id) + ")",
                exact=True).click()
            dialog.get_by_role("button", name="审核关联").click()
            page.get_by_role("button", name="确认关联到此目标").wait_for(
                state="visible", timeout=15000)

        before_link_requests = len(link_requests)
        before_confirms = len(confirmation_requests)
        choose_existing_task()
        # Staging the selection must not issue the relation POST.
        if (len(link_requests) != before_link_requests
                or len(confirmation_requests) != before_confirms):
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_SELECTED_WROTE_LINK")
        page.get_by_role("button", name="暂不关联").click()
        if page.get_by_role("button", name="确认关联到此目标").count():
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_CANCEL_STILL_PENDING")
        if (len(link_requests) != before_link_requests
                or len(confirmation_requests) != before_confirms):
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_CANCEL_WROTE_LINK")
        print("CI_PERSONAL_OS_T007_EXISTING_TASK_CANCEL_NO_WRITE=PASS")

        choose_existing_task()
        with page.expect_response(
            lambda resp: resp.request.method == "POST"
            and urlsplit(resp.url).path.startswith("/api/memory/")
            and urlsplit(resp.url).path.endswith("/confirm"),
            timeout=20000
        ) as linked:
            page.get_by_role("button", name="确认关联到此目标").click()
        response = linked.value
        if response.status != 200:
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_LINK_CONFIRM_FAILED")
        fact = response.json().get("data", {})
        manual_link_id = fact.get("id")
        if (not isinstance(manual_link_id, int) or manual_link_id <= 0
                or fact.get("subjectRef") != str(manual_task_id)
                or fact.get("objectRef") != str(goal_link_id)
                or fact.get("predicate") != "ADVANCES"
                or fact.get("status") != "CONFIRMED"):
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_LINK_INCORRECT")
        page.locator(".os-context .os-evidence span").filter(
            has_text="任务 #" + str(manual_task_id)).wait_for(
                state="visible", timeout=15000)
        if (len(link_requests) != before_link_requests + 1
                or len(confirmation_requests) != before_confirms + 1):
            raise RuntimeError("PERSONAL_OS_EXISTING_TASK_LINK_NOT_ONCE")
        print("CI_PERSONAL_OS_T007_EXISTING_TASK_REOPENED_AND_LINKED=PASS")
    finally:
        if manual_task_id is not None:
            removed = page.evaluate("""async taskId => {
              const token = localStorage.getItem('matrix-prp-token');
              const response = await fetch('/api/tasks/' + taskId, {
                method: 'DELETE',
                headers: {'Authorization': 'Bearer ' + token},
                cache: 'no-store'
              });
              return response.status;
            }""", manual_task_id)
            if removed != 200:
                raise RuntimeError("PERSONAL_OS_MANUAL_TASK_FIXTURE_DELETE_FAILED")
        if manual_link_id is not None:
            erased = page.evaluate("""async memoryId => {
              const token = localStorage.getItem('matrix-prp-token');
              const response = await fetch('/api/memory/' + memoryId, {
                method: 'DELETE',
                headers: {'Authorization': 'Bearer ' + token},
                cache: 'no-store'
              });
              return response.status;
            }""", manual_link_id)
            if erased != 200:
                raise RuntimeError("PERSONAL_OS_MANUAL_LINK_FIXTURE_ERASE_FAILED")

    # End-to-end review closure: owner-created review is linked to the goal
    # only after an explicit first-party selection and second confirmation.
    # This uses the existing PRP review endpoint and a synthetic-only record.
    review_id = None
    review_link_id = None
    try:
        review_id = page.evaluate("""async () => {
          const token = localStorage.getItem('matrix-prp-token');
          const response = await fetch('/api/reviews', {
            method: 'POST', headers: {
              'Authorization': 'Bearer ' + token,
              'Content-Type': 'application/json'
            }, body: JSON.stringify({
              reviewType: 'weekly', moduleCode: 'life',
              title: 'CI-only existing goal review',
              summary: 'Synthetic progress only', highlights: '',
              problems: '', nextActions: 'Synthetic follow-up',
              periodStart: '2026-11-01', periodEnd: '2026-11-08'
            }), cache: 'no-store'
          });
          if (response.status != 200) return null;
          return (await response.json()).data?.id ?? null;
        }""")
        if not isinstance(review_id, int) or review_id <= 0:
            raise RuntimeError("PERSONAL_OS_REVIEW_FIXTURE_NOT_CREATED")
        before_link_requests = len(link_requests)
        before_confirms = len(confirmation_requests)
        page.get_by_role("button", name="关联已有复盘（先选择）").click()
        review_dialog = page.locator(".el-dialog").filter(
            has=page.get_by_text("选择已有复盘关联目标", exact=True))
        review_dialog.wait_for(state="visible", timeout=15000)
        review_dialog.locator(".el-select").click()
        page.get_by_text(
            "CI-only existing goal review (#" + str(review_id) + ")",
            exact=True).click()
        review_dialog.get_by_role("button", name="审核复盘关联").click()
        page.get_by_role("button", name="确认复盘关联到此目标").wait_for(
            state="visible", timeout=15000)
        if (len(link_requests) != before_link_requests
                or len(confirmation_requests) != before_confirms):
            raise RuntimeError("PERSONAL_OS_REVIEW_SELECTION_AUTO_WROTE")
        page.get_by_role("button", name="暂不关联复盘").click()
        if (len(link_requests) != before_link_requests
                or len(confirmation_requests) != before_confirms):
            raise RuntimeError("PERSONAL_OS_REVIEW_CANCEL_WROTE")
        print("CI_PERSONAL_OS_T007_REVIEW_SELECTION_CANCEL_NO_WRITE=PASS")

        page.get_by_role("button", name="关联已有复盘（先选择）").click()
        review_dialog.wait_for(state="visible", timeout=15000)
        review_dialog.locator(".el-select").click()
        page.get_by_text(
            "CI-only existing goal review (#" + str(review_id) + ")",
            exact=True).click()
        review_dialog.get_by_role("button", name="审核复盘关联").click()
        with page.expect_response(
            lambda resp: resp.request.method == "POST"
            and urlsplit(resp.url).path.startswith("/api/memory/")
            and urlsplit(resp.url).path.endswith("/confirm"),
            timeout=20000
        ) as reviewed:
            page.get_by_role("button", name="确认复盘关联到此目标").click()
        response = reviewed.value
        fact = response.json().get("data", {}) if response.status == 200 else {}
        review_link_id = fact.get("id")
        if (not isinstance(review_link_id, int) or review_link_id <= 0
                or fact.get("predicate") != "EVALUATES"
                or fact.get("subjectType") != "REVIEW"
                or fact.get("subjectRef") != str(review_id)
                or fact.get("objectRef") != str(goal_link_id)
                or fact.get("status") != "CONFIRMED"):
            raise RuntimeError("PERSONAL_OS_REVIEW_GOAL_RELATION_INVALID")
        if (len(link_requests) != before_link_requests + 1
                or len(confirmation_requests) != before_confirms + 1):
            raise RuntimeError("PERSONAL_OS_REVIEW_LINK_WRITE_NOT_EXPLICIT_ONCE")
        page.locator(".os-context .os-evidence span").filter(
            has_text="复盘 #" + str(review_id)).wait_for(
                state="visible", timeout=15000)
        print("CI_PERSONAL_OS_T007_EXISTING_REVIEW_GOAL_LINK=PASS")
    finally:
        if review_id is not None:
            removed = page.evaluate("""async id => {
              const token = localStorage.getItem('matrix-prp-token');
              const response = await fetch('/api/reviews/' + id, {
                method: 'DELETE', headers: {'Authorization': 'Bearer ' + token},
                cache: 'no-store'
              });
              return response.status;
            }""", review_id)
            if removed != 200:
                raise RuntimeError("PERSONAL_OS_REVIEW_FIXTURE_DELETE_FAILED")
            if review_link_id is not None:
                stale = page.evaluate("""async ({goalId, reviewId}) => {
                  const token = localStorage.getItem('matrix-prp-token');
                  const response = await fetch('/api/goals/' + goalId + '/context', {
                    headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store'
                  });
                  if (!response.ok) return null;
                  return (await response.json()).data.filter(x =>
                    x.predicate === 'EVALUATES' && x.subjectType === 'REVIEW'
                    && x.subjectRef === String(reviewId));
                }""", {"goalId": goal_link_id, "reviewId": review_id})
                if stale != []:
                    raise RuntimeError("PERSONAL_OS_DELETED_REVIEW_STILL_IN_CONTEXT")
                erased = page.evaluate("""async id => {
                  const token = localStorage.getItem('matrix-prp-token');
                  const response = await fetch('/api/memory/' + id, {
                    method: 'DELETE',
                    headers: {'Authorization': 'Bearer ' + token},
                    cache: 'no-store'
                  });
                  return response.status;
                }""", review_link_id)
                if erased != 200:
                    raise RuntimeError("PERSONAL_OS_REVIEW_RELATION_CLEANUP_FAILED")
                print("CI_PERSONAL_OS_T007_REVOKED_REVIEW_LINK_EXCLUDED=PASS")

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
