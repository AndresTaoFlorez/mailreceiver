from __future__ import annotations

import uuid

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import work_window_repository as ww_repo
from domain import balance_repository as bal_repo
from domain import especialist_repository as esp_repo
from domain.schemas import (
    WorkWindowCreate,
    WorkWindowUpdate,
    WorkWindowOut,
    BalanceSnapshotOut,
    LoadStatusEntry,
)


class CoordinatorController(Controller):
    path = "/coordinator"
    tags = ["Coordinator"]

    # --- Work Windows ---

    @get(
        "/work-windows",
        summary="List work windows",
        description=(
            "Returns work windows, optionally filtered.\n\n"
            "**Query params:**\n"
            "- **application_code**: Filter by application (e.g. `tutela_en_linea`)\n"
            "- **especialist_code**: Filter by specialist (e.g. `s20`)\n"
            "- **active_only**: If true (default), excludes closed/inactive windows"
        ),
        status_code=HTTP_200_OK,
    )
    async def list_work_windows(
        self,
        application_code: str | None = Parameter(query="application_code", default=None),
        especialist_code: str | None = Parameter(query="especialist_code", default=None),
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await ww_repo.get_work_windows(
                db,
                application_code=application_code,
                especialist_code=especialist_code,
                active_only=active_only,
            )
        return {
            "status": "ok",
            "total": len(rows),
            "work_windows": [WorkWindowOut.from_row(r).model_dump() for r in rows],
        }

    @post(
        "/work-windows",
        summary="Create work window",
        description=(
            "Defines when a specialist handles an application.\n\n"
            "**Request body:**\n"
            "- **especialist_code**: Specialist code (e.g. `s20`). Must exist in the especialist table\n"
            "- **application_code**: Application code (e.g. `tutela_en_linea`). Must exist in the applications table\n"
            "- **load_percentage**: Fixed percentage of cases this specialist should receive (1-100). "
            "Leave null to auto-distribute: the system splits the remaining percentage equally among all null specialists\n"
            "- **schedule**: Date-keyed JSON object defining availability. "
            "Each key is an ISO date (`2026-04-28`), each value is an array of time slots `{start, end}` in `HH:MM` format. "
            "Dates not listed = specialist is off that day. "
            "Example: `{\"2026-04-28\": [{\"start\": \"08:00\", \"end\": \"12:00\"}], \"2026-04-29\": [{\"start\": \"08:00\", \"end\": \"12:00\"}, {\"start\": \"14:00\", \"end\": \"17:00\"}]}`\n"
            "- **inherit_balance_from** *(optional)*: UUID of a previous work window. "
            "If set, the specialist starts with the leftover balance (debt/surplus) from that window instead of zero. "
            "Useful for week-to-week continuity"
        ),
        status_code=HTTP_201_CREATED,
    )
    async def create_work_window(self, data: WorkWindowCreate) -> dict:
        async with async_session() as db:
            row = await ww_repo.create_work_window(
                db,
                especialist_code=data.especialist_code,
                application_code=data.application_code,
                schedule=data.schedule,
                load_percentage=data.load_percentage,
            )

            initial_balance = 0
            inherited_from = None
            if data.inherit_balance_from:
                old_snap = await bal_repo.get_snapshot(
                    db, data.especialist_code, data.inherit_balance_from,
                )
                if old_snap:
                    initial_balance = old_snap.balance
                    inherited_from = old_snap.id

            await bal_repo.ensure_snapshot(
                db,
                especialist_code=data.especialist_code,
                application_code=data.application_code,
                work_window_id=row.id,
                initial_balance=initial_balance,
                inherited_from=inherited_from,
            )
            await db.commit()

        return {"status": "ok", "work_window": WorkWindowOut.from_row(row).model_dump()}

    @put(
        "/work-windows/{window_id:str}",
        summary="Update work window",
        description=(
            "Modify an existing work window. Changes only affect future assignments.\n\n"
            "**Path param:**\n"
            "- **window_id**: UUID of the work window\n\n"
            "**Request body (all optional, send only what you want to change):**\n"
            "- **load_percentage**: New workload percentage (1-100 or null for auto)\n"
            "- **schedule**: Full replacement schedule JSON (not a partial patch — send the complete schedule)\n"
            "- **active**: Set false to close this window"
        ),
        status_code=HTTP_200_OK,
    )
    async def update_work_window(self, window_id: str, data: WorkWindowUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await ww_repo.update_work_window(db, uuid.UUID(window_id), **fields)
        if not row:
            raise NotFoundException(detail=f"WorkWindow '{window_id}' not found")
        return {"status": "ok", "work_window": WorkWindowOut.from_row(row).model_dump()}

    @post(
        "/work-windows/{window_id:str}/close",
        summary="Close work window early",
        description=(
            "Deactivates a work window before its schedule ends. "
            "The specialist will no longer receive assignments through this window.\n\n"
            "**Path param:**\n"
            "- **window_id**: UUID of the work window to close"
        ),
        status_code=HTTP_200_OK,
    )
    async def close_work_window(self, window_id: str) -> dict:
        async with async_session() as db:
            closed = await ww_repo.close_work_window(db, uuid.UUID(window_id))
        if not closed:
            raise NotFoundException(detail=f"WorkWindow '{window_id}' not found")
        return {"status": "ok", "message": "Work window closed"}

    # --- Balance ---

    @get(
        "/balance/{work_window_id:str}",
        summary="Get balance snapshots",
        description=(
            "Returns the cumulative balance state for each specialist in a work window.\n\n"
            "**Path param:**\n"
            "- **work_window_id**: UUID of the work window\n\n"
            "**Response fields per snapshot:**\n"
            "- **cases_assigned**: How many cases the specialist has received so far\n"
            "- **expected_cases**: How many they should have based on their load_percentage\n"
            "- **balance**: `cases_assigned - expected_cases`. Negative = system owes them cases (higher priority). Positive = they are ahead"
        ),
        status_code=HTTP_200_OK,
    )
    async def get_balance(self, work_window_id: str) -> dict:
        async with async_session() as db:
            rows = await bal_repo.get_snapshots_for_window(db, uuid.UUID(work_window_id))
        return {
            "status": "ok",
            "total": len(rows),
            "snapshots": [BalanceSnapshotOut.from_row(r).model_dump() for r in rows],
        }

    @post(
        "/balance/{work_window_id:str}/reset",
        summary="Reset balance to zero",
        description=(
            "Sets cases_assigned, expected_cases, and balance to 0 for all specialists in the window. "
            "Use when the coordinator wants to start counting from scratch mid-week.\n\n"
            "**Path param:**\n"
            "- **work_window_id**: UUID of the work window to reset"
        ),
        status_code=HTTP_200_OK,
    )
    async def reset_balance(self, work_window_id: str) -> dict:
        async with async_session() as db:
            count = await bal_repo.reset_snapshot(db, uuid.UUID(work_window_id))
            await db.commit()
        return {"status": "ok", "message": f"Reset {count} snapshots"}

    # --- Load status ---

    @get(
        "/load-status",
        summary="Current workload status",
        description=(
            "Overview of how work is distributed for an application. "
            "Shows each specialist's assigned cases, expected cases, and balance.\n\n"
            "**Query params:**\n"
            "- **application_code**: Application code to query (required)\n\n"
            "**Response fields per entry:**\n"
            "- **especialist_code / especialist_name**: Who\n"
            "- **cases_assigned**: How many cases they have\n"
            "- **expected_cases**: How many they should have based on load %\n"
            "- **balance**: Positive = ahead, negative = system owes them\n"
            "- **window_active**: Whether their work window is currently active"
        ),
        status_code=HTTP_200_OK,
    )
    async def load_status(
        self,
        application_code: str = Parameter(query="application_code"),
    ) -> dict:
        async with async_session() as db:
            snapshots = await bal_repo.get_snapshots_for_app(db, application_code)
            specialists = await esp_repo.get_especialists(db, active_only=False)
            windows = await ww_repo.get_work_windows(db, application_code=application_code, active_only=False)

        spec_map = {s.code: s for s in specialists}
        window_active_map = {w.id: w.active for w in windows}

        entries = []
        for snap in snapshots:
            spec = spec_map.get(snap.especialist_code)
            entries.append(LoadStatusEntry(
                especialist_code=snap.especialist_code,
                especialist_name=spec.name if spec else "",
                cases_assigned=snap.cases_assigned,
                expected_cases=float(snap.expected_cases),
                balance=float(snap.balance),
                window_active=window_active_map.get(snap.work_window_id, False),
            ).model_dump())

        return {
            "status": "ok",
            "application_code": application_code,
            "total": len(entries),
            "load_status": entries,
        }
