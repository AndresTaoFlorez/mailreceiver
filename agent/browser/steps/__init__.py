from __future__ import annotations

from agent.browser.base_step import BaseStep
from agent.browser.steps.step_01_login import LoginStep
from agent.browser.steps.step_02_navigate_folder import NavigateFolderStep
from agent.browser.steps.step_03_filter_unread import FilterUnreadStep
from agent.browser.steps.step_04_scrape_conversations import ScrapeconversationsStep


def build_login_pipeline() -> list[BaseStep]:
    return [LoginStep()]


def build_scrape_pipeline() -> list[BaseStep]:
    return [
        NavigateFolderStep(),
        FilterUnreadStep(),
        ScrapeconversationsStep(),
    ]
