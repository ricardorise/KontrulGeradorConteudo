from uuid import UUID

import asyncpg

from studio.rendering.domain.asset import AssetKind, RenderAsset

T = "content_studio"


def _asset(r: asyncpg.Record) -> RenderAsset:
    return RenderAsset(
        id=r["id"], kind=AssetKind(r["kind"]), filename=r["filename"], stored_name=r["stored_name"],
        size_bytes=r["size_bytes"], duration=r["duration"], width=r["width"], height=r["height"], fps=r["fps"],
        has_audio=r["has_audio"], created_at=r["created_at"], mean_volume_db=r["mean_volume_db"],
    )  # fmt: skip


class PostgresRenderAssetRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, a: RenderAsset) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.render_assets (id, kind, filename, stored_name, size_bytes, duration, width, height, "
            "fps, has_audio, created_at, mean_volume_db) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
            a.id, a.kind.value, a.filename, a.stored_name, a.size_bytes, a.duration, a.width, a.height, a.fps,
            a.has_audio, a.created_at, a.mean_volume_db,
        )  # fmt: skip

    async def get(self, asset_id: UUID) -> RenderAsset | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.render_assets WHERE id=$1", asset_id)
        return _asset(row) if row else None

    async def list(self, kind: AssetKind | None) -> list[RenderAsset]:
        rows = await self._pool.fetch(
            f"SELECT * FROM {T}.render_assets WHERE ($1::text IS NULL OR kind=$1) ORDER BY created_at DESC",
            kind.value if kind else None,
        )
        return [_asset(r) for r in rows]

    async def delete(self, asset_id: UUID) -> None:
        await self._pool.execute(f"DELETE FROM {T}.render_assets WHERE id=$1", asset_id)
