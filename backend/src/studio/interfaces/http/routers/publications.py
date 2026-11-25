from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import use_cases
from studio.interfaces.http.schemas import (
    PreparePublicationIn,
    PublicationEditIn,
    PublicationOut,
    PublicationPublishIn,
    PublicationReviseIn,
)
from studio.publishing.domain.publication import Link
from studio.shared.domain.errors import InvalidInput

router = APIRouter(tags=["publications"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.post("/renders/{render_id}/publication", response_model=PublicationOut, status_code=202)
async def prepare(render_id: UUID, uc: UC, body: PreparePublicationIn | None = None) -> PublicationOut:
    """Prepara a publicação: o Jules Verne escreve a descrição e o Youtoba cria título e tags (idempotente)."""
    return PublicationOut.of(await uc.prepare_publication(render_id, body.force if body else False))


@router.get("/renders/{render_id}/publication", response_model=PublicationOut | None)
async def latest(render_id: UUID, uc: UC) -> PublicationOut | None:
    pub = await uc.get_publication_for_render(render_id)
    return PublicationOut.of(pub) if pub else None


@router.get("/publications/{publication_id}", response_model=PublicationOut)
async def get(publication_id: UUID, uc: UC) -> PublicationOut:
    return PublicationOut.of(await uc.get_publication(publication_id))


@router.patch("/publications/{publication_id}", response_model=PublicationOut)
async def edit(publication_id: UUID, body: PublicationEditIn, uc: UC) -> PublicationOut:
    links = [Link(l.label, l.url, l.kind) for l in body.links] if body.links is not None else None
    return PublicationOut.of(
        await uc.edit_publication(
            publication_id, body.title, body.description, body.tags, links, body.privacy, body.notify_subscribers
        )
    )


@router.post("/publications/{publication_id}/revise", response_model=PublicationOut, status_code=202)
async def revise(publication_id: UUID, body: PublicationReviseIn, uc: UC) -> PublicationOut:
    """Pede uma revisão aos especialistas (título/tags: Youtoba; descrição: Jules Verne)."""
    return PublicationOut.of(await uc.revise_publication(publication_id, body.target, body.instructions))


@router.post("/publications/{publication_id}/regenerate", response_model=PublicationOut, status_code=202)
async def regenerate(publication_id: UUID, uc: UC) -> PublicationOut:
    return PublicationOut.of(await uc.regenerate_publication(publication_id))


@router.post("/publications/{publication_id}/publish", response_model=PublicationOut, status_code=202)
async def publish(publication_id: UUID, body: PublicationPublishIn, uc: UC) -> PublicationOut:
    """Envia o vídeo ao canal do YouTube. Exige `confirm: true`; o privado/não listado é imposto pela política do Hermes."""
    if not body.confirm:
        raise InvalidInput("Confirme a publicação (confirm=true).")
    return PublicationOut.of(await uc.publish_publication(publication_id))
