from __future__ import annotations

import asyncio

from agent.browser.base_step import BaseStep, StepContext
from agent.browser.scraping_config import load as load_scraping_config
from agent.browser.utils.email_parser import parse_email_card, get_setsize
from api.shared.logger import get_logger

logger = get_logger("agent")

SCRAPE_TIMEOUT_S = 300

_SCROLL_JS = """() => {
    const scroller = document.querySelector('[data-virtuoso-scroller="true"]');
    if (!scroller) return null;
    scroller.scrollTop += scroller.clientHeight * 0.8;
    return {
        scrollTop: Math.round(scroller.scrollTop),
        scrollHeight: scroller.scrollHeight,
        clientHeight: scroller.clientHeight
    };
}"""


class ScrapeconversationsStep(BaseStep):
    name = "scrape_conversations"
    is_critical = True

    async def execute(self, ctx: StepContext) -> StepContext:
        ctx.shared.setdefault("conversations", [])
        try:
            return await asyncio.wait_for(
                self._do_scrape(ctx),
                timeout=SCRAPE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Scrape timed out after %ds, returning partial results",
                SCRAPE_TIMEOUT_S, extra={"step": self.name},
            )
            return self._finish(ctx)

    async def _do_scrape(self, ctx: StepContext) -> StepContext:
        page = ctx.page
        cfg = load_scraping_config()

        max_iterations = cfg["max_scroll_iterations"]
        no_new_limit = cfg["no_new_rows_limit"]
        scroll_wait = cfg["scroll_wait_ms"]
        max_conversations = cfg["max_conversations"]
        listbox_timeout = cfg["listbox_timeout_ms"]
        row_wait = cfg["row_render_wait_ms"]
        expected_unread = ctx.shared.get("expected_unread")

        logger.info(
            "Starting email scrape (expected=%s, max_conversations=%s)",
            expected_unread or "unknown", max_conversations or "unlimited",
            extra={"step": self.name},
        )

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        try:
            await page.wait_for_selector('[role="listbox"]', timeout=listbox_timeout)
        except Exception:
            logger.info("No email list found - folder may be empty", extra={"step": self.name})
            return self._finish(ctx)

        await page.wait_for_timeout(row_wait)

        first_row = page.locator('[role="listbox"] [role="option"]').first
        total_count = await get_setsize(first_row)
        logger.info("Total conversations in folder (aria-setsize): %s", total_count or "unknown", extra={"step": self.name})

        if total_count == 0:
            return self._finish(ctx)

        target = expected_unread or total_count
        if max_conversations > 0 and (target is None or max_conversations < target):
            target = max_conversations

        has_virtuoso = await page.locator('[data-virtuoso-scroller="true"]').count() > 0

        # Scroll-parse loop — all data stays in memory
        seen_ids: set[str] = set()
        collected: list[dict] = []
        no_new_count = 0
        prev_total = 0

        for iteration in range(max_iterations):
            rows = page.locator('[role="listbox"] [role="option"]')
            try:
                current_count = await rows.count()
            except Exception:
                await page.wait_for_timeout(scroll_wait)
                continue

            new_found = 0
            for i in range(current_count):
                try:
                    row = rows.nth(i)
                    row_id = await row.get_attribute("id")
                    if not row_id or row_id in seen_ids:
                        continue

                    seen_ids.add(row_id)
                    email = await parse_email_card(row)
                    if not email["subject"] and not email["sender"]:
                        seen_ids.discard(row_id)
                        continue

                    collected.append(email)
                    new_found += 1

                    if max_conversations > 0 and len(collected) >= max_conversations:
                        break
                except Exception as e:
                    logger.debug("Row %d skipped: %s", i, e, extra={"step": self.name})
                    continue

            total_parsed = len(collected)
            logger.info(
                "Iteration %d: +%d new, %d total, %d DOM rows",
                iteration + 1, new_found, total_parsed, current_count,
                extra={"step": self.name},
            )

            if max_conversations > 0 and total_parsed >= max_conversations:
                break
            if target and total_parsed >= target:
                break

            # Stall detection
            if total_parsed == prev_total:
                no_new_count += 1
                if no_new_count >= no_new_limit:
                    logger.info("Stalled at %d conversations, stopping", total_parsed, extra={"step": self.name})
                    ctx.shared["scroll_exhausted"] = True
                    break
            else:
                no_new_count = 0
                prev_total = total_parsed

            # Scroll
            if has_virtuoso:
                scroll_info = await page.evaluate(_SCROLL_JS)
                if scroll_info:
                    at_bottom = scroll_info["scrollTop"] + scroll_info["clientHeight"] >= scroll_info["scrollHeight"] - 10
                    if at_bottom and no_new_count >= 2:
                        ctx.shared["scroll_exhausted"] = True
                        break
            else:
                listbox = page.locator('[role="listbox"]')
                bbox = await listbox.bounding_box()
                if bbox:
                    await page.mouse.move(bbox["x"] + 100, bbox["y"] + bbox["height"] / 2)
                    await page.mouse.wheel(0, 400)

            await page.wait_for_timeout(scroll_wait)

        ctx.shared["conversations"] = collected
        logger.info("Scrape completed - %d conversations collected", len(collected), extra={"step": self.name})
        return self._finish(ctx)

    def _finish(self, ctx: StepContext) -> StepContext:
        conversations = ctx.shared.get("conversations", [])
        expected = ctx.shared.get("expected_unread")
        scraped = len(conversations)
        scroll_exhausted = ctx.shared.get("scroll_exhausted", False)

        ctx.shared["unread_count"] = scraped
        ctx.shared["scroll_exhausted"] = scroll_exhausted
        ctx.shared["complete"] = (
            (expected is not None and scraped >= expected)
            or scroll_exhausted
        )

        if expected and scraped < expected:
            if scroll_exhausted:
                logger.info(
                    "Scraped %d conversations of %d expected messages (conversation grouping)",
                    scraped, expected, extra={"step": self.name},
                )
            else:
                logger.warning("Incomplete: got %d of %d expected", scraped, expected, extra={"step": self.name})
        return ctx
