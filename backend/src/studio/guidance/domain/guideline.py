from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import InvalidInput
from studio.shared.domain.guidance import GuidelineScope

MAX_TEXT_LENGTH = 300
MAX_ACTIVE = 30


class GuidelineOrigin(StrEnum):
    MANUAL = "manual"
    CHAT = "chat"


@dataclass
class Guideline:
    """Preferência durável do editor, aplicada aos prompts dos bots do escopo."""

    id: UUID
    scope: GuidelineScope
    text: str
    active: bool
    source: GuidelineOrigin
    created_at: datetime

    @classmethod
    def create(cls, scope: GuidelineScope, text: str, source: GuidelineOrigin) -> "Guideline":
        text = " ".join(text.split())
        if not text:
            raise InvalidInput("A orientação está vazia.")
        if len(text) > MAX_TEXT_LENGTH:
            raise InvalidInput(f"A orientação deve ter no máximo {MAX_TEXT_LENGTH} caracteres.")
        return cls(uuid4(), scope, text, True, source, utcnow())
