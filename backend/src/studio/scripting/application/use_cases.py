import logging
from uuid import UUID

from studio.scripting.application.parsing import parse_broll, parse_script
from studio.scripting.application.ports import NewsSourceReader
from studio.scripting.application.prompts import broll_prompt, script_prompt
from studio.scripting.domain.repository import ScriptRepository
from studio.scripting.domain.script import Script
from studio.shared.application.ports import AgentError, AgentGateway, BackgroundRunner, GuidelineSource
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import NotFound
from studio.shared.domain.guidance import GuidelineScope
from studio.shared.domain.status import JobStatus

log = logging.getLogger(__name__)


class ScriptWorkflow:
    """Orquestra Jules Verne (roteiro) e, em seguida, Lumière (B-roll)."""

    def __init__(
        self,
        repo: ScriptRepository,
        news: NewsSourceReader,
        agents: AgentGateway,
        runner: BackgroundRunner,
        guidelines: GuidelineSource,
    ):
        self.repo, self.news, self.agents, self.runner, self.guidelines = repo, news, agents, runner, guidelines

    async def write_script(self, script_id: UUID) -> None:
        script = await self.repo.get(script_id)
        source = await self.news.get(script.news_item_id) if script else None
        if script is None:
            return
        if source is None:
            script.fail("Notícia de origem não encontrada.")
            await self.repo.save(script)
            return
        try:
            rules = await self.guidelines.texts_for(GuidelineScope.SCRIPT)
            raw = await self.agents.ask(Bot.JULESVERNE, script_prompt(source, rules, script.instructions))
            title, texts = parse_script(raw)
            script.complete(title or source.title, texts)
            script.begin_broll()
        except AgentError as exc:
            log.warning("roteiro %s falhou: %s", script_id, exc)
            script.fail(str(exc))
        except Exception:
            log.exception("erro inesperado no roteiro %s", script_id)
            script.fail("Erro interno ao gerar o roteiro.")
        await self.repo.save(script)
        if script.status is JobStatus.DONE:
            await self.find_broll(script_id)

    async def find_broll(self, script_id: UUID, instructions: str | None = None) -> None:
        script = await self.repo.get(script_id)
        if script is None or script.broll_status is not JobStatus.RUNNING:
            return
        texts = [p.text for p in script.paragraphs]
        try:
            rules = await self.guidelines.texts_for(GuidelineScope.BROLL)
            raw = await self.agents.ask(Bot.LUMIERE, broll_prompt(script.title, texts, rules, instructions))
            scenes = parse_broll(raw, len(texts))
            if scenes:
                script.complete_broll(scenes)
            else:
                script.fail_broll("A Lumière não encontrou cenas utilizáveis. Tente buscar novamente em alguns minutos.")
        except AgentError as exc:
            log.warning("b-roll do roteiro %s falhou: %s", script_id, exc)
            script.fail_broll(str(exc))
        except Exception:
            log.exception("erro inesperado no b-roll %s", script_id)
            script.fail_broll("Erro interno ao buscar B-roll.")
        await self.repo.save(script)


class StartScriptGeneration:
    def __init__(self, workflow: ScriptWorkflow):
        self._wf = workflow

    async def __call__(self, news_item_id: UUID, force: bool = False, instructions: str | None = None) -> Script:
        if await self._wf.news.get(news_item_id) is None:
            raise NotFound("Notícia não encontrada.")
        force = force or bool(instructions and instructions.strip())  # pedido específico => novo roteiro
        if not force:
            existing = await self._wf.repo.get_latest_for_news_item(news_item_id)
            if existing and existing.status is not JobStatus.FAILED:
                return existing
        script = Script.start(news_item_id, instructions)
        await self._wf.repo.add(script)
        self._wf.runner.submit(self._wf.write_script(script.id))
        return script


class GetScript:
    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(self, script_id: UUID) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        return script


class RetryBroll:
    def __init__(self, workflow: ScriptWorkflow):
        self._wf = workflow

    async def __call__(self, script_id: UUID, instructions: str | None = None) -> Script:
        script = await self._wf.repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        script.begin_broll()
        await self._wf.repo.save(script)
        self._wf.runner.submit(self._wf.find_broll(script.id, instructions))
        return script


class AddCut:
    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(
        self,
        script_id: UUID,
        paragraph_id: UUID,
        video_url: str,
        start: float,
        end: float,
        title: str | None = None,
        text_range: tuple[int, int] | None = None,
    ) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        cut = script.add_cut(paragraph_id, video_url, start, end, title, text_range)
        await self._repo.add_cut(script_id, cut)
        return script


class DeleteCut:
    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(self, script_id: UUID, cut_id: UUID) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        script.remove_cut(cut_id)
        await self._repo.delete_cut(cut_id)
        return script


class SetCutExcerpt:
    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(self, script_id: UUID, cut_id: UUID, text_range: tuple[int, int] | None) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        cut = script.set_cut_excerpt(cut_id, text_range)
        await self._repo.set_cut_excerpt(cut)
        return script


class GetLatestScript:
    """Roteiro mais recente de uma notícia (qualquer status) ou None; a tela usa para seguir roteiros novos."""

    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(self, news_item_id: UUID) -> Script | None:
        return await self._repo.get_latest_for_news_item(news_item_id)
