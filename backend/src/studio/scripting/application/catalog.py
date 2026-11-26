from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ScriptEntry:
    """Linha do histórico de roteiros: de que assunto é, em que busca está e o que já foi feito com ele."""

    script_id: UUID
    news_item_id: UUID
    search_id: UUID
    news_title: str
    topic: str
    script_title: str | None
    status: str
    created_at: datetime
    paragraphs: int
    profile_name: str | None
    duration_minutes: int | None
    presenters: tuple[str, ...]
    extra_news: int  # notícias agregadas além da principal
    videos_done: int  # envios ao ComfyUI concluídos
    publication_status: str | None  # último rascunho/publicação no YouTube


class ScriptCatalog(Protocol):
    async def list(self, limit: int) -> list[ScriptEntry]: ...


class ListScripts:
    def __init__(self, catalog: ScriptCatalog):
        self._catalog = catalog

    async def __call__(self, limit: int = 100) -> list[ScriptEntry]:
        return await self._catalog.list(limit)
