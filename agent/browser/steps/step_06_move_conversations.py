"""
step_06_move_conversations.py — Moves emails to an analyst folder via right-click → Move.

Receives in ctx.shared:
    moves: list[dict]  each item:
        conversation_id  str   Outlook thread id  (data-convid attribute)
        source_folder    str   folder to navigate to first
        target_folder    str   exact folder name to move the email to

Flow per conversation:
1. Navigate to source_folder if not already there
2. Find the email row in the virtual-scrolled list by data-convid
3. Right-click → "Mover" / "Move" in the context menu
4. Type the exact target_folder name in the search input
5. Click the first matching suggestion
6. Verify move succeeded (row disappears from the list)
"""

from __future__ import annotations

from collections import defaultdict

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from agent.browser.base_step import BaseStep, StepContext
from agent.browser.steps.step_02_navigate_folder import NavigateFolderStep
from api.shared.logger import get_logger

logger = get_logger("agent")

_SCROLL_LIST_TO_TOP_JS = """() => {
    const v = document.querySelector('[data-virtuoso-scroller="true"]');
    if (v) { v.scrollTop = 0; return 'virtuoso'; }
    const lb = document.querySelector('[role="listbox"]');
    if (lb) { lb.scrollTop = 0; return 'listbox'; }
    return null;
}"""

_SCROLL_LIST_DOWN_JS = """() => {
    const v = document.querySelector('[data-virtuoso-scroller="true"]');
    if (v) {
        const before = v.scrollTop;
        v.scrollTop += v.clientHeight * 0.5;
        return { scrolled: v.scrollTop > before, scrollTop: v.scrollTop };
    }
    return { scrolled: false, scrollTop: 0 };
}"""


