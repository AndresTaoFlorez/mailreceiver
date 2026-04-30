from __future__ import annotations

import uuid

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from api.infrastructure.database import async_session
from api.infrastructure import work_window_repository as ww_repo
from api.infrastructure import balance_repository as bal_repo
from api.infrastructure import especialist_repository as esp_repo
from api.domain.schemas import WorkWindowCreate, WorkWindowUpdate
from api.domain.mappers import ok, ok_list, map_work_window, map_balance_snapshot, map_load_status


class CoordinatorController(Controller):
    path = "/coordinator"
    tags = ["Coordinator"]

    # --- Work Windows ---

    @get(
        "/work-windows",
        summary="List work windows",
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
                db, application_code=application_code,
                especialist_code=especialist_code, active_only=active_only,
            )
        return ok_list("work_windows", rows, map_work_window)

    @post(
        "/work-windows",
        summary="Create work window",
        status_code=HTTP_201_CREATED,
    )
    async def create_work_window(self, data: WorkWindowCreate) -> dict:
        async with async_session() as db:
            esp = await esp_repo.get_especialist_by_code(db, data.especialist_code)
            if not esp:
                return {"status": "error", "message": f"Especialist '{data.especialist_code}' not found"}

            row = await ww_repo.create_work_window(
                db,
                especialist_id=esp.id,
                application_code=data.application_code,
                schedule=data.schedule,
                load_percentage=data.load_percentage,
            )

            initial_balance = 0
            inherited_from = None
            if data.inherit_balance_from:
                old_snap = await bal_repo.get_snapshot(
                    db, esp.id, uuid.UUID(data.inherit_balance_from),
                )
                if old_snap:
                    initial_balance = old_snap.balance
                    inherited_from = old_snap.id

            await bal_repo.ensure_snapshot(
                db,
                especialist_id=esp.id,
                application_code=data.application_code,
                work_window_id=row.id,
                initial_balance=initial_balance,
                inherited_from=inherited_from,
            )
            await db.commit()

        return ok(work_window=map_work_window(row))

    @put(
        "/work-windows/{window_id:str}",
        summary="Update work window",
        status_code=HTTP_200_OK,
    )
    async def update_work_window(self, window_id: str, data: WorkWindowUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await ww_repo.update_work_window(db, uuid.UUID(window_id), **fields)
            if not row:
                raise NotFoundException(detail=f"WorkWindow '{window_id}' not found")
            await db.commit()
        return ok(work_window=map_work_window(row))

    @post(
        "/work-windows/{window_id:str}/close",
        summary="Close work window early",
        status_code=HTTP_200_OK,
    )
    async def close_work_window(self, window_id: str) -> dict:
        async with async_session() as db:
            closed = await ww_repo.close_work_window(db, uuid.UUID(window_id))
            if not closed:
                raise NotFoundException(detail=f"WorkWindow '{window_id}' not found")
            await db.commit()
        return ok(message="Work window closed")

    # --- Balance ---

    @get(
        "/balance/{work_window_id:str}",
        summary="Get balance snapshots",
        status_code=HTTP_200_OK,
    )
    async def get_balance(self, work_window_id: str) -> dict:
        async with async_session() as db:
            rows = await bal_repo.get_snapshots_for_window(db, uuid.UUID(work_window_id))
        return ok_list("snapshots", rows, map_balance_snapshot)

    @post(
        "/balance/{work_window_id:str}/reset",
        summary="Reset balance to zero",
        status_code=HTTP_200_OK,
    )
    async def reset_balance(self, work_window_id: str) -> dict:
        async with async_session() as db:
            count = await bal_repo.reset_snapshot(db, uuid.UUID(work_window_id))
            await db.commit()
        return ok(message=f"Reset {count} snapshots")

    # --- Load status ---

    @get(
        "/load-status",
        summary="Current workload status",
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

        spec_map = {s.id: s for s in specialists}
        window_active_map = {w.id: w.active for w in windows}

        entries = [
            map_load_status(
                snap,
                specialist_name=spec_map[snap.especialist_id].name if snap.especialist_id in spec_map else "",
                window_active=window_active_map.get(snap.work_window_id, False),
            )
            for snap in snapshots
        ]

        return ok(application_code=application_code, total=len(entries), load_status=entries)
