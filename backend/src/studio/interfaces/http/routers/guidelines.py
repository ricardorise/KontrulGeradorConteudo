from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import use_cases
from studio.interfaces.http.schemas import GuidelineActiveIn, GuidelineIn, GuidelineOut

router = APIRouter(prefix="/guidelines", tags=["guidance"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.get("", response_model=list[GuidelineOut])
async def list_guidelines(uc: UC) -> list[GuidelineOut]:
    return [GuidelineOut.of(g) for g in await uc.list_guidelines()]


@router.post("", response_model=GuidelineOut, status_code=201)
async def add_guideline(body: GuidelineIn, uc: UC) -> GuidelineOut:
    return GuidelineOut.of(await uc.add_guideline(body.scope, body.text))


@router.patch("/{guideline_id}", response_model=GuidelineOut)
async def set_active(guideline_id: UUID, body: GuidelineActiveIn, uc: UC) -> GuidelineOut:
    return GuidelineOut.of(await uc.set_guideline_active(guideline_id, body.active))


@router.delete("/{guideline_id}", status_code=204)
async def delete_guideline(guideline_id: UUID, uc: UC) -> Response:
    await uc.delete_guideline(guideline_id)
    return Response(status_code=204)
