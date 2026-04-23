"""
step_05_extract_body.py — Opens each scraped conversation and extracts the HTML body
of the FIRST (oldest) email in the thread.

Flow per conversation:
1. Click on the conversation row in the list
2. Wait for the reading pane to load
3. Scroll to the bottom of the conversation (oldest message is last)
4. Extract the HTML of that last/oldest message
5. Store it in the conversation's 'body' field
"""

from __future__ import annotations

from agent.browser.base_step import BaseStep, StepContext
from shared.logger import get_logger

logger = get_logger("agent")


# JS: scroll the conversation pane to the very bottom to reach the first/oldest message
_SCROLL_TO_BOTTOM_JS = """() => {
    // The conversation scroll container
    const selectors = [
        'div[role="complementary"]',
        'div[data-app-section="ConversationContainer"]',
        'div.customScrollBar',
    ];

    for (const sel of selectors) {
        const container = document.querySelector(sel);
        if (container && container.scrollHeight > container.clientHeight) {
            container.scrollTop = container.scrollHeight;
            return true;
        }
    }

    // Fallback: scroll the whole reading pane area
    const pane = document.querySelector('[role="main"]');
    if (pane) {
        pane.scrollTop = pane.scrollHeight;
        return true;
    }

    return false;
}"""


# JS: get all individual message bodies in the conversation, return the last one (oldest)
_EXTRACT_FIRST_MESSAGE_JS = """() => {
    // Outlook renders each message in the thread as a separate div
    // with role="document" or within an ItemPart container
    const messageBodies = document.querySelectorAll(
        'div[role="document"], div[data-testid="message-body"]'
    );

    if (messageBodies.length > 0) {
        // Last element = oldest/first message in the conversation
        const oldest = messageBodies[messageBodies.length - 1];
        return oldest.innerHTML.trim();
    }

    // Fallback: try common Outlook body containers
    const fallbackSelectors = [
        'div.XbIp4',
        'div[aria-label*="cuerpo"]',
        'div[aria-label*="body"]',
        'div[aria-label*="Cuerpo"]',
        'div[aria-label*="Body"]',
    ];

    for (const sel of fallbackSelectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
            const oldest = els[els.length - 1];
            if (oldest.innerHTML.trim().length > 10) {
                return oldest.innerHTML.trim();
            }
        }
    }

    // Last resort: largest dir=ltr/rtl div
    const candidates = document.querySelectorAll('div[dir="ltr"], div[dir="rtl"]');
    let best = null;
    let bestLen = 0;
    for (const c of candidates) {
        if (c.innerHTML.length > bestLen) {
            bestLen = c.innerHTML.length;
            best = c;
        }
    }
    if (best && bestLen > 50) {
        return best.innerHTML.trim();
    }

    return '';
}"""


# JS: count how many messages are visible in the conversation
_COUNT_MESSAGES_JS = """() => {
    const msgs = document.querySelectorAll(
        'div[role="document"], div[data-testid="message-body"]'
    );
    return msgs.length;
}"""


class ExtractBodyStep(BaseStep):
    name = "extract_body"
    is_critical = False

    async def execute(self, ctx: StepContext) -> StepContext:
        page = ctx.page
        conversations = ctx.shared.get("conversations", [])

        if not conversations:
            logger.info("No conversations to extract body from", extra={"step": self.name})
            return ctx

        logger.info(
            "Extracting body from %d conversations",
            len(conversations),
            extra={"step": self.name},
        )

        for i, conv in enumerate(conversations):
            conv_id = conv.get("conversation_id", "")
            if not conv_id:
                continue

            try:
                # Find the row in the list by data-convid
                row = page.locator(f'[role="option"][data-convid="{conv_id}"]')
                if await row.count() == 0:
                    logger.debug("Row not found for conv %s, skipping", conv_id, extra={"step": self.name})
                    continue

                # Click to open the conversation
                await row.first.click()
                await page.wait_for_timeout(2000)

                # Wait for at least one message body to appear
                try:
                    await page.wait_for_selector(
                        'div[role="document"], div[data-testid="message-body"], '
                        'div.XbIp4, div[aria-label*="cuerpo"], div[aria-label*="body"]',
                        timeout=8000,
                    )
                except Exception:
                    logger.debug("Reading pane not found for conv %s", conv_id[:20], extra={"step": self.name})
                    continue

                # Check how many messages are in the thread
                msg_count = await page.evaluate(_COUNT_MESSAGES_JS)
                logger.debug(
                    "Conv %s has %d visible messages",
                    conv_id[:20], msg_count,
                    extra={"step": self.name},
                )

                # Scroll to bottom to reach the first/oldest message
                if msg_count > 1:
                    for _ in range(5):
                        scrolled = await page.evaluate(_SCROLL_TO_BOTTOM_JS)
                        if not scrolled:
                            break
                        await page.wait_for_timeout(800)

                    # Extra wait for content to render after scroll
                    await page.wait_for_timeout(1000)

                # Extract the oldest message body HTML
                body_html = await page.evaluate(_EXTRACT_FIRST_MESSAGE_JS)

                if body_html:
                    conv["body"] = body_html
                    logger.info(
                        "[%d/%d] Extracted body for conv %s (%d chars, %d msgs in thread)",
                        i + 1, len(conversations), conv_id[:20], len(body_html), msg_count,
                        extra={"step": self.name},
                    )
                else:
                    logger.debug(
                        "[%d/%d] No body found for conv %s",
                        i + 1, len(conversations), conv_id[:20],
                        extra={"step": self.name},
                    )

            except Exception as e:
                logger.warning(
                    "[%d/%d] Error extracting body for conv %s: %s",
                    i + 1, len(conversations), conv_id[:20], e,
                    extra={"step": self.name},
                )
                continue

        extracted = sum(1 for c in conversations if c.get("body"))
        logger.info(
            "Body extraction complete: %d/%d conversations have body",
            extracted, len(conversations),
            extra={"step": self.name},
        )

        ctx.shared["conversations"] = conversations
        return ctx
