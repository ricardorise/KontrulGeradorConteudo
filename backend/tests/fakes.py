import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from studio.conversation.domain.conversation import Conversation
from studio.discovery.domain.news_search import NewsItem, NewsSearch
from studio.scripting.application.ports import NewsSource
from studio.scripting.domain.script import Script
from studio.shared.application.ports import AgentError
from studio.shared.domain.bots import Bot


class FakeAgents:
    """Responde por bot com texto fixo (ou levanta AgentError); registra os prompts."""

    def __init__(self, replies: dict[Bot, str | Exception]):
        self.replies, self.calls = replies, []

    async def ask(self, bot: Bot, prompt: str) -> str:
        self.calls.append((bot, prompt))
        reply = self.replies[bot]
        if isinstance(reply, Exception):
            raise reply
        return reply


class InlineRunner:
    """Guarda as tarefas e as executa sob demanda, deixando os testes determinísticos."""

    def __init__(self) -> None:
        self.pending: list[Coroutine[Any, Any, None]] = []

    def submit(self, work: Coroutine[Any, Any, None]) -> None:
        self.pending.append(work)

    async def drain(self) -> None:
        while self.pending:
            await self.pending.pop(0)


class MemoryNewsRepo:
    def __init__(self) -> None:
        self.data: dict[UUID, NewsSearch] = {}

    async def add(self, search: NewsSearch) -> None:
        self.data[search.id] = search

    async def save(self, search: NewsSearch) -> None:
        self.data[search.id] = search

    async def get(self, search_id: UUID) -> NewsSearch | None:
        return self.data.get(search_id)

    async def list_recent(self, limit: int) -> list[NewsSearch]:
        return list(self.data.values())[:limit]

    async def find_item(self, item_id: UUID) -> tuple[NewsSearch, NewsItem] | None:
        for search in self.data.values():
            for item in search.items:
                if item.id == item_id:
                    return search, item
        return None

    async def fail_interrupted(self) -> int:
        return 0


class MemoryScriptRepo:
    def __init__(self) -> None:
        self.data: dict[UUID, Script] = {}

    async def add(self, script: Script) -> None:
        self.data[script.id] = script

    async def save(self, script: Script) -> None:
        self.data[script.id] = script

    async def get(self, script_id: UUID) -> Script | None:
        return self.data.get(script_id)

    async def get_latest_for_news_item(self, news_item_id: UUID) -> Script | None:
        matches = [s for s in self.data.values() if s.news_item_id == news_item_id]
        return max(matches, key=lambda s: s.created_at, default=None)

    async def add_cut(self, script_id, cut) -> None:
        pass  # o agregado em memória já guarda os cortes

    async def delete_cut(self, cut_id) -> None:
        pass

    async def set_cut_excerpt(self, cut) -> None:
        pass

    async def fail_interrupted(self) -> int:
        return 0


class MemoryConversationRepo:
    def __init__(self) -> None:
        self.data: dict[UUID, Conversation] = {}

    async def add(self, conversation: Conversation) -> None:
        self.data[conversation.id] = conversation

    async def save(self, conversation: Conversation) -> None:
        self.data[conversation.id] = conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return self.data.get(conversation_id)

    async def list_recent(self, bot: Bot | None, limit: int) -> list[Conversation]:
        return [c for c in self.data.values() if bot is None or c.bot == bot][:limit]

    async def fail_interrupted(self) -> int:
        return 0


class MemoryNewsReader:
    def __init__(self, repo: MemoryNewsRepo):
        self._repo = repo

    async def get(self, news_item_id: UUID) -> NewsSource | None:
        found = await self._repo.find_item(news_item_id)
        if not found:
            return None
        search, item = found
        return NewsSource(item.id, search.topic, item.title, item.summary, item.details, item.source_url)


class FakeGuidelines:
    def __init__(self, texts: dict | None = None):
        self.texts = texts or {}

    async def texts_for(self, scope) -> list[str]:
        return self.texts.get(scope, [])


class FakeStudio:
    """StudioGateway em memória: registra as chamadas e devolve resultados fixos."""

    def __init__(self) -> None:
        from studio.conversation.application.ports import ScreenSnapshot

        self.calls: list[tuple] = []
        self.snap = ScreenSnapshot("Meta Quest", ["Notícia A", "Notícia B"], None, [])

    async def snapshot(self, ctx):
        return self.snap

    def _ok(self, kind, label, **refs):
        from studio.conversation.domain.conversation import ActionOutcome
        from studio.shared.domain.status import JobStatus

        return ActionOutcome(kind, JobStatus.DONE, label, None, refs)

    async def search_news(self, topic, instructions):
        self.calls.append(("search_news", topic, instructions))
        return self._ok("search_news", f"Busca iniciada: {topic}", search_id="s1")

    async def generate_script(self, ctx, news_number, instructions):
        self.calls.append(("generate_script", news_number, instructions))
        return self._ok("generate_script", "Roteiro em andamento", script_id="sc1")

    async def rebuild_broll(self, ctx, instructions):
        self.calls.append(("rebuild_broll", instructions))
        return self._ok("rebuild_broll", "Refazendo o B-roll")

    async def remember(self, scope, text):
        self.calls.append(("remember", scope.value, text))
        return self._ok("save_guideline", f"Orientação salva: {text}")


__all__ = ["AgentError", "asyncio"]
