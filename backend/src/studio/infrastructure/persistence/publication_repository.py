import json
from uuid import UUID

import asyncpg

from studio.publishing.domain.publication import Link, Publication, PublicationStatus

T = "content_studio"


def _publication(r: asyncpg.Record) -> Publication:
    return Publication(
        id=r["id"], render_id=r["render_id"], script_id=r["script_id"], status=PublicationStatus(r["status"]),
        created_at=r["created_at"], updated_at=r["updated_at"], title=r["title"],
        title_alternatives=json.loads(r["title_alternatives"]), description=r["description"], tags=json.loads(r["tags"]),
        links=[Link(**l) for l in json.loads(r["links"])], privacy=r["privacy"], category_id=r["category_id"],
        language=r["language"], notify_subscribers=r["notify_subscribers"], rationale=r["rationale"], error=r["error"],
        error_stage=r["error_stage"], video_id=r["video_id"], video_url=r["video_url"], published_at=r["published_at"],
    )  # fmt: skip


def _values(p: Publication) -> tuple:
    return (
        p.id, p.render_id, p.script_id, p.status.value, p.title, json.dumps(p.title_alternatives, ensure_ascii=False),
        p.description, json.dumps(p.tags, ensure_ascii=False),
        json.dumps([{"label": l.label, "url": l.url, "kind": l.kind} for l in p.links], ensure_ascii=False),
        p.privacy, p.category_id, p.language, p.notify_subscribers, p.rationale, p.error, p.error_stage,
        p.video_id, p.video_url, p.created_at, p.updated_at, p.published_at,
    )  # fmt: skip


class PostgresPublicationRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, p: Publication) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.publications (id, render_id, script_id, status, title, title_alternatives, description, tags, "
            "links, privacy, category_id, language, notify_subscribers, rationale, error, error_stage, video_id, video_url, "
            "created_at, updated_at, published_at) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8::jsonb,$9::jsonb,$10,$11,$12,$13,"
            "$14,$15,$16,$17,$18,$19,$20,$21)",
            *_values(p),
        )

    async def save(self, p: Publication) -> None:
        await self._pool.execute(
            f"UPDATE {T}.publications SET render_id=$2, script_id=$3, status=$4, title=$5, title_alternatives=$6::jsonb, description=$7, tags=$8::jsonb, "
            "links=$9::jsonb, privacy=$10, category_id=$11, language=$12, notify_subscribers=$13, rationale=$14, error=$15, "
            "error_stage=$16, video_id=$17, video_url=$18, created_at=$19, updated_at=$20, published_at=$21 WHERE id=$1",
            *_values(p),
        )

    async def get(self, publication_id: UUID) -> Publication | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.publications WHERE id=$1", publication_id)
        return _publication(row) if row else None

    async def latest_for_render(self, render_id: UUID) -> Publication | None:
        row = await self._pool.fetchrow(
            f"SELECT * FROM {T}.publications WHERE render_id=$1 ORDER BY created_at DESC LIMIT 1", render_id
        )
        return _publication(row) if row else None

    async def fail_interrupted(self) -> int:
        """Reinício do backend: geração/revisão interrompida => falha; envio interrompido => volta a 'ready' com aviso
        (pode ter sido enviado: o editor confere no YouTube Studio antes de tentar de novo)."""
        gen = await self._pool.execute(
            f"UPDATE {T}.publications SET status='failed', error='Interrompido por reinício do servidor.', "
            "error_stage='generation' WHERE status='drafting' AND title=''"
        )
        rev = await self._pool.execute(
            f"UPDATE {T}.publications SET status='ready', error='Revisão interrompida por reinício do servidor.', "
            "error_stage='revision' WHERE status='drafting'"
        )
        pub = await self._pool.execute(
            f"UPDATE {T}.publications SET status='ready', error_stage='publish', error='O envio foi interrompido por reinício "
            "do servidor e pode ter chegado ao YouTube: confira no YouTube Studio antes de publicar de novo.' "
            "WHERE status='publishing'"
        )
        return sum(int(x.split()[-1]) for x in (gen, rev, pub))
