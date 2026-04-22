from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeout

from agent.browser.base_step import BaseStep, StepContext
from shared.logger import get_logger

logger = get_logger("agent")

OUTLOOK_MAIL_URL = "https://outlook.office.com/mail/"


class LoginStep(BaseStep):
    name = "outlook_login"
    is_critical = True

    async def execute(self, ctx: StepContext) -> StepContext:
        page = ctx.page
        user = ctx.shared["outlook_user"]
        password = ctx.shared["outlook_password"]

        # Check if already on Outlook mail
        current_url = page.url
        if "outlook.office.com/mail" in current_url:
            # Verify the inbox is actually loaded (not a stale page)
            try:
                await page.locator('[role="tree"], [role="navigation"]').first.wait_for(
                    state="visible", timeout=5000
                )
                logger.info("Already logged in, skipping login", extra={"step": self.name})
                return ctx
            except PlaywrightTimeout:
                logger.info("Page looks stale, proceeding with login", extra={"step": self.name})

        # Navigate to Outlook mail
        logger.info("Navigating to Outlook mail", extra={"step": self.name})
        await page.goto(OUTLOOK_MAIL_URL)
        await page.wait_for_load_state("domcontentloaded")

        # Race: does the email input appear or are we already in the inbox?
        email_input = page.locator('input[type="email"]')
        try:
            await email_input.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            # No login form — we're already authenticated
            logger.info("No login form detected, already authenticated", extra={"step": self.name})
            await page.wait_for_url("**/mail/**", timeout=15000)
            return ctx

        # Full login flow
        logger.info("Entering email", extra={"step": self.name})
        await email_input.fill(user)
        await page.locator('input[type="submit"]').click()
        await page.wait_for_load_state("domcontentloaded")

        logger.info("Entering password", extra={"step": self.name})
        password_input = page.locator('input[type="password"]')
        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(password)
        await page.locator('input[type="submit"]').click()
        await page.wait_for_load_state("domcontentloaded")

        # "Stay signed in?" prompt
        try:
            checkbox = page.locator('input[type="checkbox"]')
            if await checkbox.count() > 0 and not await checkbox.is_checked():
                await checkbox.check()
            await page.locator('input[type="submit"]').click(timeout=5000)
            await page.wait_for_load_state("domcontentloaded")
            logger.info("Session kept alive", extra={"step": self.name})
        except Exception:
            logger.info("No 'Stay signed in' prompt - continuing")

        await page.wait_for_url("**/mail/**", timeout=30000)
        logger.info("Outlook login completed", extra={"step": self.name})
        return ctx
