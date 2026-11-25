from uuid import UUID

from studio.guidance.domain.guideline import MAX_ACTIVE, Guideline, GuidelineOrigin
from studio.guidance.domain.repository import GuidelineRepository
from studio.shared.domain.errors import Conflict, NotFound
from studio.shared.domain.guidance import GuidelineScope


class AddGuideline:
    def __init__(self, repo: GuidelineRepository):
        self._repo = repo

    async def __call__(
        self, scope: GuidelineScope, text: str, source: GuidelineOrigin = GuidelineOrigin.MANUAL
    ) -> Guideline:
        guideline = Guideline.create(scope, text, source)
        existing = await self._repo.find_duplicate(guideline.scope, guideline.text)
        if existing:  # já aprendido: só reativa
            if not existing.active:
                await self._repo.set_active(existing.id, True)
                existing.active = True
            return existing
        if sum(g.active for g in await self._repo.list_all()) >= MAX_ACTIVE:
            raise Conflict(f"Limite de {MAX_ACTIVE} orientações ativas; desative ou apague alguma.")
        await self._repo.add(guideline)
        return guideline


class ListGuidelines:
    def __init__(self, repo: GuidelineRepository):
        self._repo = repo

    async def __call__(self) -> list[Guideline]:
        return await self._repo.list_all()


class SetGuidelineActive:
    def __init__(self, repo: GuidelineRepository):
        self._repo = repo

    async def __call__(self, guideline_id: UUID, active: bool) -> Guideline:
        guideline = await self._repo.get(guideline_id)
        if guideline is None:
            raise NotFound("Orientação não encontrada.")
        await self._repo.set_active(guideline_id, active)
        guideline.active = active
        return guideline


class DeleteGuideline:
    def __init__(self, repo: GuidelineRepository):
        self._repo = repo

    async def __call__(self, guideline_id: UUID) -> None:
        if await self._repo.get(guideline_id) is None:
            raise NotFound("Orientação não encontrada.")
        await self._repo.delete(guideline_id)


class ActiveGuidelineTexts:
    """Implementa a porta GuidelineOrigin: textos ativos do escopo + os de escopo 'all'."""

    def __init__(self, repo: GuidelineRepository):
        self._repo = repo

    async def texts_for(self, scope: GuidelineScope) -> list[str]:
        wanted = {scope, GuidelineScope.ALL}
        return [g.text for g in await self._repo.list_all() if g.active and g.scope in wanted]
