from __future__ import annotations

from litestar import Litestar, Request, get, post
from litestar.di import Provide
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED

from mailreceiver.config import ensure_dirs
from mailreceiver.database import init_db
from mailreceiver.excel import update_excel
from mailreceiver.models import EmailIn
from mailreceiver.storage import list_emails, upsert_email


@post(
    "/emails",
    status_code=HTTP_201_CREATED,
    summary="Receive an email",
    description=(
        "Receives an email payload, stores metadata in SQLite, saves the HTML body to disk, "
        "decodes and saves base64 attachments, and updates the Excel summary. "
        "If the conversation_id already exists, the record is updated instead of duplicated."
    ),
    tags=["emails"],
)
async def receive_email(data: EmailIn) -> dict:
    record = await upsert_email(data)
    update_excel(record)
    return {"status": "ok", "conversation_id": record["conversation_id"]}


@get("/emails")
async def get_emails() -> list[dict]:
    return await list_emails()


@post(
    "/debug",
    summary="Debug incoming request",
    description="Accepts any JSON payload and echoes back headers, body, and query params for inspection.",
    tags=["debug"],
)
async def debug(request: Request) -> dict:
    body = await request.json()
    return {
        "headers": dict(request.headers),
        "query": dict(request.query_params),
        "body": body,
    }


@get("/health")
async def health() -> dict:
    return {"status": "healthy"}


async def on_startup() -> None:
    ensure_dirs()
    await init_db()


app = Litestar(
    route_handlers=[receive_email, get_emails, debug, health],
    on_startup=[on_startup],
)
