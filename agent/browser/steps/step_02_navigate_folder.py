from __future__ import annotations

import re

from agent.browser.base_step import BaseStep, StepContext
from shared.logger import get_logger

logger = get_logger("agent")

OUTLOOK_MAIL_URL = "https://outlook.office.com/mail/"


class NavigateFolderStep(BaseStep):
    name = "navigate_folder"
    is_critical = True

    async def execute(self, ctx: StepContext) -> StepContext:
        page = ctx.page
        folder = ctx.shared["folder"]

        logger.info("Navigating to folder '%s'", folder, extra={"step": self.name})

        # Always reload to a clean state — prevents stale DOM from previous scrape
        await page.goto(OUTLOOK_MAIL_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Wait for the folder pane to be ready
        await page.wait_for_selector('[role="tree"], [role="navigation"]', timeout=20000)

        # Try multiple selector strategies for the folder name
        selectors = [
            f'[role="treeitem"]:has-text("{folder}")',
            f'text="{folder}"',
            f'span:text-is("{folder}")',
        ]

        clicked = False
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                await loc.wait_for(state="visible", timeout=5000)
                await loc.click()
                clicked = True
                logger.info("Folder clicked with selector: %s", selector, extra={"step": self.name})
                break
            except Exception:
                continue

        if not clicked:
            raise TimeoutError(f"Could not find folder '{folder}' in sidebar")

        # Wait for folder content to load
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        # Extract unread count from the folder treeitem badge
        expected_unread = await self._extract_folder_unread_count(page, folder)
        ctx.shared["expected_unread"] = expected_unread
        logger.info(
            "Folder '%s' opened (expected unread: %s)",
            folder, expected_unread or "unknown",
            extra={"step": self.name},
        )
        return ctx

    async def _extract_folder_unread_count(self, page, folder: str) -> int | None:
        """Extract the unread count from the folder treeitem's title attribute.

        The title looks like: 'Bandeja de entrada : Elementos 314 (92 no leídos)'
        We extract the number inside parentheses before 'no leídos/unread'.
        """
        try:
            treeitem = page.locator(f'[role="treeitem"]:has-text("{folder}")').first
            title = await treeitem.get_attribute("title") or ""

            # Try "title" attr first: "Folder : Elementos 314 (92 no leídos)"
            match = re.search(r"\((\d+)\s+no\s+le", title, re.IGNORECASE)
            if match:
                return int(match.group(1))

            # English variant: "(92 unread)"
            match = re.search(r"\((\d+)\s+unread", title, re.IGNORECASE)
            if match:
                return int(match.group(1))

            # Fallback: badge span with the count number
            badge = treeitem.locator("span.Mt2TB, span.BptzE").first
            badge_text = (await badge.inner_text(timeout=2000)).strip()
            if badge_text.isdigit():
                return int(badge_text)

        except Exception as e:
            logger.debug("Could not extract unread count: %s", e, extra={"step": self.name})
        return None
