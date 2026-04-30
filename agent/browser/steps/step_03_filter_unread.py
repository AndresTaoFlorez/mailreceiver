from __future__ import annotations

from api.presentation.config import STORAGE_PATH
from agent.browser.base_step import BaseStep, StepContext
from agent.browser.scraping_config import load as load_scraping_config
from api.shared.logger import get_logger

logger = get_logger("agent")


class FilterUnreadStep(BaseStep):
    name = "filter_unread"
    is_critical = False

    async def execute(self, ctx: StepContext) -> StepContext:
        page = ctx.page

        if not ctx.shared.get("unread_only", False):
            logger.info("No filter requested, skipping", extra={"step": self.name})
            return ctx

        logger.info("Applying unread filter", extra={"step": self.name})

        # --- Step 1: Find and click the filter button ---
        filter_btn_selectors = [
            'button[id="mailListFilterMenu"]',
            'button[aria-label*="iltr"]',
            'button[aria-label*="Filter"]',
            'button[aria-label*="Filtrar"]',
        ]

        clicked_btn = False
        for sel in filter_btn_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    clicked_btn = True
                    logger.info("Filter button clicked with: %s", sel, extra={"step": self.name})
                    break
            except Exception:
                continue

        if not clicked_btn:
            logger.warning("Could not find filter button", extra={"step": self.name})
            ctx.shared["filter_applied"] = False
            return ctx

        # Wait for dropdown to appear
        await page.wait_for_timeout(2000)

        # Save screenshot AFTER click for debugging
        screenshot_path = STORAGE_PATH / "debug_filter_after_click.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path))

        # Dump the dropdown HTML for debugging
        try:
            menu_html = await page.evaluate("""() => {
                const menus = document.querySelectorAll('[role="menu"], [role="listbox"], [role="menubar"]');
                return Array.from(menus).map(m => m.outerHTML).join('\\n---\\n');
            }""")
            debug_path = STORAGE_PATH / "debug_filter_menu.html"
            debug_path.write_text(menu_html or "(no menu found)", encoding="utf-8")
        except Exception:
            pass

        # --- Step 2: Find and click the "No leido" / "Unread" option ---
        selectors = [
            '[role="menuitemradio"]:has-text("No le")',
            '[role="menuitemradio"]:has-text("Unread")',
            '[role="menuitem"]:has-text("No le")',
            '[role="menuitem"]:has-text("Unread")',
            '[role="option"]:has-text("No le")',
            '[role="option"]:has-text("Unread")',
            'button:has-text("No le")',
            'button:has-text("Unread")',
            'div[role="menu"] >> text=/No le[ií]do/i',
            'div[role="menu"] >> text=/Unread/i',
        ]

        for selector in selectors:
            option = page.locator(selector).first
            try:
                if await option.count() > 0 and await option.is_visible():
                    await option.click()
                    logger.info("Clicked unread option with: %s", selector, extra={"step": self.name})
                    break
            except Exception:
                continue
        else:
            logger.warning("Could not find unread filter option in dropdown", extra={"step": self.name})
            await page.keyboard.press("Escape")
            ctx.shared["filter_applied"] = False
            return ctx

        # Wait for the filter to apply and list to reload
        cfg = load_scraping_config()
        await page.wait_for_timeout(cfg["filter_wait_ms"])

        # Save screenshot after filter applied
        await page.screenshot(path=str(STORAGE_PATH / "debug_filter_applied.png"))

        ctx.shared["filter_applied"] = True
        logger.info("Unread filter applied", extra={"step": self.name})
        return ctx
