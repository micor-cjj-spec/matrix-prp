#!/usr/bin/env python3
"""Synthetic Personal OS browser review on the existing disposable PRP Chromium stack.

Only enabled by the stacked T-004 CI workflow. No real user data, passwords,
URLs with OAuth codes, or personal memory contents are logged.
"""
import os
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

    print("CI_PERSONAL_OS_CHROMIUM_FIRST_PARTY_GOAL_MEMORY_PRIVACY=PASS")
