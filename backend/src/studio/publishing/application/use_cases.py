import logging
from uuid import UUID

from studio.publishing.application.ports import (
    PublicationMaterial,
    PublicationSource,
    PublishError,
    PublishRequest,
    YoutubePublisher,
)
from studio.publishing.application.parsing import parse_description, parse_title
from studio.publishing.application.prompts import description_prompt, description_revision_prompt, title_prompt
from studio.publishing.domain.publication import Link, Publication, PublicationStatus
from studio.publishing.domain.repository import PublicationRepository
from studio.shared.application.ports import AgentError, AgentGateway, BackgroundRunner, GuidelineSource
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.guidance import GuidelineScope

log = logging.getLogger(__name__)
TARGETS = ("title", "description", "tags", "all")


class PublicationWorkflow:
    """Jules Verne escreve a descrição; o Youtoba cria título e tags; o publicador envia ao YouTube."""

    def __init__(
        self, repo: PublicationRepository, source: PublicationSource, agents: AgentGateway, runner: BackgroundRunner,
        publisher: YoutubePublisher, guidelines: GuidelineSource,
    ):  # fmt: skip
        self.repo, self.source, self.agents, self.runner = repo, source, agents, runner
        self.publisher, self.guidelines = publisher, guidelines

    async def generate(self, publication_id: UUID) -> None:
        pub = await self.repo.get(publication_id)
        material = await self.source.material(pub.render_id) if pub else None
        if pub is None:
            return
        try:
            if material is None:
                raise AgentError("O vídeo deste envio não está mais disponível.")
            rules = await self.guidelines.texts_for(GuidelineScope.SCRIPT)
            description = parse_description(await self.agents.ask(Bot.JULESVERNE, description_prompt(material, rules)))
            title, alternatives, tags, rationale = parse_title(
                await self.agents.ask(Bot.YOUTOBA, title_prompt(material, description))
            )
            pub = await self.repo.get(publication_id) or pub
            pub.apply_generated(title, alternatives, description, tags, rationale)
        except AgentError as exc:
            log.warning("publicação %s: geração falhou: %s", publication_id, exc)
            pub.fail(str(exc), "generation")
        except Exception:
            log.exception("erro inesperado gerando a publicação %s", publication_id)
            pub.fail("Erro interno ao gerar título e descrição.", "generation")
        await self.repo.save(pub)

    async def revise(self, publication_id: UUID, target: str, instructions: str) -> None:
        pub = await self.repo.get(publication_id)
        material = await self.source.material(pub.render_id) if pub else None
        if pub is None:
            return
        try:
            if material is None:
                raise AgentError("O vídeo deste envio não está mais disponível.")
            description, title, alternatives, tags, rationale = None, None, None, None, None
            if target in ("description", "all"):
                description = parse_description(
                    await self.agents.ask(Bot.JULESVERNE, description_revision_prompt(material, pub, instructions))
                )
            if target in ("title", "tags", "all"):
                current = description if description is not None else pub.description
                title, alternatives, new_tags, rationale = parse_title(
                    await self.agents.ask(Bot.YOUTOBA, title_prompt(material, current, instructions, target))
                )
                tags = new_tags if target in ("tags", "all") else None
                if target == "tags":
                    title, alternatives = None, None
            pub = await self.repo.get(publication_id) or pub  # o editor pode ter editado enquanto os agentes trabalhavam
            pub.apply_revision(title, alternatives, description, tags, rationale)
        except AgentError as exc:
            log.warning("publicação %s: revisão falhou: %s", publication_id, exc)
            pub.fail(str(exc), "revision")
        except Exception:
            log.exception("erro inesperado revisando a publicação %s", publication_id)
            pub.fail("Erro interno ao revisar.", "revision")
        await self.repo.save(pub)

    async def publish(self, publication_id: UUID) -> None:
        pub = await self.repo.get(publication_id)
        if pub is None or pub.status is not PublicationStatus.PUBLISHING:
            return
        request = PublishRequest(
            pub.render_id, pub.title, pub.full_description, pub.tags, pub.category_id, pub.language, pub.privacy,
            pub.notify_subscribers,
        )  # fmt: skip
        try:
            result = await self.publisher.publish(request)
            pub.mark_published(result.video_id)
            log.info("publicação %s enviada ao YouTube: %s", publication_id, result.video_id)
        except (PublishError, InvalidInput) as exc:
            log.warning("publicação %s falhou: %s", publication_id, exc)
            pub.fail(str(exc), "publish")
        except Exception:
            log.exception("erro inesperado publicando %s", publication_id)
            pub.fail("Erro interno ao publicar.", "publish")
        await self.repo.save(pub)


