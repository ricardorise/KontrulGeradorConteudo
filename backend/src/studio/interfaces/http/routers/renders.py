from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import use_cases
from studio.interfaces.http.schemas import RenderAssetOut, RenderIn, RenderOut, RenderPreviewOut, RenderRemixIn

router = APIRouter(tags=["renders"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.get("/scripts/{script_id}/render-preview", response_model=RenderPreviewOut)
async def preview(script_id: UUID, uc: UC, background: str | None = None) -> RenderPreviewOut:
    """O que seria enviado ao ComfyUI (roteiro, background, lista de edição) e o que impede o envio."""
    return RenderPreviewOut.of(await uc.preview_render(script_id, background))


@router.post("/scripts/{script_id}/renders", response_model=RenderOut, status_code=202)
async def start_render(script_id: UUID, uc: UC, body: RenderIn | None = None) -> RenderOut:
    return RenderOut.of(
        await uc.start_render(
            script_id, body.background if body else None,
            body.intro_asset_id if body else None, body.outro_asset_id if body else None,
            body.music_asset_id if body else None, body.music_volume if body else None,
            body.background_asset_id if body else None,
            intro_volume=body.intro_volume if body else 1.0, outro_volume=body.outro_volume if body else 1.0,
            background_volume=body.background_volume if body else 0.0,
            normalize_vignettes=body.normalize_vignettes if body else True,
            music_intro_volume=body.music_intro_volume if body else None,
            music_outro_volume=body.music_outro_volume if body else None,
            narration=body.narration.to_domain() if body and body.narration else None,
        )
    )  # fmt: skip


@router.get("/scripts/{script_id}/renders", response_model=list[RenderOut])
async def list_renders(script_id: UUID, uc: UC, limit: int = Query(10, ge=1, le=50)) -> list[RenderOut]:
    return [RenderOut.of(j) for j in await uc.list_renders(script_id, limit)]


@router.post("/renders/{render_id}/remix", response_model=RenderOut, status_code=202)
async def remix(render_id: UUID, body: RenderRemixIn, uc: UC) -> RenderOut:
    """Refaz só a montagem final (vinhetas, volumes, trilha) reaproveitando o vídeo da fala; não roda o ComfyUI."""
    return RenderOut.of(
        await uc.remix_render(
            render_id, body.intro_asset_id, body.outro_asset_id, body.music_asset_id, body.music_volume,
            body.intro_volume, body.outro_volume, body.normalize_vignettes,
            body.music_intro_volume, body.music_outro_volume,
        )
    )  # fmt: skip


@router.get("/renders/{render_id}", response_model=RenderOut)
async def get_render(render_id: UUID, uc: UC) -> RenderOut:
    return RenderOut.of(await uc.get_render(render_id))


@router.get("/renders/{render_id}/video")
async def render_video(render_id: UUID, uc: UC, download: bool = False) -> StreamingResponse:
    """Repassa o MP4 do ComfyUI (GET /view) para o navegador, sem expor o ComfyUI."""
    job = await uc.get_render(render_id)
    source = await uc.open_render_video(render_id)
    disposition = "attachment" if download else "inline"
    if source.path is not None:  # montado com as vinhetas: arquivo local (aceita Range, o player consegue avançar)
        return FileResponse(source.path, media_type="video/mp4", filename=job.output.filename, content_disposition_type=disposition)
    stream = source.stream
    headers = {"Content-Disposition": f'{disposition}; filename="{job.output.filename}"'}
    if stream.content_length is not None:
        headers["Content-Length"] = str(stream.content_length)
    return StreamingResponse(stream.chunks, media_type="video/mp4", headers=headers)


@router.post("/render-assets", response_model=RenderAssetOut, status_code=201)
async def upload_asset(uc: UC, kind: str = Form(...), file: UploadFile = File(...)) -> RenderAssetOut:
    """Envia uma vinheta (kind = intro | outro) para ser usada na montagem do vídeo final."""

    async def chunks():
        while block := await file.read(1 << 20):
            yield block

    return RenderAssetOut.of(await uc.upload_render_asset(kind, file.filename or "video.mp4", chunks()))


@router.get("/render-assets", response_model=list[RenderAssetOut])
async def list_assets(uc: UC, kind: str | None = None) -> list[RenderAssetOut]:
    return [RenderAssetOut.of(a, ok) for a, ok in await uc.list_render_assets(kind)]


@router.delete("/render-assets/{asset_id}", status_code=204)
async def delete_asset(asset_id: UUID, uc: UC) -> Response:
    await uc.delete_render_asset(asset_id)
    return Response(status_code=204)
