from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import use_cases
from studio.interfaces.http.schemas import NewsSearchIn, NewsSearchOut

router = APIRouter(prefix="/news-searches", tags=["news"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.post("", response_model=NewsSearchOut, status_code=202)
async def start_search(body: NewsSearchIn, uc: UC) -> NewsSearchOut:
    return NewsSearchOut.of(await uc.start_news_search(body.topic, body.instructions, radar_scope=body.radar_scope, window_hours=body.window_hours, window_end=body.window_end))


@router.get("", response_model=list[NewsSearchOut])
async def list_searches(uc: UC, limit: int = Query(20, ge=1, le=100)) -> list[NewsSearchOut]:
    return [NewsSearchOut.of(s) for s in await uc.list_news_searches(limit)]


@router.get("/{search_id}", response_model=NewsSearchOut)
async def get_search(search_id: UUID, uc: UC) -> NewsSearchOut:
    return NewsSearchOut.of(await uc.get_news_search(search_id))
