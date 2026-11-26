import logging
from typing import Protocol
from uuid import UUID

from studio.scripting.application.parsing import parse_broll, parse_script_lines
from studio.scripting.application.ports import NewsSourceReader
from studio.scripting.application.prompts import broll_prompt, script_prompt, shorten_prompt
from studio.scripting.domain.config import BUILTIN_PROFILES, DURATIONS, ScriptConfig, ScriptProfile, builtin_profile
from studio.scripting.domain.repository import ScriptProfileRepository, ScriptRepository
from studio.scripting.domain.script import Script
from studio.shared.application.ports import AgentError, AgentGateway, BackgroundRunner, GuidelineSource
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
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
            prompt = script_prompt(source, rules, script.instructions, script.config)
            raw = await self.agents.ask(Bot.JULESVERNE, prompt)
            title, lines = parse_script_lines(raw, script.config)
            config = script.config
            total = sum(len(t) for _, t in lines)
            if config and not config.fits(total):  # passou do tempo escolhido: o roteirista refaz uma vez, mais curto
                raw = await self.agents.ask(Bot.JULESVERNE, shorten_prompt(prompt, total, config))
                title, lines = parse_script_lines(raw, config)
                total = sum(len(t) for _, t in lines)
                if not config.fits(total):
                    raise AgentError(
                        f"O roteiro ficou com {total} caracteres, acima do limite de {config.max_chars} "
                        f"({config.duration_minutes} min), mesmo após o ajuste. Gere de novo."
                    )
            script.complete(title or source.title, [t for _, t in lines], [s for s, _ in lines])
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

    async def find_broll(
        self, script_id: UUID, instructions: str | None = None, paragraph_ids: list[UUID] | None = None
    ) -> None:
        """Busca B-roll para todos os parágrafos ou só para os escolhidos, sem apagar o que já existe."""
        script = await self.repo.get(script_id)
        if script is None or script.broll_status is not JobStatus.RUNNING:
            return
        wanted = set(paragraph_ids) if paragraph_ids is not None else None
        targets = [p for p in script.paragraphs if wanted is None or p.id in wanted]
        subset = None if wanted is None else [p.position for p in targets]
        try:
            rules = await self.guidelines.texts_for(GuidelineScope.BROLL)
            prompt = broll_prompt(
                script.title, [p.text for p in targets], rules, instructions,
                indexes=subset, avoid_video_ids=script.used_video_ids(),
            )  # fmt: skip
            raw = await self.agents.ask(Bot.LUMIERE, prompt)
            scenes = parse_broll(raw, len(script.paragraphs), set(subset) if subset is not None else None)
            # recarrega: o editor pode ter inserido/trocado vídeos enquanto a Lumière pesquisava
            script = await self.repo.get(script_id) or script
            if scenes:
                script.complete_broll(scenes, set(subset) if subset is not None else None)
            else:
                script.fail_broll("A Lumière não encontrou cenas novas. As sugestões atuais foram mantidas; tente de novo em alguns minutos.")
        except AgentError as exc:
            log.warning("b-roll do roteiro %s falhou: %s", script_id, exc)
            script.fail_broll(str(exc))
        except Exception:
            log.exception("erro inesperado no b-roll %s", script_id)
            script.fail_broll("Erro interno ao buscar B-roll.")
        await self.repo.save(script)


class ScriptConfigOptions:
    """Opções da "Configuração do roteiro": perfis (básicos + cadastrados) e tempos."""

    def __init__(self, profiles: ScriptProfileRepository):
        self._profiles = profiles

    async def profiles(self) -> list[ScriptProfile]:
        return [*BUILTIN_PROFILES, *await self._profiles.list_custom()]

    async def resolve(self, profile_id: str | None) -> ScriptProfile | None:
        if not profile_id:
            return None
        found = builtin_profile(profile_id) or await self._profiles.get(profile_id)
        if found is None:
            raise InvalidInput("Perfil de roteirista não encontrado.")
        return found

    async def build(
        self, profile_id: str | None, duration_minutes: int | None, presenters: list[str] | None
    ) -> ScriptConfig:
        return ScriptConfig.build(await self.resolve(profile_id), duration_minutes, presenters)

    durations = DURATIONS


