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
    page.on("request", lambda req: private_requests.append(1)
            if (urlsplit(req.url).path == "/api/memory/private") else None)

    # Start with real authenticated first-party Vue UI and fresh isolated MySQL.
    page.goto(origin + "/prp/personal-os", wait_until="domcontentloaded",
              timeout=30000)
    page.locator(".os-hero h1").wait_for(state="visible", timeout=20000)
    if page.locator(".os-alert").is_visible():
        raise RuntimeError("PERSONAL_OS_BACKEND_NOT_AVAILABLE")
    if private_requests:
        raise RuntimeError("PERSONAL_OS_PRIVATE_MEMORY_AUTO_FETCH")

    # The only way to create a goal here is an explicit first-party form submit.
    page.get_by_placeholder("例如：完成一个阶段性学习计划").fill(
        "CI-only first-party goal")
    page.get_by_role("button", name="创建目标").click()
    page.locator(".os-goal-card").filter(
        has_text="CI-only first-party goal").wait_for(
            state="visible", timeout=15000)

    page.locator(".el-segmented").get_by_text(
        "个人记忆", exact=True).click()
    page.locator(".os-panel textarea").fill(
        "CI-only private fact for browser approval")
    page.get_by_role("button", name="保存为待确认候选").click()
    pending = page.locator(".os-list-panel article.os-memory-card").filter(
        has_text="CI-only private fact for browser approval")
    pending.wait_for(state="visible", timeout=15000)
    if private_requests:
        raise RuntimeError("PERSONAL_OS_PRIVATE_MEMORY_FETCH_BEFORE_CLICK")

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

    print("CI_PERSONAL_OS_CHROMIUM_FIRST_PARTY_GOAL_MEMORY_PRIVACY=PASS")
