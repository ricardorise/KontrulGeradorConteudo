from studio.publishing.domain.publication import clean_text
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentOutputError


def _list(value: object) -> list[str]:
    return [str(v).strip() for v in value if isinstance(v, str | int | float) and str(v).strip()] if isinstance(value, list) else []


def parse_description(raw: str) -> str:
    text = extract_json_object(raw, "description").get("description")
    if not isinstance(text, str) or not text.strip():
        raise AgentOutputError("O Jules Verne não devolveu a descrição.")
    return clean_text(text)[:4000]


def parse_title(raw: str) -> tuple[str, list[str], list[str], str | None]:
    payload = extract_json_object(raw, "title")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise AgentOutputError("O Youtoba não devolveu o título.")
    rationale = payload.get("rationale")
    return title.strip(), _list(payload.get("alternatives")), _list(payload.get("tags")), (
        rationale.strip() if isinstance(rationale, str) and rationale.strip() else None
    )
