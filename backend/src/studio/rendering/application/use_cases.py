import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from studio.rendering.application.ports import (
    MediaError,
    MediaProbe,
    MediaStore,
    OutputStream,
    RenderError,
    RenderSubmission,
    ScriptSourceReader,
    VideoComposer,
    VideoRenderer,
)
from studio.rendering.domain.asset import AssetKind, RenderAsset
from studio.rendering.domain.edit_plan import EditPlan, build_plan
from studio.rendering.domain.render_job import RenderJob
from studio.rendering.domain.repository import RenderAssetRepository, RenderJobRepository
from studio.shared.application.ports import BackgroundRunner
from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import InvalidInput, NotFound
from studio.shared.domain.status import JobStatus

log = logging.getLogger(__name__)
LOST_TOLERANCE = 6


@dataclass(frozen=True)
class RenderPreview:
    background: str
    plan: EditPlan
    music_volume: float = 0.08
    background_volume_supported: bool = False


class PreviewRender:
    def __init__(self, scripts: ScriptSourceReader, renderer: VideoRenderer):
        self._scripts, self._renderer = scripts, renderer

    async def __call__(self, script_id: UUID, background: str | None = None) -> RenderPreview:
        script = await self._scripts.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        return RenderPreview(
            (background or "").strip() or self._renderer.default_background(),
            build_plan(script),
            self._renderer.default_music_volume(),
            self._renderer.supports_background_volume(),
        )


class RenderMonitor:
    """Acompanha o prompt no ComfyUI (GET /history) até concluir ou falhar."""

    def __init__(
        self,
        jobs: RenderJobRepository,
        renderer: VideoRenderer,
        poll_interval_s: float = 4,
        max_wait_s: float = 4 * 3600,
        finisher: "RenderFinisher | None" = None,
    ):
        self._jobs, self._renderer, self._finisher = jobs, renderer, finisher
        self._interval, self._max_wait = poll_interval_s, max_wait_s

    async def watch(self, job_id: UUID) -> None:
        waited, failures, lost = 0.0, 0, 0
        while waited <= self._max_wait:
            job = await self._jobs.get(job_id)
            if job is None or job.status.is_terminal or not job.prompt_id:
                return
            try:
                progress = await self._renderer.progress(job.prompt_id)
                failures = 0
            except RenderError as exc:
                failures += 1
                log.warning("render %s: consulta ao ComfyUI falhou (%d): %s", job_id, failures, exc)
                if failures >= 20:
                    job.fail(f"Perdi a conexão com o ComfyUI: {exc}")
                    await self._jobs.save(job)
                    return
                progress = None
            lost = lost + 1 if progress is not None and progress.state == "lost" else 0
            if lost >= LOST_TOLERANCE:  # tolera a janela logo após o envio, antes de aparecer na fila
                job.fail("O ComfyUI não tem mais este envio (fila reiniciada ou limpa?). Envie novamente.")
                await self._jobs.save(job)
                return
            if progress is not None and progress.state != "lost":
                if progress.state == "done" and progress.output:
                    if job.has_vignettes and self._finisher:
                        job.begin_composing(progress.output)
                        await self._jobs.save(job)
                        await self._finisher.finish(job)  # monta abertura + vídeo + final (ou falha o job)
                    else:
                        job.complete(progress.output)
                elif progress.state == "failed":
                    job.fail(progress.error or "A execução falhou no ComfyUI.")
                elif job.queued != (progress.state == "queued"):
                    job.set_queued(progress.state == "queued")
                else:
                    await asyncio.sleep(self._interval)
                    waited += self._interval
                    continue
                await self._jobs.save(job)
                if job.status.is_terminal:
                    return
            await asyncio.sleep(self._interval)
            waited += self._interval
        job = await self._jobs.get(job_id)
        if job and not job.status.is_terminal:
            job.fail("Tempo máximo de espera excedido.")
            await self._jobs.save(job)


MAX_GAIN = 1.5  # 150%


def _check_gain(value: float, what: str, maximum: float = MAX_GAIN) -> float:
    if not 0 <= value <= maximum:
        raise InvalidInput(f"O volume {what} deve ficar entre 0 e {round(maximum * 100)}%.")
    return value


