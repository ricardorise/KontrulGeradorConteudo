import json
from uuid import UUID

import asyncpg

from studio.discovery.domain.news_search import NewsItem, NewsSearch
from studio.shared.domain.status import JobStatus

T = "content_studio"


def _item(row: asyncpg.Record) -> NewsItem:
    return NewsItem(
        id=row["id"], position=row["position"], title=row["title"], summary=row["summary"],
        details=row["details"], source_url=row["source_url"], published_at=row["published_at"],
        radar=json.loads(row["radar"]) if isinstance(row["radar"], str) else (row["radar"] or {}),
    )  # fmt: skip


def _search(row: asyncpg.Record, items: list[NewsItem]) -> NewsSearch:
    return NewsSearch(
        id=row["id"], topic=row["topic"], status=JobStatus(row["status"]), created_at=row["created_at"],
        error=row["error"], finished_at=row["finished_at"], instructions=row["instructions"], items=items,
        report_context=json.loads(row["report_context"]) if isinstance(row["report_context"], str) else (row["report_context"] or {}),
    )  # fmt: skip


class PostgresNewsSearchRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, search: NewsSearch) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.news_searches (id, topic, status, error, created_at, finished_at, instructions, report_context) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)",
            search.id, search.topic, search.status.value, search.error, search.created_at, search.finished_at,
            search.instructions, json.dumps(search.report_context),
        )  # fmt: skip

    async def save(self, search: NewsSearch) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"UPDATE {T}.news_searches SET status=$2, error=$3, finished_at=$4, report_context=$5::jsonb WHERE id=$1",
                search.id, search.status.value, search.error, search.finished_at, json.dumps(search.report_context),
            )  # fmt: skip
            if search.items:
                await conn.execute(f"DELETE FROM {T}.news_items WHERE search_id=$1", search.id)
                await conn.executemany(
                    f"INSERT INTO {T}.news_items (id, search_id, position, title, summary, details, "
                    "source_url, published_at, radar) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)",
                    [
                        (i.id, search.id, i.position, i.title, i.summary, i.details, i.source_url, i.published_at, json.dumps(i.radar))
                        for i in search.items
                    ],
                )

    async def get(self, search_id: UUID) -> NewsSearch | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.news_searches WHERE id=$1", search_id)
        if row is None:
            return None
        items = await self._pool.fetch(
            f"SELECT * FROM {T}.news_items WHERE search_id=$1 ORDER BY position", search_id
        )
        return _search(row, [_item(r) for r in items])

    async def list_recent(self, limit: int) -> list[NewsSearch]:
        rows = await self._pool.fetch(f"SELECT * FROM {T}.news_searches ORDER BY created_at DESC LIMIT $1", limit)
        item_rows = await self._pool.fetch(
            f"SELECT * FROM {T}.news_items WHERE search_id = ANY($1::uuid[]) ORDER BY position",
            [r["id"] for r in rows],
        )
        grouped: dict[UUID, list[NewsItem]] = {}
        for r in item_rows:
            grouped.setdefault(r["search_id"], []).append(_item(r))
        return [_search(r, grouped.get(r["id"], [])) for r in rows]

    async def find_item(self, item_id: UUID) -> tuple[NewsSearch, NewsItem] | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.news_items WHERE id=$1", item_id)
        if row is None:
            return None
        search = await self._pool.fetchrow(f"SELECT * FROM {T}.news_searches WHERE id=$1", row["search_id"])
        item = _item(row)
        return _search(search, [item]), item

    async def fail_interrupted(self) -> int:
        result = await self._pool.execute(
            f"UPDATE {T}.news_searches SET status='failed', finished_at=now(), "
            "error='Interrompido por reinício do servidor.' WHERE status IN ('pending','running')"
        )
        return int(result.split()[-1])
