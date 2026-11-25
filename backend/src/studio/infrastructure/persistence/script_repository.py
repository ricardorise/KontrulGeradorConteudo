from uuid import UUID

import asyncpg

from studio.scripting.domain.script import BrollSuggestion, Cut, Excerpt, Paragraph, Script
from studio.shared.domain.status import JobStatus

T = "content_studio"


class PostgresScriptRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, script: Script) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.scripts (id, news_item_id, title, status, error, broll_status, broll_error, "
            "created_at, finished_at, instructions) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
            script.id, script.news_item_id, script.title, script.status.value, script.error,
            script.broll_status.value, script.broll_error, script.created_at, script.finished_at, script.instructions,
        )  # fmt: skip

    async def save(self, script: Script) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"UPDATE {T}.scripts SET title=$2, status=$3, error=$4, broll_status=$5, broll_error=$6, "
                "finished_at=$7 WHERE id=$1",
                script.id, script.title, script.status.value, script.error,
                script.broll_status.value, script.broll_error, script.finished_at,
            )  # fmt: skip
            if not script.paragraphs:
                return
            await conn.executemany(
                f"INSERT INTO {T}.script_paragraphs (id, script_id, position, text) VALUES ($1,$2,$3,$4) "
                "ON CONFLICT (id) DO UPDATE SET position=EXCLUDED.position, text=EXCLUDED.text",
                [(p.id, script.id, p.position, p.text) for p in script.paragraphs],
            )
            await conn.execute(
                f"DELETE FROM {T}.broll_suggestions WHERE paragraph_id = ANY($1::uuid[])",
                [p.id for p in script.paragraphs],
            )
            await conn.executemany(
                f"INSERT INTO {T}.broll_suggestions (id, paragraph_id, position, video_url, video_id, "
                "start_seconds, title, description, justification) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                [
                    (b.id, p.id, i, b.video_url, b.video_id, b.start_seconds, b.title, b.description, b.justification)
                    for p in script.paragraphs
                    for i, b in enumerate(p.broll)
                ],
            )

    async def get(self, script_id: UUID) -> Script | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.scripts WHERE id=$1", script_id)
        return await self._hydrate(row) if row else None

    async def get_latest_for_news_item(self, news_item_id: UUID) -> Script | None:
        row = await self._pool.fetchrow(
            f"SELECT * FROM {T}.scripts WHERE news_item_id=$1 ORDER BY created_at DESC LIMIT 1", news_item_id
        )
        return await self._hydrate(row) if row else None

    async def add_cut(self, script_id: UUID, cut: Cut) -> None:
        ex = cut.excerpt
        async with self._pool.acquire() as conn, conn.transaction():
            if ex:
                await conn.execute(
                    f"INSERT INTO {T}.paragraph_excerpts (id, paragraph_id, start_offset, end_offset, text) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    ex.id, ex.paragraph_id, ex.start, ex.end, ex.text,
                )
            await conn.execute(
                f"INSERT INTO {T}.script_cuts (id, script_id, paragraph_id, video_id, video_url, video_title, "
                "start_seconds, end_seconds, created_at, excerpt_id) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                cut.id, script_id, cut.paragraph_id, cut.video_id, cut.video_url, cut.video_title,
                cut.start_seconds, cut.end_seconds, cut.created_at, ex.id if ex else None,
            )  # fmt: skip

    async def set_cut_excerpt(self, cut: Cut) -> None:
        ex = cut.excerpt
        async with self._pool.acquire() as conn, conn.transaction():
            old = await conn.fetchval(f"SELECT excerpt_id FROM {T}.script_cuts WHERE id=$1", cut.id)
            await conn.execute(f"UPDATE {T}.script_cuts SET excerpt_id=NULL WHERE id=$1", cut.id)
            if old:
                await conn.execute(f"DELETE FROM {T}.paragraph_excerpts WHERE id=$1", old)
            if ex:
                await conn.execute(
                    f"INSERT INTO {T}.paragraph_excerpts (id, paragraph_id, start_offset, end_offset, text) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    ex.id, ex.paragraph_id, ex.start, ex.end, ex.text,
                )
                await conn.execute(f"UPDATE {T}.script_cuts SET excerpt_id=$2 WHERE id=$1", cut.id, ex.id)

    async def delete_cut(self, cut_id: UUID) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            excerpt_id = await conn.fetchval(f"SELECT excerpt_id FROM {T}.script_cuts WHERE id=$1", cut_id)
            await conn.execute(f"DELETE FROM {T}.script_cuts WHERE id=$1", cut_id)
            if excerpt_id:  # o trecho só existe por causa do corte
                await conn.execute(f"DELETE FROM {T}.paragraph_excerpts WHERE id=$1", excerpt_id)

    async def fail_interrupted(self) -> int:
        scripts = await self._pool.execute(
            f"UPDATE {T}.scripts SET status='failed', finished_at=now(), "
            "error='Interrompido por reinício do servidor.' WHERE status IN ('pending','running')"
        )
        broll = await self._pool.execute(
            f"UPDATE {T}.scripts SET broll_status='failed', "
            "broll_error='Interrompido por reinício do servidor.' WHERE broll_status='running'"
        )
        return int(scripts.split()[-1]) + int(broll.split()[-1])

    async def _hydrate(self, row: asyncpg.Record) -> Script:
        paragraph_rows = await self._pool.fetch(
            f"SELECT * FROM {T}.script_paragraphs WHERE script_id=$1 ORDER BY position", row["id"]
        )
        broll_rows = await self._pool.fetch(
            f"SELECT * FROM {T}.broll_suggestions WHERE paragraph_id = ANY($1::uuid[]) ORDER BY position",
            [p["id"] for p in paragraph_rows],
        )
        by_paragraph: dict[UUID, list[BrollSuggestion]] = {}
        for b in broll_rows:
            by_paragraph.setdefault(b["paragraph_id"], []).append(
                BrollSuggestion(
                    id=b["id"], video_url=b["video_url"], video_id=b["video_id"],
                    description=b["description"], start_seconds=b["start_seconds"],
                    title=b["title"], justification=b["justification"],
                )  # fmt: skip
            )
        cut_rows = await self._pool.fetch(
            f"SELECT c.*, e.start_offset AS ex_start, e.end_offset AS ex_end, e.text AS ex_text "
            f"FROM {T}.script_cuts c LEFT JOIN {T}.paragraph_excerpts e ON e.id = c.excerpt_id "
            "WHERE c.script_id=$1 ORDER BY c.created_at",
            row["id"],
        )
        return Script(
            id=row["id"], news_item_id=row["news_item_id"], status=JobStatus(row["status"]),
            created_at=row["created_at"], broll_status=JobStatus(row["broll_status"]), title=row["title"],
            error=row["error"], broll_error=row["broll_error"], finished_at=row["finished_at"],
            instructions=row["instructions"],
            paragraphs=[
                Paragraph(id=p["id"], position=p["position"], text=p["text"], broll=by_paragraph.get(p["id"], []))
                for p in paragraph_rows
            ],
            cuts=[
                Cut(
                    id=c["id"], paragraph_id=c["paragraph_id"], video_id=c["video_id"], video_url=c["video_url"],
                    start_seconds=c["start_seconds"], end_seconds=c["end_seconds"], created_at=c["created_at"],
                    video_title=c["video_title"],
                    excerpt=Excerpt(c["excerpt_id"], c["paragraph_id"], c["ex_start"], c["ex_end"], c["ex_text"])
                    if c["excerpt_id"]
                    else None,
                )  # fmt: skip
                for c in cut_rows
            ],
        )  # fmt: skip
