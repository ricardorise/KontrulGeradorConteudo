from uuid import UUID

import asyncpg

from studio.rendering.domain.render_job import RenderJob, RenderOutput
from studio.shared.domain.status import JobStatus

T = "content_studio"


def _job(r: asyncpg.Record) -> RenderJob:
    output = RenderOutput(r["output_filename"], r["output_subfolder"] or "", r["output_type"] or "output") if r["output_filename"] else None
    return RenderJob(
        id=r["id"], script_id=r["script_id"], status=JobStatus(r["status"]), background=r["background"],
        roteiro=r["roteiro"], edit_list=r["edit_list"], created_at=r["created_at"], prompt_id=r["prompt_id"],
        queued=r["queued"], output=output, error=r["error"], finished_at=r["finished_at"],
        intro_asset_id=r["intro_asset_id"], outro_asset_id=r["outro_asset_id"], stage=r["stage"],
        final_path=r["final_path"], music_asset_id=r["music_asset_id"], music_volume=r["music_volume"],
        background_asset_id=r["background_asset_id"], intro_volume=r["intro_volume"], outro_volume=r["outro_volume"],
        background_volume=r["background_volume"], normalize_vignettes=r["normalize_vignettes"], main_path=r["main_path"], music_in_video=r["music_in_video"],
        music_intro_volume=r["music_intro_volume"], music_outro_volume=r["music_outro_volume"],
    )  # fmt: skip


class PostgresRenderJobRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, job: RenderJob) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.renders (id, script_id, status, prompt_id, background, roteiro, edit_list, queued, "
            "error, created_at, finished_at, intro_asset_id, outro_asset_id, stage, music_asset_id, music_volume, background_asset_id, intro_volume, outro_volume, "
            "background_volume, normalize_vignettes, main_path, output_filename, output_subfolder, output_type, final_path, "
            "music_in_video, music_intro_volume, music_outro_volume) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29)",
            job.id, job.script_id, job.status.value, job.prompt_id, job.background, job.roteiro, job.edit_list,
            job.queued, job.error, job.created_at, job.finished_at, job.intro_asset_id, job.outro_asset_id, job.stage,
            job.music_asset_id, job.music_volume, job.background_asset_id, job.intro_volume, job.outro_volume,
            job.background_volume, job.normalize_vignettes, job.main_path,
            job.output.filename if job.output else None, job.output.subfolder if job.output else None,
            job.output.type if job.output else None, job.final_path, job.music_in_video,
            job.music_intro_volume, job.music_outro_volume,
        )  # fmt: skip

    async def save(self, job: RenderJob) -> None:
        out = job.output
        await self._pool.execute(
            f"UPDATE {T}.renders SET status=$2, prompt_id=$3, queued=$4, error=$5, finished_at=$6, "
            "output_filename=$7, output_subfolder=$8, output_type=$9, stage=$10, final_path=$11, main_path=$12 WHERE id=$1",
            job.id, job.status.value, job.prompt_id, job.queued, job.error, job.finished_at,
            out.filename if out else None, out.subfolder if out else None, out.type if out else None,
            job.stage, job.final_path, job.main_path,
        )  # fmt: skip

    async def get(self, job_id: UUID) -> RenderJob | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.renders WHERE id=$1", job_id)
        return _job(row) if row else None

    async def list_for_script(self, script_id: UUID, limit: int) -> list[RenderJob]:
        rows = await self._pool.fetch(
            f"SELECT * FROM {T}.renders WHERE script_id=$1 ORDER BY created_at DESC LIMIT $2", script_id, limit
        )
        return [_job(r) for r in rows]

    async def list_active(self) -> list[RenderJob]:
        rows = await self._pool.fetch(f"SELECT * FROM {T}.renders WHERE status IN ('pending','running')")
        return [_job(r) for r in rows]
