from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import use_cases
from studio.conversation.application.ports import ScreenContext
from studio.interfaces.http.schemas import ConversationIn, ConversationOut, MessageIn
from studio.shared.domain.bots import Bot

router = APIRouter(prefix="/conversations", tags=["chat"])
UC = Annotated[UseCases, Depends(use_cases)]


@router.post("", response_model=ConversationOut, status_code=201)
async def open_conversation(body: ConversationIn, uc: UC) -> ConversationOut:
    return ConversationOut.of(await uc.open_conversation(body.bot))


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    uc: UC, bot: Bot | None = None, limit: int = Query(30, ge=1, le=100)
) -> list[ConversationOut]:
    return [ConversationOut.of(c) for c in await uc.list_conversations(bot, limit)]


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: UUID, uc: UC) -> ConversationOut:
    return ConversationOut.of(await uc.get_conversation(conversation_id))


@router.post("/{conversation_id}/messages", response_model=ConversationOut, status_code=202)
async def send_message(conversation_id: UUID, body: MessageIn, uc: UC) -> ConversationOut:
    context = ScreenContext(body.context.search_id, body.context.script_id, body.context.publication_id)
    return ConversationOut.of(await uc.send_message(conversation_id, body.content, context))
