from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from studio.shared.domain.bots import CHAT_BOTS, Bot
from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus

MAX_MESSAGE_LENGTH = 4000
DEFAULT_TITLE = "Nova conversa"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ActionOutcome:
    """Resultado de uma ação que o bot pediu e o sistema executou (mostrado como chip no chat)."""

    type: str  # search_news | generate_script | rebuild_broll | save_guideline
    status: JobStatus  # DONE ou FAILED
    label: str
    error: str | None = None
    refs: dict[str, str] = field(default_factory=dict)  # search_id, script_id, news_item_id...


@dataclass
class Message:
    id: UUID
    role: Role
    content: str
    status: JobStatus
    created_at: datetime
    error: str | None = None
    actions: list[ActionOutcome] = field(default_factory=list)


@dataclass
class Conversation:
    """Agregado: conversa de um usuário com um bot (as respostas chegam de forma assíncrona)."""

    id: UUID
    bot: Bot
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[Message] = field(default_factory=list)

    @classmethod
    def open(cls, bot: Bot) -> "Conversation":
        if bot not in CHAT_BOTS:
            raise InvalidInput(f"O bot '{bot}' não está disponível para chat.")
        now = utcnow()
        return cls(id=uuid4(), bot=bot, title=DEFAULT_TITLE, created_at=now, updated_at=now)

    @property
    def has_pending_reply(self) -> bool:
        return any(m.role is Role.ASSISTANT and not m.status.is_terminal for m in self.messages)

    def post_user_message(self, content: str) -> Message:
        """Registra a fala do usuário e abre a resposta pendente do bot; devolve esta última."""
        content = content.strip()
        if not content:
            raise InvalidInput("A mensagem está vazia.")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise InvalidInput(f"A mensagem deve ter no máximo {MAX_MESSAGE_LENGTH} caracteres.")
        if self.has_pending_reply:
            raise Conflict("Aguarde o bot terminar de responder.")
        now = utcnow()
        if self.title == DEFAULT_TITLE:
            self.title = content if len(content) <= 60 else content[:57].rstrip() + "..."
        self.messages.append(Message(uuid4(), Role.USER, content, JobStatus.DONE, now))
        reply = Message(uuid4(), Role.ASSISTANT, "", JobStatus.RUNNING, now)
        self.messages.append(reply)
        self.updated_at = now
        return reply

    def history_before(self, message_id: UUID) -> list[Message]:
        for index, message in enumerate(self.messages):
            if message.id == message_id:
                return self.messages[:index]
        raise NotFound("Mensagem não encontrada.")

    def complete_reply(self, message_id: UUID, content: str, actions: list[ActionOutcome] | None = None) -> None:
        reply = self._reply(message_id)
        reply.content, reply.status, reply.error = content.strip(), JobStatus.DONE, None
        reply.actions = actions or []
        self.updated_at = utcnow()

    def fail_reply(self, message_id: UUID, error: str) -> None:
        reply = self._reply(message_id)
        reply.status, reply.error = JobStatus.FAILED, error
        self.updated_at = utcnow()

    def _reply(self, message_id: UUID) -> Message:
        for message in self.messages:
            if message.id == message_id and message.role is Role.ASSISTANT:
                return message
        raise NotFound("Resposta não encontrada.")