class StartRender:
    def __init__(
        self, jobs: RenderJobRepository, preview: PreviewRender, renderer: VideoRenderer, runner: BackgroundRunner,
        monitor: RenderMonitor, assets: RenderAssetRepository | None = None, store: MediaStore | None = None,
    ):  # fmt: skip
        self._jobs, self._preview, self._renderer = jobs, preview, renderer
        self._runner, self._monitor, self._assets, self._store = runner, monitor, assets, store

    async def _vignette(self, asset_id: UUID | None, kind: AssetKind) -> RenderAsset | None:
        if asset_id is None:
            return None
        asset = await self._assets.get(asset_id) if self._assets else None
        if asset is None or asset.kind is not kind:
            raise InvalidInput(f"Vinheta de {kind.value} não encontrada. Envie o vídeo novamente.")
        return asset

    async def __call__(
        self, script_id: UUID, background: str | None = None, intro_id: UUID | None = None, outro_id: UUID | None = None,
        music_id: UUID | None = None, music_volume: float | None = None, background_id: UUID | None = None,
        *, intro_volume: float = 1.0, outro_volume: float = 1.0, background_volume: float = 0.0,
        normalize_vignettes: bool = True, music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> RenderJob:  # fmt: skip
        preview = await self._preview(script_id, background)
        intro = await self._vignette(intro_id, AssetKind.INTRO)
        outro = await self._vignette(outro_id, AssetKind.OUTRO)
        music = await self._vignette(music_id, AssetKind.MUSIC)
        background = await self._vignette(background_id, AssetKind.BACKGROUND)
        background_path = (
            f"papotechcast/fundo-{background.id.hex[:8]}{Path(background.stored_name).suffix}" if background else preview.background
        )
        volume = preview.music_volume if music_volume is None else music_volume
        _check_gain(volume, "da trilha", 1.0)
        for what, level in (("da trilha na abertura", music_intro_volume), ("da trilha no final", music_outro_volume)):
            if level is not None:
                _check_gain(level, what, 1.0)
        _check_gain(intro_volume, "da abertura")
        _check_gain(outro_volume, "do final")
        _check_gain(background_volume, "do áudio do background")
        if background_volume > 0 and not preview.background_volume_supported:
            raise InvalidInput("O workflow atual do ComfyUI não tem o volume do áudio do background.")
        if preview.plan.problems:
            raise InvalidInput("Não dá para enviar ainda:\n- " + "\n- ".join(preview.plan.problems))
        job = RenderJob.create(
            script_id, background_path, preview.plan.roteiro, preview.plan.edit_list,
            intro.id if intro else None, outro.id if outro else None,
            music.id if music else None, volume if music else None, background.id if background else None,
            intro_volume, outro_volume, background_volume, normalize_vignettes,
            bool(music and not (intro or outro)),  # sem vinhetas a trilha vai dentro do vídeo do ComfyUI
            music_intro_volume if music and intro else None, music_outro_volume if music and outro else None,
        )  # fmt: skip
        await self._jobs.add(job)
        try:
            if background and self._store:  # vídeo grande: só sobe se o ComfyUI ainda não tiver o mesmo arquivo
                await self._renderer.upload_input(
                    self._store.asset_path(background.stored_name), "papotechcast", background_path.split("/", 1)[1]
                )
            track = None
            # Com vinhetas, a trilha é misturada na montagem final (desde a abertura), não dentro do vídeo do ComfyUI.
            if music and self._store and not (intro or outro):  # a trilha precisa estar na pasta input do ComfyUI antes do envio
                suffix = Path(music.stored_name).suffix
                track = await self._renderer.upload_input(
                    self._store.asset_path(music.stored_name), "papotechcast", f"trilha-{music.id.hex[:8]}{suffix}"
                )
            prompt_id = await self._renderer.submit(
                RenderSubmission(
                    job.roteiro, background_path, job.edit_list, track, volume if track else None,
                    background_volume if preview.background_volume_supported else None,
                )
            )
        except RenderError as exc:
            job.fail(str(exc))
            await self._jobs.save(job)
            return job
        job.submitted(prompt_id)
        await self._jobs.save(job)
        self._runner.submit(self._monitor.watch(job.id))
        return job


class GetRender:
    def __init__(self, jobs: RenderJobRepository):
        self._jobs = jobs

    async def __call__(self, job_id: UUID) -> RenderJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("Renderização não encontrada.")
        return job


class ListRenders:
    def __init__(self, jobs: RenderJobRepository):
        self._jobs = jobs

    async def __call__(self, script_id: UUID, limit: int = 10) -> list[RenderJob]:
        return await self._jobs.list_for_script(script_id, max(1, min(limit, 50)))


@dataclass
class VideoSource:
    """Vídeo pronto: arquivo local (já montado com as vinhetas) ou fluxo repassado do ComfyUI."""

    path: Path | None = None
    stream: OutputStream | None = None


class OpenRenderVideo:
    def __init__(self, jobs: RenderJobRepository, renderer: VideoRenderer):
        self._jobs, self._renderer = jobs, renderer

    async def __call__(self, job_id: UUID) -> VideoSource:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("Renderização não encontrada.")
        if job.status is not JobStatus.DONE or job.output is None:
            raise InvalidInput("O vídeo ainda não está pronto.")
        if job.final_path and Path(job.final_path).is_file():
            return VideoSource(path=Path(job.final_path))
        try:
            return VideoSource(stream=await self._renderer.open_output(job.output))
        except RenderError as exc:
            raise NotFound(str(exc)) from exc


class RenderFinisher:
    """Baixa o MP4 da narração e monta: abertura → vídeo com a fala → final.

    Como a abertura vem antes do vídeo principal, a fala só começa depois da vinheta; cada vinheta
    mantém o próprio áudio.
    """

    def __init__(
        self, jobs: RenderJobRepository, assets: RenderAssetRepository, renderer: VideoRenderer,
        store: MediaStore, composer: VideoComposer,
    ):  # fmt: skip
        self._jobs, self._assets, self._renderer = jobs, assets, renderer
        self._store, self._composer = store, composer

    async def finish(self, job: RenderJob) -> None:
        try:
            intro = await self._asset_path(job.intro_asset_id)
            outro = await self._asset_path(job.outro_asset_id)
            main = Path(job.main_path) if job.main_path and Path(job.main_path).is_file() else None
            if main is None:  # guarda o vídeo da fala: permite remixar sem refazer o ComfyUI
                main = self._store.main_path(job.id)
                stream = await self._renderer.open_output(job.output)  # type: ignore[arg-type]
                await self._store.write_stream(main, stream.chunks)
                job.main_path = str(main)
            dest = self._store.result_path(job.id)
            music = None if job.music_is_baked else await self._asset_path(job.music_asset_id)
            await self._composer.compose(
                main, intro, outro, dest, music, job.music_volume if job.music_volume is not None else 0.08,
                job.intro_volume, job.outro_volume, job.normalize_vignettes,
                job.music_intro_volume, job.music_outro_volume,
            )
            job.final_path = str(dest)
            job.complete(job.output)  # type: ignore[arg-type]
        except (MediaError, RenderError) as exc:
            log.warning("render %s: montagem das vinhetas falhou: %s", job.id, exc)
            job.fail(f"O vídeo da narração ficou pronto no ComfyUI, mas a montagem com as vinhetas falhou: {exc}")
        except Exception:
            log.exception("render %s: erro inesperado na montagem", job.id)
            job.fail("Erro inesperado ao montar o vídeo com as vinhetas.")
        await self._jobs.save(job)

    async def _asset_path(self, asset_id: UUID | None) -> Path | None:
        if asset_id is None:
            return None
        asset = await self._assets.get(asset_id)
        if asset is None:
            raise MediaError("a vinheta escolhida foi apagada")
        return self._store.asset_path(asset.stored_name)


class RemixRender:
    """Refaz só a montagem final de um vídeo já pronto (novas vinhetas/volumes) sem rodar o ComfyUI de novo."""

    def __init__(self, jobs: RenderJobRepository, assets: RenderAssetRepository, runner: BackgroundRunner, finisher: RenderFinisher):
        self._jobs, self._assets, self._runner, self._finisher = jobs, assets, runner, finisher

    async def _asset(self, asset_id: UUID | None, kind: AssetKind) -> UUID | None:
        if asset_id is None:
            return None
        asset = await self._assets.get(asset_id)
        if asset is None or asset.kind is not kind:
            raise InvalidInput(f"Vinheta de {kind.value} não encontrada. Envie o vídeo novamente.")
        return asset.id

    async def __call__(
        self, job_id: UUID, intro_id: UUID | None, outro_id: UUID | None, music_id: UUID | None,
        music_volume: float | None, intro_volume: float = 1.0, outro_volume: float = 1.0, normalize: bool = True,
        music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> RenderJob:  # fmt: skip
        source = await self._jobs.get(job_id)
        if source is None:
            raise NotFound("Renderização não encontrada.")
        if not source.can_remix:
            raise InvalidInput("Só dá para remixar um vídeo que já ficou pronto.")
        intro = await self._asset(intro_id, AssetKind.INTRO)
        outro = await self._asset(outro_id, AssetKind.OUTRO)
        music = await self._asset(music_id, AssetKind.MUSIC)
        if source.music_is_baked:
            music = None  # a trilha já está dentro do vídeo da fala; não dá para trocar sem refazer o envio
        if not (intro or outro or music or source.music_is_baked):
            raise InvalidInput("Escolha ao menos uma vinheta ou um áudio de fundo para remixar.")
        _check_gain(intro_volume, "da abertura")
        _check_gain(outro_volume, "do final")
        if music_volume is not None:
            _check_gain(music_volume, "da trilha", 1.0)
        for what, level in (("da trilha na abertura", music_intro_volume), ("da trilha no final", music_outro_volume)):
            if level is not None:
                _check_gain(level, what, 1.0)
        job = source.remix(
            intro, outro, music, music_volume, intro_volume, outro_volume, normalize,
            music_intro_volume if intro else None, music_outro_volume if outro else None,
        )  # fmt: skip
        await self._jobs.add(job)
        self._runner.submit(self._finisher.finish(job))
        return job


# ---- vinhetas (upload) ----
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac"}
MAX_ASSET_SECONDS = 600  # vinhetas
MAX_BACKGROUND_SECONDS = 6 * 3600
MAX_MUSIC_SECONDS = 3 * 3600


class UploadRenderAsset:
    def __init__(self, assets: RenderAssetRepository, store: MediaStore, probe: MediaProbe, max_bytes: int):
        self._assets, self._store, self._probe, self._max_bytes = assets, store, probe, max_bytes

    async def __call__(self, kind: str, filename: str, chunks: AsyncIterator[bytes]) -> RenderAsset:
        try:
            asset_kind = AssetKind(kind)
        except ValueError:
            raise InvalidInput("Tipo inválido (use abertura, final, background ou trilha).") from None
        is_music = asset_kind is AssetKind.MUSIC
        suffix = Path(filename).suffix.lower()
        allowed = AUDIO_SUFFIXES | VIDEO_SUFFIXES if is_music else VIDEO_SUFFIXES
        if suffix not in allowed:
            wanted = "MP3, WAV, M4A, AAC, OGG, OPUS ou FLAC" if is_music else "MP4, MOV, M4V, WEBM ou MKV"
            raise InvalidInput(f"Formato não suportado ({suffix or 'sem extensão'}). Use {wanted}.")
        asset_id = uuid4()
        stored = f"{asset_id}{suffix}"
        try:
            size = await self._store.save_upload(stored, chunks, self._max_bytes)
            path = self._store.asset_path(stored)
            try:
                info = await self._probe.probe(path)
            except MediaError as exc:
                raise InvalidInput(f"Não consegui ler o vídeo: {exc}") from exc
            if is_music:
                if not info.has_audio or info.duration <= 0:
                    raise InvalidInput("O arquivo não tem áudio.")
                if info.duration > MAX_MUSIC_SECONDS:
                    raise InvalidInput("A trilha deve ter até 3 horas.")
            else:
                if not info.has_video or info.duration <= 0:
                    raise InvalidInput("O arquivo não tem vídeo.")
                limit = MAX_BACKGROUND_SECONDS if asset_kind is AssetKind.BACKGROUND else MAX_ASSET_SECONDS
                if info.duration > limit:
                    what = "O background" if asset_kind is AssetKind.BACKGROUND else "A vinheta"
                    raise InvalidInput(f"{what} deve ter até {limit // 3600 if limit >= 3600 else limit // 60} {'horas' if limit >= 3600 else 'minutos'}.")
        except Exception:
            self._store.remove(self._store.asset_path(stored))
            raise
        level = None
        if info.has_audio and asset_kind is not AssetKind.BACKGROUND and info.duration <= MAX_ASSET_SECONDS:
            level = await self._probe.mean_volume(self._store.asset_path(stored))  # só vinhetas curtas: é rápido
        asset = RenderAsset(
            asset_id, asset_kind, Path(filename).name[:200], stored, size, info.duration, info.width, info.height,
            info.fps, info.has_audio, utcnow(), level,
        )  # fmt: skip
        await self._assets.add(asset)
        return asset


class ListRenderAssets:
    def __init__(self, assets: RenderAssetRepository):
        self._assets = assets

    async def __call__(self, kind: str | None = None) -> list[RenderAsset]:
        try:
            return await self._assets.list(AssetKind(kind) if kind else None)
        except ValueError:
            raise InvalidInput("Tipo de vinheta inválido.") from None


class DeleteRenderAsset:
    def __init__(self, assets: RenderAssetRepository, store: MediaStore):
        self._assets, self._store = assets, store

    async def __call__(self, asset_id: UUID) -> None:
        asset = await self._assets.get(asset_id)
        if asset is None:
            raise NotFound("Vinheta não encontrada.")
        await self._assets.delete(asset_id)
        self._store.remove(self._store.asset_path(asset.stored_name))


async def resume_active(jobs: RenderJobRepository, runner: BackgroundRunner, monitor: RenderMonitor) -> int:
    """Após reinício: retoma o acompanhamento dos envios já aceitos pelo ComfyUI; falha os que nem chegaram a ser enviados."""
    resumed = 0
    for job in await jobs.list_active():
        if job.prompt_id:
            runner.submit(monitor.watch(job.id))
            resumed += 1
        else:
            job.fail("Interrompido antes do envio ao ComfyUI.")
            await jobs.save(job)
    return resumed
