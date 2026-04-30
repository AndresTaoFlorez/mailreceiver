from __future__ import annotations

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Parameter

from api.infrastructure.database import async_session
from api.infrastructure import especialist_repository as repo
from api.domain.schemas import EspecialistCreate, EspecialistUpdate
from api.domain.mappers import ok, ok_list, map_especialist


class EspecialistController(Controller):
    path = "/especialists"
    tags = ["Specialists"]

    @get(
        "/",
        summary="List specialists",
        status_code=HTTP_200_OK,
    )
    async def list_especialists(
        self,
        level: int | None = Parameter(query="level", default=None),
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await repo.get_especialists(db, level=level, active_only=active_only)
        return ok_list("especialists", rows, map_especialist)

    @post(
        "/",
        summary="Create specialists",
        description="Register one or more specialists. Accepts a JSON array.",
        status_code=HTTP_201_CREATED,
    )
    async def create_especialist(self, data: list[EspecialistCreate]) -> dict:
        codes = [item.code for item in data]
        dupes_in_request = [c for c in codes if codes.count(c) > 1]
        if dupes_in_request:
            raise ClientException(
                detail=f"Duplicate codes in request: {', '.join(set(dupes_in_request))}",
                status_code=400,
            )

        async with async_session() as db:
            existing = await repo.get_especialists(db, active_only=False)
            existing_codes = {r.code for r in existing}
            already_exist = [c for c in codes if c in existing_codes]
            if already_exist:
                raise ClientException(
                    detail=f"Codes already exist: {', '.join(already_exist)}",
                    status_code=409,
                )

            created = []
            for item in data:
                row = await repo.create_especialist(
                    db, code=item.code, name=item.name, level=item.level,
                    load_percentage=item.load_percentage, priority=item.priority,
                )
                created.append(map_especialist(row))
        return ok(total=len(created), especialists=created)

    @put(
        "/{code:str}",
        summary="Update specialist",
        status_code=HTTP_200_OK,
    )
    async def update_especialist(self, code: str, data: EspecialistUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await repo.update_especialist(db, code, **fields)
        if not row:
            raise NotFoundException(detail=f"Especialist with code '{code}' not found")
        return ok(especialist=map_especialist(row))
