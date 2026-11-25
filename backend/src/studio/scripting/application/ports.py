from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class NewsSource:
    """Visão da notícia que o contexto de roteiro precisa (anti-corruption layer)."""

    id: UUID
    topic: str
    title: str
    summary: str
    details: str | None
    source_url: str | None


class NewsSourceReader(Protocol):
    async def get(self, news_item_id: UUID) -> NewsSource | None: ...
