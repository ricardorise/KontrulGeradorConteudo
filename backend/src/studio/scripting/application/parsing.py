from studio.scripting.domain.script import BrollSuggestion
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentOutputError

MAX_SCENES_PER_PARAGRAPH = 3


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text and text.lower() not in {"null", "none"} else None


def parse_script(raw: str) -> tuple[str | None, list[str]]:
    payload = extract_json_object(raw, "paragraphs")
    paragraphs = payload["paragraphs"]
    if not isinstance(paragraphs, list):
        raise AgentOutputError("O campo 'paragraphs' não é uma lista.")
    texts = [str(p).strip() for p in paragraphs if isinstance(p, str | int | float) and str(p).strip()]
    if not texts:
        raise AgentOutputError("O Jules Verne não retornou parágrafos.")
    return _text(payload.get("title")), texts


def parse_broll(raw: str, paragraph_count: int, allowed: set[int] | None = None) -> dict[int, list[BrollSuggestion]]:
    payload = extract_json_object(raw, "scenes")
    entries = payload["scenes"]
    if not isinstance(entries, list):
        raise AgentOutputError("O campo 'scenes' não é uma lista.")
    scenes: dict[int, list[BrollSuggestion]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("paragraph"))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < paragraph_count or (allowed is not None and index not in allowed):
            continue
        suggestion = BrollSuggestion.from_scene(
            url=str(entry.get("url") or ""),
            description=_text(entry.get("description")) or "",
            title=_text(entry.get("title")),
            justification=_text(entry.get("justification")),
            start_seconds=entry.get("start_seconds"),
        )
        bucket = scenes.setdefault(index, [])
        if suggestion and len(bucket) < MAX_SCENES_PER_PARAGRAPH:
            bucket.append(suggestion)
    return {index: found for index, found in scenes.items() if found}
