"""
step_05_extract_body.py — Opens each scraped conversation and extracts the HTML body
of the FIRST (oldest) email in the thread.

Flow per conversation:
1. Scroll the email list to bring the conversation row into the virtual DOM
2. Click on the conversation row
3. Wait for the reading pane to load
4. Scroll to the bottom of the conversation (oldest message is last)
5. Extract the HTML of that last/oldest message
6. Store it in the conversation's 'body' field
"""

from __future__ import annotations

from pathlib import Path

from agent.browser.base_step import BaseStep, StepContext
from shared.logger import get_logger

EXTRACTED_HTML_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "html"

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


# JS: extract the full reading pane (subject, sender, date, attachments, body)
# and clean Outlook UI chrome while preserving the email content faithfully
_EXTRACT_FULL_EMAIL_JS = """(mode) => {
    // mode: 'latest' (newest email), 'oldest' (first email), 'full' (all emails)
    // Build a clean email HTML from the reading pane parts,
    // extracting only the meaningful content (sender, date, to, attachments, body)
    // and discarding all Outlook UI chrome.

    // --- 0. Extract subject ---
    let subject = '';
    const subjectEl = document.querySelector('[id$="_SUBJECT"], [aria-labelledby*="SUBJECT"]');
    if (subjectEl) {
        // The subject heading may reference another element via aria-labelledby
        const labelledBy = subjectEl.getAttribute('aria-labelledby') || '';
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) subject = labelEl.textContent.trim();
        }
        if (!subject) subject = subjectEl.textContent.trim();
    }
    // Fallback: conversation subject in the header
    if (!subject) {
        const convSubject = document.querySelector('[id*="CONV_"][id$="_SUBJECT"]');
        if (convSubject) subject = convSubject.textContent.trim();
    }

    // --- 1. Extract sender name ---
    let sender = '';
    const senderEl = document.querySelector('.OZZZK, [id$="_FROM"] span span');
    if (senderEl) sender = senderEl.textContent.trim();

    // --- 2. Extract date ---
    let date = '';
    const dateEl = document.querySelector('[data-testid="SentReceivedSavedTime"]');
    if (dateEl) date = dateEl.textContent.trim();

    // --- 3. Extract recipients (Para:) ---
    let recipients = '';
    const recipientEl = document.querySelector('[data-testid="RecipientWell"]');
    if (recipientEl) {
        // Get all recipient names, skip the "Para:" label
        const names = recipientEl.querySelectorAll('[class*="hoverTarget"] span[class*="1abrpkv"], [class*="hoverTarget"][aria-label]');
        const recips = [];
        names.forEach(n => {
            const text = n.textContent.trim() || n.getAttribute('aria-label') || '';
            if (text && text !== 'Para:' && text !== 'To:') recips.push(text);
        });
        if (recips.length > 0) recipients = recips.join(', ');

        // Fallback: read from aria-label
        if (!recipients) {
            const editorEl = recipientEl.querySelector('[aria-label*="Para:"], [aria-label*="To:"]');
            if (editorEl) {
                const label = editorEl.getAttribute('aria-label') || '';
                recipients = label.replace(/^(Para|To):\\s*/i, '').trim();
            }
        }
    }

    // --- 4. Extract attachments ---
    const attachments = [];
    document.querySelectorAll('[id$="_ATTACHMENTS"] [role="option"]').forEach(att => {
        const label = att.getAttribute('aria-label') || '';
        // e.g. "Resolución04NombraSecretaria.pdf Abrir 149 KB"
        const clean = label.replace(/\\s*Abrir\\s*/i, ' ').replace(/\\s*Open\\s*/i, ' ').trim();
        if (clean) attachments.push(clean);
    });

    // --- 5. Extract body based on mode ---
    let bodyHtml = '';
    const messageBodies = document.querySelectorAll(
        'div[role="document"], div[data-testid="message-body"]'
    );

    function cleanMessageClone(el) {
        const clone = el.cloneNode(true);
        clone.querySelectorAll('button, .fui-Button, .qF8_5').forEach(e => e.remove());
        clone.querySelectorAll('.R1UVb').forEach(e => {
            if (!e.querySelector('table, img')) e.remove();
        });
        clone.querySelectorAll('table').forEach(t => {
            if (t.style.transform) t.style.transform = '';
            if (t.style.transformOrigin) t.style.transformOrigin = '';
            t.style.width = '100%';
            t.style.boxSizing = 'border-box';
        });
        return clone.innerHTML.trim();
    }

    if (messageBodies.length > 0) {
        if (mode === 'full') {
            // All messages, newest first
            const parts = [];
            for (let i = 0; i < messageBodies.length; i++) {
                const part = cleanMessageClone(messageBodies[i]);
                if (part) parts.push(part);
            }
            bodyHtml = parts.join('<hr style="border:none;border-top:2px solid rgba(128,128,128,0.3);margin:20px 0;">');
        } else if (mode === 'oldest') {
            bodyHtml = cleanMessageClone(messageBodies[messageBodies.length - 1]);
        } else {
            // 'latest' (default) — first in DOM is the newest
            bodyHtml = cleanMessageClone(messageBodies[0]);
        }
    } else {
        // Fallback selectors — progressively broader to catch system/notification emails
        const fallbacks = [
            'div.XbIp4',
            'div[aria-label*="cuerpo"]',
            'div[aria-label*="body"]',
            'div[aria-label*="mensaje"]',
            'div[aria-label*="message"]',
            'div[data-testid="reading-pane-content"]',
            'div[role="main"] div[class*="body"]',
            'div[role="main"] div[class*="Body"]',
            'div[role="complementary"] div[class*="body"]',
            'div[role="complementary"] div[class*="Body"]',
        ];
        for (const sel of fallbacks) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0 && els[els.length - 1].innerHTML.trim().length > 10) {
                bodyHtml = els[els.length - 1].innerHTML.trim();
                break;
            }
        }

        // Last resort: grab the entire reading pane content area
        if (!bodyHtml) {
            const paneSelectors = [
                'div[role="main"]',
                'div[role="complementary"]',
                'div[data-app-section="ConversationContainer"]',
            ];
            for (const sel of paneSelectors) {
                const pane = document.querySelector(sel);
                if (pane && pane.innerHTML.trim().length > 50) {
                    const clone = pane.cloneNode(true);
                    // Remove toolbar/header chrome, keep only content
                    clone.querySelectorAll(
                        'button, [role="toolbar"], [role="menubar"], [role="banner"], '
                        + '.fui-Button, [data-testid="reading-pane-header"]'
                    ).forEach(el => el.remove());
                    const cleaned = clone.innerHTML.trim();
                    if (cleaned.length > 50) {
                        bodyHtml = cleaned;
                        break;
                    }
                }
            }
        }
    }

    if (!bodyHtml && !sender) return {html: '', to_address: ''};

    // --- 6. Build clean HTML ---
    let html = '';

    // Header section
    if (subject) {
        html += '<div style="margin-bottom:8px;font-size:16px;font-weight:bold;">' + subject + '</div>';
    }
    if (sender) {
        html += '<div style="margin-bottom:4px;font-size:14px;font-weight:bold;">' + sender + '</div>';
    }
    if (recipients) {
        html += '<div style="margin-bottom:4px;font-size:12px;opacity:0.8;">Para: ' + recipients + '</div>';
    }
    if (date) {
        html += '<div style="margin-bottom:8px;font-size:12px;opacity:0.7;">' + date + '</div>';
    }
    if (attachments.length > 0) {
        html += '<div style="margin-bottom:12px;font-size:12px;padding:8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;">';
        attachments.forEach(a => {
            html += '<div style="padding:2px 0;">📎 ' + a + '</div>';
        });
        html += '</div>';
    }

    // Separator
    if (sender || recipients || date) {
        html += '<hr style="border:none;border-top:1px solid rgba(128,128,128,0.3);margin:12px 0;">';
    }

    // Body
    html += bodyHtml;

    return {html: html, to_address: recipients};
}"""


