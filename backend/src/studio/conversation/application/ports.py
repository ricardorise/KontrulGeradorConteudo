from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studio.conversation.domain.conversation import ActionOutcome
from studio.shared.domain.guidance import GuidelineScope


@dataclass(frozen=True)
class ScreenContext:
    """O que o usuário está vendo na tela quando fala com o bot."""

    search_id: UUID | None = None
    script_id: UUID | None = None
    publication_id: UUID | None = None  # rascunho de publicação no YouTube aberto na tela


@dataclass(frozen=True)
class ScreenSnapshot:
    search_topic: str | None = None
    news_titles: list[str] = field(default_factory=list)
    script_title: str | None = None
    script_paragraphs: list[str] = field(default_factory=list)
    publication: str | None = None  # resumo do rascunho de publicação aberto


class StudioGateway(Protocol):
    """Porta de saída: o que o chat pode fazer no estúdio (implementada sobre os outros contextos)."""

    async def snapshot(self, ctx: ScreenContext) -> ScreenSnapshot: ...

    async def search_news(self, topic: str, instructions: str | None) -> ActionOutcome: ...

    async def generate_script(self, ctx: ScreenContext, news_number: int, instructions: str | None) -> ActionOutcome: ...

    async def rebuild_broll(self, ctx: ScreenContext, instructions: str | None) -> ActionOutcome: ...

    async def remember(self, scope: GuidelineScope, text: str) -> ActionOutcome: ...

    async def edit_publication(self, ctx: ScreenContext, fields: dict) -> ActionOutcome: ...

    async def revise_publication(self, ctx: ScreenContext, target: str, instructions: str) -> ActionOutcome: ...
