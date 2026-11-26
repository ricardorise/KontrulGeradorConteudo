import json

import asyncpg

from studio.scripting.application.catalog import ScriptEntry

T = "content_studio"


class PostgresScriptCatalog:
    """Leitura (sem agregado): roteiros mais recentes com assunto, busca de origem e andamento."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def list(self, limit: int) -> list[ScriptEntry]:
        rows = await self._pool.fetch(
            f"""
            SELECT s.id, s.news_item_id, n.search_id, n.title AS news_title, q.topic, s.title, s.status, s.created_at,
                   s.config, cardinality(s.extra_news_item_ids) AS extra_news,
                   (SELECT count(*) FROM {T}.script_paragraphs p WHERE p.script_id = s.id) AS paragraphs,
                   (SELECT count(*) FROM {T}.renders r WHERE r.script_id = s.id AND r.status = 'done') AS videos_done,
                   (SELECT pub.status FROM {T}.publications pub JOIN {T}.renders r2 ON r2.id = pub.render_id
                     WHERE r2.script_id = s.id ORDER BY pub.created_at DESC LIMIT 1) AS publication_status
            FROM {T}.scripts s
            JOIN {T}.news_items n ON n.id = s.news_item_id
            JOIN {T}.news_searches q ON q.id = n.search_id
            ORDER BY s.created_at DESC LIMIT $1
            """,
            limit,
        )
        entries = []
        for r in rows:
            config = json.loads(r["config"]) if r["config"] else {}
            entries.append(
                ScriptEntry(
                    script_id=r["id"], news_item_id=r["news_item_id"], search_id=r["search_id"], news_title=r["news_title"],
                    topic=r["topic"], script_title=r["title"], status=r["status"], created_at=r["created_at"],
                    paragraphs=r["paragraphs"], profile_name=config.get("profile_name"),
                    duration_minutes=config.get("duration_minutes"), presenters=tuple(config.get("presenters") or ()),
                    extra_news=r["extra_news"], videos_done=r["videos_done"], publication_status=r["publication_status"],
                )  # fmt: skip
            )
        return entries