class AddScriptProfile:
    def __init__(self, profiles: ScriptProfileRepository):
        self._profiles = profiles

    async def __call__(self, name: str, instructions: str, description: str = "") -> ScriptProfile:
        profile = ScriptProfile.create(name, instructions, description)
        if name.strip().lower() in {p.name.lower() for p in await self._profiles.list_custom()}:
            raise Conflict("Já existe um perfil com esse nome.")
        await self._profiles.add(profile)
        return profile


class DeleteScriptProfile:
    def __init__(self, profiles: ScriptProfileRepository):
        self._profiles = profiles

    async def __call__(self, profile_id: str) -> None:
        if builtin_profile(profile_id):
            raise InvalidInput("Os perfis básicos não podem ser apagados.")
        if not await self._profiles.delete(profile_id):
            raise NotFound("Perfil não encontrado.")


class StartScriptGeneration:
    def __init__(self, workflow: ScriptWorkflow):
        self._wf = workflow

    async def __call__(
        self, news_item_id: UUID, force: bool = False, instructions: str | None = None, config: ScriptConfig | None = None
    ) -> Script:
        if await self._wf.news.get(news_item_id) is None:
            raise NotFound("Notícia não encontrada.")
        has_config = bool(config and not config.is_empty)
        force = force or has_config or bool(instructions and instructions.strip())  # pedido específico => novo roteiro
        if not force:
            existing = await self._wf.repo.get_latest_for_news_item(news_item_id)
            if existing and existing.status is not JobStatus.FAILED:
                return existing
        script = Script.start(news_item_id, instructions, config)
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

    async def __call__(
        self, script_id: UUID, instructions: str | None = None, paragraph_ids: list[UUID] | None = None
    ) -> Script:
        script = await self._wf.repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        script.begin_broll(set(paragraph_ids) if paragraph_ids is not None else None)
        await self._wf.repo.save(script)
        self._wf.runner.submit(self._wf.find_broll(script.id, instructions, paragraph_ids))
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


class VideoTitles(Protocol):
    """Porta de saída: título público de um vídeo do YouTube (None se não der para obter)."""

    async def title_of(self, video_id: str) -> str | None: ...


class AddBroll:
    """Insere um vídeo escolhido pelo editor (link do YouTube) num parágrafo."""

    def __init__(self, repo: ScriptRepository, titles: VideoTitles):
        self._repo, self._titles = repo, titles

    async def __call__(self, script_id: UUID, paragraph_id: UUID, url: str) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        suggestion = script.add_manual_broll(paragraph_id, url)  # valida o link e as regras
        title = await self._titles.title_of(suggestion.video_id)
        if title:
            script.replace_broll(suggestion.id, url, title)
            suggestion = next(b for p in script.paragraphs for b in p.broll if b.id == suggestion.id)
        await self._repo.add_broll(paragraph_id, suggestion)
        return script


class ReplaceBroll:
    """Troca o vídeo de uma sugestão por outro escolhido pelo editor (o corte feito no vídeo antigo continua válido)."""

    def __init__(self, repo: ScriptRepository, titles: VideoTitles):
        self._repo, self._titles = repo, titles

    async def __call__(self, script_id: UUID, broll_id: UUID, url: str) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        suggestion = script.replace_broll(broll_id, url)
        title = await self._titles.title_of(suggestion.video_id)
        if title:
            suggestion = script.replace_broll(broll_id, url, title)
        await self._repo.update_broll(suggestion)
        return script


class RemoveBroll:
    def __init__(self, repo: ScriptRepository):
        self._repo = repo

    async def __call__(self, script_id: UUID, broll_id: UUID) -> Script:
        script = await self._repo.get(script_id)
        if script is None:
            raise NotFound("Roteiro não encontrado.")
        script.remove_broll(broll_id)
        await self._repo.delete_broll(broll_id)
        return script
