from urllib.parse import urlparse
from uuid import UUID

from studio.discovery.domain.repository import NewsSearchRepository
from studio.publishing.application.ports import PublicationMaterial
from studio.publishing.domain.publication import Link
from studio.rendering.domain.repository import RenderJobRepository
from studio.scripting.domain.repository import ScriptRepository
from studio.shared.domain.status import JobStatus

MAX_SOURCES, MAX_SCENES = 15, 20


def _host(url: str) -> str:
    return (urlparse(url).hostname or url).removeprefix("www.")


class RenderPublicationSource:
    """Adaptador: monta o material da publicação a partir do envio, do roteiro, da notícia e dos cortes usados."""

    def __init__(self, renders: RenderJobRepository, scripts: ScriptRepository, searches: NewsSearchRepository):
        self._renders, self._scripts, self._searches = renders, scripts, searches

    async def material(self, render_id: UUID) -> PublicationMaterial | None:
        job = await self._renders.get(render_id)
        if job is None or job.status is not JobStatus.DONE or job.output is None:
            return None
        script = await self._scripts.get(job.script_id)
        found = await self._searches.find_item(script.news_item_id) if script else None
        if script is None or found is None:
            return None
        search, item = found

        merged = [item]
        for extra_id in script.extra_news_item_ids:  # notícias agregadas: suas fontes também entram na descrição
            more = await self._searches.find_item(extra_id)
            if more:
                merged.append(more[1])
        urls = [u for it in merged for u in (it.source_url, *[s for s in (it.radar or {}).get("sources", []) if isinstance(s, str)])]
        links: list[Link] = []
        seen: set[str] = set()
        for url in urls:
            if url and url.startswith(("http://", "https://")) and url not in seen and len(seen) < MAX_SOURCES:
                seen.add(url)
                links.append(Link(_host(url), url, "source"))
        used: dict[str, str] = {}
        for cut in script.cuts:  # só as cenas que de fato entraram nos cortes
            used.setdefault(cut.video_id, cut.video_title or "Vídeo no YouTube")
        links += [Link(title[:90], f"https://youtu.be/{vid}", "broll") for vid, title in list(used.items())[:MAX_SCENES]]
        return PublicationMaterial(
            script_id=script.id, topic=search.topic, script_title=script.title,
            paragraphs=[p.text for p in script.paragraphs], news_title=" + ".join(it.title for it in merged), news_summary="\n".join(it.summary for it in merged),
            news_details="\n\n".join(filter(None, (it.details for it in merged))) or None, links=links, video_name=job.output.filename,
        )  # fmt: skip
