from uuid import UUID

import asyncpg

from studio.scripting.domain.config import ScriptProfile

T = "content_studio"


def _profile(r: asyncpg.Record) -> ScriptProfile:
    return ScriptProfile(
        id=str(r["id"]), name=r["name"], description=r["description"], instructions=r["instructions"],
        created_at=r["created_at"],
    )  # fmt: skip


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


class PostgresScriptProfileRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def list_custom(self) -> list[ScriptProfile]:
        rows = await self._pool.fetch(f"SELECT * FROM {T}.script_profiles ORDER BY created_at")
        return [_profile(r) for r in rows]

    async def get(self, profile_id: str) -> ScriptProfile | None:
        uid = _uuid(profile_id)
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.script_profiles WHERE id=$1", uid) if uid else None
        return _profile(row) if row else None

    async def add(self, profile: ScriptProfile) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.script_profiles (id, name, description, instructions) VALUES ($1,$2,$3,$4)",
            UUID(profile.id), profile.name, profile.description, profile.instructions,
        )

    async def delete(self, profile_id: str) -> bool:
        uid = _uuid(profile_id)
        if uid is None:
            return False
        return (await self._pool.execute(f"DELETE FROM {T}.script_profiles WHERE id=$1", uid)).endswith("1")