class MoveConversationsStep(BaseStep):
    name = "move_conversations"
    is_critical = False

    async def execute(self, ctx: StepContext) -> StepContext:
        page = ctx.page
        moves: list[dict] = ctx.shared.get("moves", [])

        if not moves:
            logger.info("No conversations to move", extra={"step": self.name})
            ctx.shared["moves_done"] = 0
            ctx.shared["moves_failed"] = 0
            return ctx

        # Group by source_folder so we only navigate once per folder
        by_folder: dict[str, list[dict]] = defaultdict(list)
        for m in moves:
            by_folder[m["source_folder"]].append(m)

        done = 0
        failed = 0
        _nav = NavigateFolderStep()

        for source_folder, folder_moves in by_folder.items():
            logger.info(
                "Navigating to source folder '%s' for %d move(s)",
                source_folder, len(folder_moves),
                extra={"step": self.name},
            )

            # Navigate to the source folder
            nav_ctx = StepContext(page=page, shared={"folder": source_folder})
            try:
                await _nav.execute(nav_ctx)
            except Exception as e:
                logger.error(
                    "Could not navigate to folder '%s': %s — skipping %d move(s)",
                    source_folder, e, len(folder_moves),
                    extra={"step": self.name},
                )
                failed += len(folder_moves)
                continue

            await page.evaluate(_SCROLL_LIST_TO_TOP_JS)
            await page.wait_for_timeout(1500)

            for i, move in enumerate(folder_moves):
                conv_id = move["conversation_id"]
                target = move["target_folder"]

                try:
                    moved = await self._move_one(page, conv_id, target, i + 1, len(folder_moves))
                    if moved:
                        done += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(
                        "Unexpected error moving conv %s to '%s': %s",
                        conv_id[:20], target, e,
                        extra={"step": self.name},
                    )
                    failed += 1

        logger.info(
            "Move complete: done=%d failed=%d",
            done, failed,
            extra={"step": self.name},
        )
        ctx.shared["moves_done"] = done
        ctx.shared["moves_failed"] = failed
        return ctx

    # ------------------------------------------------------------------

    async def _find_row(self, page: Page, conv_id: str, max_scrolls: int = 30):
        selector = f'[role="option"][data-convid="{conv_id}"]'
        row = page.locator(selector)
        if await row.count() > 0:
            return row.first

        for _ in range(max_scrolls):
            result = await page.evaluate(_SCROLL_LIST_DOWN_JS)
            if not result.get("scrolled"):
                break
            await page.wait_for_timeout(600)
            row = page.locator(selector)
            if await row.count() > 0:
                return row.first

        return None

    async def _move_one(
        self,
        page: Page,
        conv_id: str,
        target_folder: str,
        idx: int,
        total: int,
    ) -> bool:
        logger.info(
            "[%d/%d] Moving conv %s to '%s'",
            idx, total, conv_id[:20], target_folder,
            extra={"step": self.name},
        )

        row = await self._find_row(page, conv_id)
        if row is None:
            logger.warning(
                "[%d/%d] Row not found for conv %s — skipping",
                idx, total, conv_id[:20],
                extra={"step": self.name},
            )
            return False

        await row.scroll_into_view_if_needed()
        await page.wait_for_timeout(400)

        # Right-click to open context menu
        await row.click(button="right")
        await page.wait_for_timeout(800)

        # Click "Mover" / "Move" in the context menu
        move_selectors = [
            '[role="menuitem"]:has-text("Mover")',
            '[role="menuitem"]:has-text("Move")',
            '[id*="move" i]',
            'button:has-text("Mover")',
            'button:has-text("Move")',
        ]
        clicked_move = False
        for sel in move_selectors:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=3000)
                await loc.click()
                clicked_move = True
                break
            except PlaywrightTimeout:
                continue

        if not clicked_move:
            logger.warning(
                "[%d/%d] 'Move' option not found in context menu for conv %s",
                idx, total, conv_id[:20],
                extra={"step": self.name},
            )
            # Dismiss context menu
            await page.keyboard.press("Escape")
            return False

        await page.wait_for_timeout(800)

        # Type folder name in the search input that appears after clicking Move
        input_selectors = [
            'input[placeholder*="carpeta" i]',
            'input[placeholder*="folder" i]',
            'input[placeholder*="buscar" i]',
            'input[placeholder*="search" i]',
            '[role="dialog"] input',
            '[role="listbox"] ~ input',
            '.ms-SearchBox-field',
            'input[type="text"]',
        ]
        found_input = False
        for sel in input_selectors:
            try:
                inp = page.locator(sel).first
                await inp.wait_for(state="visible", timeout=3000)
                await inp.fill(target_folder)
                found_input = True
                break
            except PlaywrightTimeout:
                continue

        if not found_input:
            logger.warning(
                "[%d/%d] Folder search input not found for conv %s",
                idx, total, conv_id[:20],
                extra={"step": self.name},
            )
            await page.keyboard.press("Escape")
            return False

        await page.wait_for_timeout(1000)

        # Click the first matching folder suggestion
        suggestion_selectors = [
            f'[role="option"]:has-text("{target_folder}")',
            f'[role="listitem"]:has-text("{target_folder}")',
            f'[role="treeitem"]:has-text("{target_folder}")',
            f'li:has-text("{target_folder}")',
            f'span:text-is("{target_folder}")',
        ]
        clicked_folder = False
        for sel in suggestion_selectors:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=4000)
                await loc.click()
                clicked_folder = True
                break
            except PlaywrightTimeout:
                continue

        if not clicked_folder:
            logger.warning(
                "[%d/%d] Folder '%s' not found in suggestions for conv %s",
                idx, total, target_folder, conv_id[:20],
                extra={"step": self.name},
            )
            await page.keyboard.press("Escape")
            return False

        # Wait briefly and verify the row is gone (email was moved)
        await page.wait_for_timeout(1500)
        row_still_present = await page.locator(
            f'[role="option"][data-convid="{conv_id}"]'
        ).count()

        if row_still_present == 0:
            logger.info(
                "[%d/%d] Moved conv %s to '%s' successfully",
                idx, total, conv_id[:20], target_folder,
                extra={"step": self.name},
            )
            return True
        else:
            logger.warning(
                "[%d/%d] Conv %s still present after move attempt to '%s'",
                idx, total, conv_id[:20], target_folder,
                extra={"step": self.name},
            )
            return False
