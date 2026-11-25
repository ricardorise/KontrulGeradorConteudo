import json
from uuid import UUID

from studio.discovery.domain.repository import NewsSearchRepository
from studio.scripting.application.ports import NewsSource


class DiscoveryNewsSourceReader:
    """Adaptador: o contexto de roteiro lê notícias do contexto de descoberta sem importar seu domínio."""

    def __init__(self, searches: NewsSearchRepository):
        self._searches = searches

    async def get(self, news_item_id: UUID) -> NewsSource | None:
        found = await self._searches.find_item(news_item_id)
        if found is None:
            return None
        search, item = found
        return NewsSource(
            id=item.id, topic=search.topic, title=item.title, summary=item.summary,
            details="\n\n".join(filter(None, [item.details, ("Radar oficial: " + json.dumps(item.radar, ensure_ascii=False)) if item.radar else None])), source_url=item.source_url,
        )  # fmt: skip
