import logging
from uuid import UUID

from studio.conversation.application.actions import PROTOCOL, ActionExecutor, parse_actions, render_snapshot
from studio.conversation.application.ports import ScreenContext, StudioGateway
from studio.conversation.domain.conversation import Conversation, Message, Role
from studio.conversation.domain.repository import ConversationRepository
from studio.shared.application.ports import AgentError, AgentGateway, BackgroundRunner
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import NotFound

log = logging.getLogger(__name__)

HISTORY_MAX_MESSAGES = 20
HISTORY_MAX_CHARS = 12000


def build_prompt(history: list[Message], user_message: str) -> str:
    """Cada chamada ao Hermes é sem estado; o histórico persistido vai junto no prompt."""
    lines: list[str] = []
    size = 0
    for message in reversed(history[-HISTORY_MAX_MESSAGES:]):
        if message.status.value != "done" or not message.content:
            continue
        speaker = "Usuário" if message.role is Role.USER else "Você"
        line = f"{speaker}: {message.content}"
        if size + len(line) > HISTORY_MAX_CHARS:
            break
        lines.append(line)
        size += len(line)
    if not lines:
        return user_message
    transcript = "\n\n".join(reversed(lines))
    return (
        "Continuação de uma conversa em andamento. Histórico até aqui:\n\n"
        f"{transcript}\n\nNova mensagem do usuário (responda a ela):\n{user_message}"
    )


class OpenConversation:
    def __init__(self, repo: ConversationRepository):
        self._repo = repo

    async def __call__(self, bot: Bot) -> Conversation:
        conversation = Conversation.open(bot)
        await self._repo.add(conversation)
        return conversation


class SendMessage:
    def __init__(
        self, repo: ConversationRepository, agents: AgentGateway, runner: BackgroundRunner, studio: StudioGateway
    ):
        self._repo, self._agents, self._runner, self._studio = repo, agents, runner, studio
        self._executor = ActionExecutor(studio)

    async def __call__(
        self, conversation_id: UUID, content: str, context: ScreenContext | None = None
    ) -> Conversation:
        conversation = await self._repo.get(conversation_id)
        if conversation is None:
            raise NotFound("Conversa não encontrada.")
        reply = conversation.post_user_message(content)
        await self._repo.save(conversation)
        self._runner.submit(self._answer(conversation_id, reply.id, context or ScreenContext()))
        return conversation

    async def _answer(self, conversation_id: UUID, reply_id: UUID, ctx: ScreenContext) -> None:
        conversation = await self._repo.get(conversation_id)
        if conversation is None:
            return
        history = conversation.history_before(reply_id)
        try:
            snapshot = await self._studio.snapshot(ctx)
            prompt = f"{PROTOCOL}\n\n{render_snapshot(snapshot)}\n\n{build_prompt(history[:-1], history[-1].content)}"
            raw = await self._agents.ask(conversation.bot, prompt)
            text, requested = parse_actions(raw)
            outcomes = await self._executor.run(requested, ctx)
            if not text and outcomes:
                text = "Pronto — executei o que você pediu."
            conversation.complete_reply(reply_id, text, outcomes)
        except AgentError as exc:
            log.warning("resposta do %s falhou: %s", conversation.bot, exc)
            conversation.fail_reply(reply_id, str(exc))
        except Exception:
            log.exception("erro inesperado respondendo conversa %s", conversation_id)
            conversation.fail_reply(reply_id, "Erro interno ao obter a resposta.")
        await self._repo.save(conversation)


class GetConversation:
    def __init__(self, repo: ConversationRepository):
        self._repo = repo

    async def __call__(self, conversation_id: UUID) -> Conversation:
        conversation = await self._repo.get(conversation_id)
        if conversation is None:
            raise NotFound("Conversa não encontrada.")
        return conversation


class ListConversations:
    def __init__(self, repo: ConversationRepository):
        self._repo = repo

    async def __call__(self, bot: Bot | None = None, limit: int = 30) -> list[Conversation]:
        return await self._repo.list_recent(bot, max(1, min(limit, 100)))
