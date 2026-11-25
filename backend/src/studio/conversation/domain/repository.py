from typing import Protocol
from uuid import UUID

from studio.conversation.domain.conversation import Conversation
from studio.shared.domain.bots import Bot


class ConversationRepository(Protocol):
    async def add(self, conversation: Conversation) -> None: ...

    async def save(self, conversation: Conversation) -> None: ...

    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def list_recent(self, bot: Bot | None, limit: int) -> list[Conversation]: ...

    async def fail_interrupted(self) -> int: ...
