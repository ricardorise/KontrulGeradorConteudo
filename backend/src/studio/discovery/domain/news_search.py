from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import InvalidInput
from studio.shared.domain.status import JobStatus

MAX_TOPIC_LENGTH = 200


@dataclass(frozen=True)
class NewsItem:
    id: UUID
    position: int
    title: str
    summary: str
    details: str | None = None
    source_url: str | None = None
    published_at: str | None = None
    radar: dict = field(default_factory=dict)


@dataclass
class NewsSearch:
    """Agregado: uma busca de notícias por tema feita pelo Tonton."""

    id: UUID
    topic: str
    status: JobStatus
    created_at: datetime
    error: str | None = None
    finished_at: datetime | None = None
    instructions: str | None = None
    items: list[NewsItem] = field(default_factory=list)
    report_context: dict = field(default_factory=dict)

    @classmethod
    def start(cls, topic: str, instructions: str | None = None) -> "NewsSearch":
        topic = " ".join(topic.split())
        if not topic:
            raise InvalidInput("Informe um tema ou assunto para a busca.")
        if len(topic) > MAX_TOPIC_LENGTH:
            raise InvalidInput(f"O tema deve ter no máximo {MAX_TOPIC_LENGTH} caracteres.")
        return cls(
            id=uuid4(), topic=topic, status=JobStatus.RUNNING, created_at=utcnow(),
            instructions=(instructions or "").strip() or None,
        )

    def complete(self, items: list[NewsItem]) -> None:
        self.items = items
        self.status = JobStatus.DONE
        self.error = None
        self.finished_at = utcnow()

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.finished_at = utcnow()
