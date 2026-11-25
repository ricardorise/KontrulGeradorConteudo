"""Adaptador da porta StudioGateway: o chat age sobre os casos de uso dos outros contextos."""

from studio.conversation.application.ports import ScreenContext, ScreenSnapshot
from studio.conversation.domain.conversation import ActionOutcome
from studio.discovery.application.use_cases import GetNewsSearch, StartNewsSearch
from studio.guidance.application.use_cases import AddGuideline
from studio.guidance.domain.guideline import GuidelineOrigin
from studio.scripting.application.use_cases import GetScript, RetryBroll, StartScriptGeneration
from studio.shared.domain.errors import InvalidInput, NotFound
from studio.shared.domain.guidance import GuidelineScope
from studio.shared.domain.status import JobStatus

_SCOPE_LABEL = {
    GuidelineScope.NEWS: "busca de notícias",
    GuidelineScope.SCRIPT: "roteiro",
    GuidelineScope.BROLL: "B-roll",
    GuidelineScope.ALL: "tudo",
}


class StudioUseCaseGateway:
    def __init__(
        self,
        start_news_search: StartNewsSearch,
        get_news_search: GetNewsSearch,
        start_script: StartScriptGeneration,
        get_script: GetScript,
        retry_broll: RetryBroll,
        add_guideline: AddGuideline,
    ):
        self._start_search, self._get_search = start_news_search, get_news_search
        self._start_script, self._get_script = start_script, get_script
        self._retry_broll, self._add_guideline = retry_broll, add_guideline

    async def snapshot(self, ctx: ScreenContext) -> ScreenSnapshot:
        topic, titles, script_title, paragraphs = None, [], None, []
        try:
            if ctx.search_id:
                search = await self._get_search(ctx.search_id)
                topic, titles = search.topic, [i.title for i in search.items]
            if ctx.script_id:
                script = await self._get_script(ctx.script_id)
                script_title, paragraphs = script.title, [p.text for p in script.paragraphs]
        except NotFound:
            pass  # contexto velho da tela: segue com o que houver
        return ScreenSnapshot(topic, titles, script_title, paragraphs)

    async def search_news(self, topic: str, instructions: str | None) -> ActionOutcome:
        search = await self._start_search(topic, instructions)
        return ActionOutcome("search_news", JobStatus.DONE, f"Busca iniciada: {search.topic}", None, {"search_id": str(search.id)})

    async def generate_script(self, ctx: ScreenContext, news_number: int, instructions: str | None) -> ActionOutcome:
        if not ctx.search_id:
            raise InvalidInput("Não há lista de notícias aberta na tela.")
        search = await self._get_search(ctx.search_id)
        if not 1 <= news_number <= len(search.items):
            raise InvalidInput(f"A notícia {news_number} não existe na lista (há {len(search.items)}).")
        item = search.items[news_number - 1]
        script = await self._start_script(item.id, False, instructions)
        return ActionOutcome(
            "generate_script", JobStatus.DONE, f"Roteiro em andamento: {item.title}", None,
            {"search_id": str(search.id), "news_item_id": str(item.id), "script_id": str(script.id)},
        )  # fmt: skip

    async def rebuild_broll(self, ctx: ScreenContext, instructions: str | None) -> ActionOutcome:
        if not ctx.script_id:
            raise InvalidInput("Não há roteiro aberto na tela.")
        script = await self._retry_broll(ctx.script_id, instructions)
        return ActionOutcome("rebuild_broll", JobStatus.DONE, "Refazendo o B-roll", None, {"script_id": str(script.id)})

    async def remember(self, scope: GuidelineScope, text: str) -> ActionOutcome:
        guideline = await self._add_guideline(scope, text, GuidelineOrigin.CHAT)
        return ActionOutcome(
            "save_guideline", JobStatus.DONE, f"Orientação salva ({_SCOPE_LABEL[scope]}): {guideline.text}", None,
            {"guideline_id": str(guideline.id)},
        )  # fmt: skip
