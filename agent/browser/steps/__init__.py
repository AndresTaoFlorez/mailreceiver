from __future__ import annotations

from agent.browser.base_step import BaseStep
from agent.browser.steps.step_01_login import LoginStep
from agent.browser.steps.step_02_navigate_folder import NavigateFolderStep
from agent.browser.steps.step_03_filter_unread import FilterUnreadStep
from agent.browser.steps.step_04_scrape_conversations import ScrapeconversationsStep
from agent.browser.steps.step_05_extract_body import ExtractBodyStep
from agent.browser.steps.step_06_move_conversations import MoveConversationsStep


def build_login_pipeline() -> list[BaseStep]:
    return [LoginStep()]


def build_scrape_pipeline() -> list[BaseStep]:
    return [
        NavigateFolderStep(),
        FilterUnreadStep(),
        ScrapeconversationsStep(),
        ExtractBodyStep(),
    ]


def build_move_pipeline() -> list[BaseStep]:
    """Pipeline that moves already-assigned emails to their analyst's folder."""
    return [MoveConversationsStep()]
