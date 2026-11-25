from uuid import uuid4

from studio.discovery.domain.news_search import NewsItem
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentOutputError


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"null", "none"} else None


_RADAR_TEXT = ('ranking_reason', 'category', 'status', 'nature', 'why_now', 'velocity', 'started_at', 'content_potential', 'divergences')
_RADAR_LISTS = ('where_growing', 'evidence', 'angles', 'sources')


def _radar(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {key: text for key in _RADAR_TEXT if (text := _clean(value.get(key)))}
    for key in _RADAR_LISTS:
        raw = value.get(key)
        if isinstance(raw, list):
            result[key] = [text for item in raw if isinstance(item, str) and (text := _clean(item))]
        elif isinstance(raw, str) and (text := _clean(raw)):
            result[key] = [text]
    return result


def parse_news(raw: str, *, ranked: bool = False) -> list[NewsItem]:
    payload = extract_json_object(raw, "news")
    entries = payload["news"]
    if not isinstance(entries, list):
        raise AgentOutputError("O campo 'news' não é uma lista.")
    if ranked:
        if any(not isinstance(e, dict) or type(e.get('rank')) is not int for e in entries):
            raise AgentOutputError('O Radar não retornou um ranking inteiro para todos os assuntos.')
        if sorted(e['rank'] for e in entries) != list(range(1, len(entries)+1)):
            raise AgentOutputError('O ranking do Radar tem posições repetidas ou lacunas.')
        entries = sorted(entries, key=lambda e: e['rank'])
    items: list[NewsItem] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _clean(entry.get("title"))
        summary = _clean(entry.get("summary"))
        if not title or not summary:
            if ranked:
                raise AgentOutputError("Assunto do ranking sem título ou resumo.")
            continue
        if ranked and not _radar(entry.get('radar')).get('ranking_reason'):
            raise AgentOutputError('O Radar não justificou uma posição do ranking.')
        items.append(
            NewsItem(
                id=uuid4(),
                position=len(items),
                title=title,
                summary=summary,
                details=_clean(entry.get("details")),
                source_url=_clean(entry.get("source_url")),
                published_at=_clean(entry.get("published_at")),
                radar=_radar(entry.get("radar")),
            )
        )
    if not items:
        raise AgentOutputError("O Tonton não retornou nenhuma notícia utilizável.")
    return items