class PreparePublication:
    def __init__(self, workflow: PublicationWorkflow):
        self._wf = workflow

    async def __call__(self, render_id: UUID, force: bool = False) -> Publication:
        material = await self._wf.source.material(render_id)
        if material is None:
            raise Conflict("O vídeo deste envio ainda não está pronto.")
        existing = await self._wf.repo.latest_for_render(render_id)
        if existing and not force and existing.status is not PublicationStatus.FAILED:
            return existing
        pub = Publication.start(render_id, material.script_id, material.links)
        await self._wf.repo.add(pub)
        self._wf.runner.submit(self._wf.generate(pub.id))
        return pub


class RegeneratePublication:
    def __init__(self, workflow: PublicationWorkflow):
        self._wf = workflow

    async def __call__(self, publication_id: UUID) -> Publication:
        pub = await _get(self._wf.repo, publication_id)
        pub.begin_generation()
        await self._wf.repo.save(pub)
        self._wf.runner.submit(self._wf.generate(pub.id))
        return pub


class RevisePublication:
    def __init__(self, workflow: PublicationWorkflow):
        self._wf = workflow

    async def __call__(self, publication_id: UUID, target: str, instructions: str) -> Publication:
        if target not in TARGETS:
            raise InvalidInput("Escolha o que revisar: title, description, tags ou all.")
        if not instructions.strip():
            raise InvalidInput("Diga o que deve mudar.")
        pub = await _get(self._wf.repo, publication_id)
        pub.begin_revision()
        await self._wf.repo.save(pub)
        self._wf.runner.submit(self._wf.revise(pub.id, target, instructions.strip()))
        return pub


class EditPublication:
    def __init__(self, repo: PublicationRepository):
        self._repo = repo

    async def __call__(
        self, publication_id: UUID, title: str | None = None, description: str | None = None, tags: list[str] | None = None,
        links: list[Link] | None = None, privacy: str | None = None, notify_subscribers: bool | None = None,
    ) -> Publication:  # fmt: skip
        pub = await _get(self._repo, publication_id)
        pub.edit(title, description, tags, links, privacy, notify_subscribers)
        await self._repo.save(pub)
        return pub


class PublishToYoutube:
    """Só acontece quando o usuário confirma (botão **Publicar**); o chat não tem como disparar isto."""

    def __init__(self, workflow: PublicationWorkflow):
        self._wf = workflow

    async def __call__(self, publication_id: UUID) -> Publication:
        pub = await _get(self._wf.repo, publication_id)
        pub.begin_publish()
        await self._wf.repo.save(pub)
        self._wf.runner.submit(self._wf.publish(pub.id))
        return pub


class GetPublication:
    def __init__(self, repo: PublicationRepository):
        self._repo = repo

    async def __call__(self, publication_id: UUID) -> Publication:
        return await _get(self._repo, publication_id)


class GetPublicationForRender:
    def __init__(self, repo: PublicationRepository):
        self._repo = repo

    async def __call__(self, render_id: UUID) -> Publication | None:
        return await self._repo.latest_for_render(render_id)


async def _get(repo: PublicationRepository, publication_id: UUID) -> Publication:
    pub = await repo.get(publication_id)
    if pub is None:
        raise NotFound("Publicação não encontrada.")
    return pub