# JS: count how many messages are visible in the conversation
_COUNT_MESSAGES_JS = """() => {
    const msgs = document.querySelectorAll(
        'div[role="document"], div[data-testid="message-body"]'
    );
    return msgs.length;
}"""


# JS: scroll the email list back to the top
_SCROLL_LIST_TO_TOP_JS = """() => {
    const virtuoso = document.querySelector('[data-virtuoso-scroller="true"]');
    if (virtuoso) {
        virtuoso.scrollTop = 0;
        return 'virtuoso';
    }
    const listbox = document.querySelector('[role="listbox"]');
    if (listbox) {
        listbox.scrollTop = 0;
        return 'listbox';
    }
    return null;
}"""


# JS: scroll the email list down by a fraction to find rows not yet in the virtual DOM
_SCROLL_LIST_DOWN_JS = """() => {
    const virtuoso = document.querySelector('[data-virtuoso-scroller="true"]');
    if (virtuoso) {
        const before = virtuoso.scrollTop;
        virtuoso.scrollTop += virtuoso.clientHeight * 0.5;
        return { scrolled: virtuoso.scrollTop > before, scrollTop: virtuoso.scrollTop };
    }
    return { scrolled: false, scrollTop: 0 };
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

        # Scroll the email list back to the top before starting.
        # Step 4 scrolled to the bottom, so most rows are gone from the virtual DOM.
        await page.evaluate(_SCROLL_LIST_TO_TOP_JS)
        await page.wait_for_timeout(1500)

        for i, conv in enumerate(conversations):
            conv_id = conv.get("conversation_id", "")
            if not conv_id:
                continue

            try:
                # Find the row — it may not be in the virtual DOM yet, so scroll to find it
                row = await self._find_row_in_virtual_list(page, conv_id)
                if row is None:
                    logger.info(
                        "[%d/%d] Row not found for conv %s after scrolling, skipping",
                        i + 1, len(conversations), conv_id[:20],
                        extra={"step": self.name},
                    )
                    continue

                # Click on the subject area to open the conversation
                # Avoid clicking on tag/category spans (.KwNwl) which open filters
                await row.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                subject_el = row.locator("span.TtcXM").first
                if await subject_el.count() > 0:
                    await subject_el.click()
                else:
                    await row.click(position={"x": 200, "y": 10})
                await page.wait_for_timeout(2000)

                # Wait for at least one message body to appear
                try:
                    await page.wait_for_selector(
                        'div[role="document"], div[data-testid="message-body"], '
                        'div.XbIp4, div[aria-label*="cuerpo"], div[aria-label*="body"]',
                        timeout=12000,
                    )
                except Exception:
                    logger.info(
                        "[%d/%d] Reading pane not found for conv %s",
                        i + 1, len(conversations), conv_id[:20],
                        extra={"step": self.name},
                    )
                    continue

                # Check how many messages are in the thread
                msg_count = await page.evaluate(_COUNT_MESSAGES_JS)
                logger.debug(
                    "Conv %s has %d visible messages",
                    conv_id[:20], msg_count,
                    extra={"step": self.name},
                )

                extraction_mode = ctx.shared.get("extraction_mode", "latest")

                # Scroll to bottom only when we need older messages
                if msg_count > 1 and extraction_mode in ("oldest", "full"):
                    for _ in range(5):
                        scrolled = await page.evaluate(_SCROLL_TO_BOTTOM_JS)
                        if not scrolled:
                            break
                        await page.wait_for_timeout(800)

                    # Extra wait for content to render after scroll
                    await page.wait_for_timeout(1000)

                # Extract body HTML + metadata based on extraction_mode
                result = await page.evaluate(_EXTRACT_FULL_EMAIL_JS, extraction_mode)
                body_html = result.get("html", "") if isinstance(result, dict) else result
                to_address = result.get("to_address", "") if isinstance(result, dict) else ""

                if to_address:
                    conv["to_address"] = to_address

                if body_html:
                    conv["body"] = body_html

                    # Save HTML to disk for inspection
                    EXTRACTED_HTML_DIR.mkdir(parents=True, exist_ok=True)
                    safe_id = conv_id[:40].replace("/", "_").replace("\\", "_")
                    subject = conv.get("subject", "sin_asunto")[:50].replace("/", "_").replace("\\", "_")
                    filename = f"{i + 1:03d}_{safe_id}_{subject}.html"
                    html_path = EXTRACTED_HTML_DIR / filename
                    # Detect dark mode: Outlook uses data-ogsc attributes and
                    # rgb(255, 255, 255) text color when in dark mode
                    lower_html = body_html.lower()
                    is_dark = "data-ogsc" in lower_html or "rgb(255, 255, 255)" in lower_html
                    if is_dark:
                        bg_style = "background:#1e1e1e;color:#d4d4d4;"
                    else:
                        bg_style = "background:#ffffff;color:#1e1e1e;"
                    wrapped = (
                        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                        f'<body style="{bg_style}padding:20px;font-family:sans-serif">'
                        f'{body_html}</body></html>'
                    )
                    html_path.write_text(wrapped, encoding="utf-8")

                    logger.info(
                        "[%d/%d] Extracted body for conv %s (%d chars, %d msgs in thread) → %s",
                        i + 1, len(conversations), conv_id[:20], len(body_html), msg_count, filename,
                        extra={"step": self.name},
                    )
                else:
                    logger.info(
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

    async def _find_row_in_virtual_list(self, page, conv_id: str, max_scrolls: int = 30):
        """Find a conversation row in the virtual-scrolled email list.

        Outlook uses Virtuoso virtual scroll which only keeps ~15-20 rows in
        the DOM at a time. If the row isn't visible, we scroll down incrementally
        until we find it or exhaust attempts.
        """
        selector = f'[role="option"][data-convid="{conv_id}"]'

        # Check if already visible
        row = page.locator(selector)
        if await row.count() > 0:
            return row.first

        # Not visible — scroll down incrementally to find it
        for _ in range(max_scrolls):
            result = await page.evaluate(_SCROLL_LIST_DOWN_JS)
            if not result.get("scrolled"):
                break
            await page.wait_for_timeout(800)

            row = page.locator(selector)
            if await row.count() > 0:
                return row.first

        return None
