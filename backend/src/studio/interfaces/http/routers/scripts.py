from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from studio.interfaces.http.container import UseCases
from studio.shared.domain.errors import InvalidInput
from studio.interfaces.http.deps import use_cases
from studio.interfaces.http.schemas import CutExcerptIn, CutIn, ScriptIn, ScriptOut

router = APIRouter(tags=["scripts"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.post("/news-items/{news_item_id}/script", response_model=ScriptOut, status_code=202)
async def generate_script(
    news_item_id: UUID, uc: UC, body: ScriptIn | None = None, force: bool = False
) -> ScriptOut:
    """Idempotente: devolve o roteiro existente; `force=true` ou `instructions` geram um novo."""
    return ScriptOut.of(await uc.start_script(news_item_id, force, body.instructions if body else None))


@router.get("/news-items/{news_item_id}/script", response_model=ScriptOut | None)
async def latest_script(news_item_id: UUID, uc: UC) -> ScriptOut | None:
    """Roteiro mais recente da notícia (null se não houver); não cria nada."""
    script = await uc.get_latest_script(news_item_id)
    return ScriptOut.of(script) if script else None


@router.get("/scripts/{script_id}", response_model=ScriptOut)
async def get_script(script_id: UUID, uc: UC) -> ScriptOut:
    return ScriptOut.of(await uc.get_script(script_id))


@router.post("/scripts/{script_id}/broll", response_model=ScriptOut, status_code=202)
async def retry_broll(script_id: UUID, uc: UC, body: ScriptIn | None = None) -> ScriptOut:
    return ScriptOut.of(await uc.retry_broll(script_id, body.instructions if body else None))


@router.post("/scripts/{script_id}/cuts", response_model=ScriptOut, status_code=201)
async def add_cut(script_id: UUID, body: CutIn, uc: UC) -> ScriptOut:
    if (body.text_start is None) != (body.text_end is None):
        raise InvalidInput("Informe o início e o fim do trecho de texto juntos.")
    text_range = (body.text_start, body.text_end) if body.text_start is not None else None
    return ScriptOut.of(
        await uc.add_cut(
            script_id, body.paragraph_id, body.video_url, body.start_seconds, body.end_seconds,
            body.video_title, text_range,
        )
    )  # fmt: skip


@router.delete("/scripts/{script_id}/cuts/{cut_id}", response_model=ScriptOut)
async def delete_cut(script_id: UUID, cut_id: UUID, uc: UC) -> ScriptOut:
    return ScriptOut.of(await uc.delete_cut(script_id, cut_id))


@router.patch("/scripts/{script_id}/cuts/{cut_id}/excerpt", response_model=ScriptOut)
async def set_cut_excerpt(script_id: UUID, cut_id: UUID, body: CutExcerptIn, uc: UC) -> ScriptOut:
    """Troca o trecho de texto de um corte existente (sem trecho = remove o vínculo)."""
    if (body.text_start is None) != (body.text_end is None):
        raise InvalidInput("Informe o início e o fim do trecho de texto juntos.")
    text_range = (body.text_start, body.text_end) if body.text_start is not None else None
    return ScriptOut.of(await uc.set_cut_excerpt(script_id, cut_id, text_range))
