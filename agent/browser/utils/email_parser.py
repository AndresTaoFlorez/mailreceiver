"""
email_parser.py — Parses an Outlook Web email card (role="option") into structured data.

Outlook Web renders each email in the list as a div[role="option"].
The relevant data lives in:

    Sender name : <span title="user@domain.com">Display Name</span>
    Subject     : <span class="TtcXM" title="">Subject text</span>
    Date        : <span title="Mar 17/03/2026 9:04">17/03/2026</span>
    Unread      : aria-label starts with "No leido" or "Unread"
    Conv ID     : data-convid attribute on the row

The parser extracts all fields in a single JS evaluate call for performance.
"""

from __future__ import annotations

from playwright.async_api import Locator


# Single JS function that extracts all fields at once — avoids multiple round-trips
_PARSE_JS = """el => {
    const result = {
        conversation_id: el.getAttribute('data-convid') || '',
        subject: '',
        sender: '',
        sender_email: '',
        body: '',
        tags: '',
        to_address: '',
        from_address: ''
    };

    // Sender: span whose title contains '@'
    const senderEl = el.querySelector('span[title*="@"]');
    if (senderEl) {
        result.sender = (senderEl.textContent || '').trim();
        result.sender_email = (senderEl.getAttribute('title') || '').trim();
        result.from_address = result.sender_email;
    }

    // Subject: span with class TtcXM, or first span[title] not sender/date/action
    // Use title attribute first (has full text), fallback to textContent
    const subjectEl = el.querySelector('span.TtcXM');
    if (subjectEl) {
        const titleAttr = (subjectEl.getAttribute('title') || '').trim();
        result.subject = titleAttr || (subjectEl.textContent || '').trim();
    } else {
        const actionKeywords = ['Marcar', 'Mark', 'Eliminar', 'Delete', 'Dejar', 'Pin', 'Archivar', 'Archive', 'Mover', 'Move', 'Busca'];
        const spans = el.querySelectorAll('span[title]');
        for (const sp of spans) {
            const title = sp.getAttribute('title') || '';
            const text = (sp.textContent || '').trim();
            if (!text || text.length <= 2) continue;
            if (title.includes('@')) continue;
            if (title.includes('/')) continue;
            if (actionKeywords.some(kw => title.includes(kw))) continue;
            result.subject = text;
            break;
        }
    }

    // Date: span whose title contains '/'
    // Format is typically "Mar 21/04/2026 19:11" or "21/04/2026 9:04"
    result.date = {year: null, month: null, day: null, hour: null};
    const dateEl = el.querySelector('span[title*="/"]');
    if (dateEl) {
        const raw = (dateEl.getAttribute('title') || '').trim();
        // Match dd/mm/yyyy and optional HH:MM
        const m = raw.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):?(\d{2})?/);
        if (m) {
            result.date.day = parseInt(m[1], 10);
            result.date.month = parseInt(m[2], 10);
            result.date.year = parseInt(m[3], 10);
            result.date.hour = parseInt(m[4], 10);
        }
    }

    return result;
}"""


async def parse_email_card(row: Locator) -> dict:
    """Extract all email fields in a single browser round-trip."""
    try:
        return await row.evaluate(_PARSE_JS)
    except Exception:
        return {
            "conversation_id": "",
            "subject": "",
            "sender": "",
            "sender_email": "",
            "body": "",
            "tags": "",
            "to_address": "",
            "from_address": "",
            "date": {"year": None, "month": None, "day": None, "hour": None},
        }


async def get_setsize(row: Locator) -> int | None:
    """Get the aria-setsize (total email count) from an email card."""
    val = await row.get_attribute("aria-setsize")
    return int(val) if val and val != "0" else None


async def is_unread(row: Locator) -> bool:
    """Check if an email card represents an unread message."""
    label = await row.get_attribute("aria-label") or ""
    label_lower = label.lower()
    return label_lower.startswith("no le") or label_lower.startswith("unread")
