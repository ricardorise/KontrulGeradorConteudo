from uuid import UUID

import asyncpg

from studio.guidance.domain.guideline import Guideline, GuidelineOrigin
from studio.shared.domain.guidance import GuidelineScope

T = "content_studio"


def _guideline(r: asyncpg.Record) -> Guideline:
    return Guideline(
        id=r["id"], scope=GuidelineScope(r["scope"]), text=r["text"], active=r["active"],
        source=GuidelineOrigin(r["source"]), created_at=r["created_at"],
    )  # fmt: skip


class PostgresGuidelineRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, g: Guideline) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.guidelines (id, scope, text, active, source, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
            g.id, g.scope.value, g.text, g.active, g.source.value, g.created_at,
        )

    async def get(self, guideline_id: UUID) -> Guideline | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.guidelines WHERE id=$1", guideline_id)
        return _guideline(row) if row else None

    async def set_active(self, guideline_id: UUID, active: bool) -> None:
        await self._pool.execute(f"UPDATE {T}.guidelines SET active=$2 WHERE id=$1", guideline_id, active)

    async def delete(self, guideline_id: UUID) -> None:
        await self._pool.execute(f"DELETE FROM {T}.guidelines WHERE id=$1", guideline_id)

    async def list_all(self) -> list[Guideline]:
        rows = await self._pool.fetch(f"SELECT * FROM {T}.guidelines ORDER BY created_at")
        return [_guideline(r) for r in rows]

    async def find_duplicate(self, scope: GuidelineScope, text: str) -> Guideline | None:
        row = await self._pool.fetchrow(
            f"SELECT * FROM {T}.guidelines WHERE scope=$1 AND lower(text)=lower($2) LIMIT 1", scope.value, text
        )
        return _guideline(row) if row else None
