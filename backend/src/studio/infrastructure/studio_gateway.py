"""Adaptador da porta StudioGateway: o chat age sobre os casos de uso dos outros contextos."""

from studio.conversation.application.ports import ScreenContext, ScreenSnapshot
from studio.conversation.domain.conversation import ActionOutcome
from studio.discovery.application.use_cases import GetNewsSearch, StartNewsSearch
from studio.guidance.application.use_cases import AddGuideline
from studio.guidance.domain.guideline import GuidelineOrigin
from studio.publishing.application.use_cases import EditPublication, GetPublication, RevisePublication
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
        edit_publication: EditPublication | None = None,
        revise_publication: RevisePublication | None = None,
        get_publication: GetPublication | None = None,
    ):
        self._start_search, self._get_search = start_news_search, get_news_search
        self._start_script, self._get_script = start_script, get_script
        self._retry_broll, self._add_guideline = retry_broll, add_guideline
        self._edit_publication, self._revise_publication, self._get_publication = edit_publication, revise_publication, get_publication

    async def snapshot(self, ctx: ScreenContext) -> ScreenSnapshot:
        topic, titles, script_title, paragraphs, publication = None, [], None, [], None
        try:
            if ctx.search_id:
                search = await self._get_search(ctx.search_id)
                topic, titles = search.topic, [i.title for i in search.items]
            if ctx.script_id:
                script = await self._get_script(ctx.script_id)
                script_title, paragraphs = script.title, [p.text for p in script.paragraphs]
            if ctx.publication_id and self._get_publication:
                p = await self._get_publication(ctx.publication_id)
                publication = (
                    f"estado: {p.status.value}\ntítulo ({len(p.title)}/100): {p.title}\n"
                    f"descrição: {p.description[:600]}\ntags: {', '.join(p.tags)}\nprivacidade: {p.privacy}"
                )
        except NotFound:
            pass  # contexto velho da tela: segue com o que houver
        return ScreenSnapshot(topic, titles, script_title, paragraphs, publication)

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

    async def edit_publication(self, ctx: ScreenContext, fields: dict) -> ActionOutcome:
        if not ctx.publication_id or not self._edit_publication:
            raise InvalidInput("Não há rascunho de publicação aberto na tela.")
        tags = fields.get("tags")
        pub = await self._edit_publication(
            ctx.publication_id,
            title=fields.get("title"),
            description=fields.get("description"),
            tags=[str(t) for t in tags] if isinstance(tags, list) else None,
            privacy=fields.get("privacy"),
        )
        changed = ", ".join(k for k in ("title", "description", "tags", "privacy") if fields.get(k) is not None)
        return ActionOutcome(
            "set_publication", JobStatus.DONE, f"Publicação atualizada ({changed})", None, {"publication_id": str(pub.id)}
        )  # fmt: skip

    async def revise_publication(self, ctx: ScreenContext, target: str, instructions: str) -> ActionOutcome:
        if not ctx.publication_id or not self._revise_publication:
            raise InvalidInput("Não há rascunho de publicação aberto na tela.")
        pub = await self._revise_publication(ctx.publication_id, target, instructions)
        who = {"title": "Youtoba (título)", "tags": "Youtoba (tags)", "description": "Jules Verne (descrição)"}.get(target, "Jules Verne e Youtoba")
        return ActionOutcome(
            "revise_publication", JobStatus.DONE, f"Revisando com {who}…", None, {"publication_id": str(pub.id)}
        )  # fmt: skip
