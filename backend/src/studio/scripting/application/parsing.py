from studio.scripting.domain.config import ScriptConfig
from studio.scripting.domain.script import BrollSuggestion
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentOutputError

MAX_SCENES_PER_PARAGRAPH = 3


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text and text.lower() not in {"null", "none"} else None


def parse_script(raw: str) -> tuple[str | None, list[str]]:
    title, lines = parse_script_lines(raw)
    return title, [text for _, text in lines]


def parse_script_lines(raw: str, config: ScriptConfig | None = None) -> tuple[str | None, list[tuple[str | None, str]]]:
    """Parágrafos como (apresentador, texto). Com dois apresentadores, cada item é {"speaker","text"}; um apresentador
    que o roteirista não identificou assume a alternância entre os dois."""
    payload = extract_json_object(raw, "paragraphs")
    paragraphs = payload["paragraphs"]
    if not isinstance(paragraphs, list):
        raise AgentOutputError("O campo 'paragraphs' não é uma lista.")
    lines: list[tuple[str | None, str]] = []
    for entry in paragraphs:
        speaker_raw = None
        if isinstance(entry, dict):
            speaker_raw, entry = entry.get("speaker") or entry.get("apresentador"), entry.get("text") or entry.get("texto")
        if not isinstance(entry, str | int | float) or not str(entry).strip():
            continue
        speaker = None
        if config and config.is_dialogue:
            speaker = config.resolve_speaker(speaker_raw)
            if speaker is None:  # sem identificação válida: alterna entre os dois
                last = lines[-1][0] if lines else None
                speaker = config.presenters[1] if last == config.presenters[0] else config.presenters[0]
        lines.append((speaker, str(entry).strip()))
    if not lines:
        raise AgentOutputError("O Jules Verne não retornou parágrafos.")
    return _text(payload.get("title")), lines


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
