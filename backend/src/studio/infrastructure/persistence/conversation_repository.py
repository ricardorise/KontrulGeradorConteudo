import json
from uuid import UUID

import asyncpg

from studio.conversation.domain.conversation import ActionOutcome, Conversation, Message, Role
from studio.shared.domain.bots import Bot
from studio.shared.domain.status import JobStatus

T = "content_studio"


def _conversation(row: asyncpg.Record, messages: list[Message]) -> Conversation:
    return Conversation(
        id=row["id"], bot=Bot(row["bot"]), title=row["title"], created_at=row["created_at"],
        updated_at=row["updated_at"], messages=messages,
    )  # fmt: skip


def _action_json(a: ActionOutcome) -> dict:
    return {"type": a.type, "status": a.status.value, "label": a.label, "error": a.error, "refs": a.refs}


def _action(data: dict) -> ActionOutcome:
    return ActionOutcome(data["type"], JobStatus(data["status"]), data["label"], data.get("error"), data.get("refs", {}))


class PostgresConversationRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def add(self, conversation: Conversation) -> None:
        await self._pool.execute(
            f"INSERT INTO {T}.conversations (id, bot, title, created_at, updated_at) VALUES ($1,$2,$3,$4,$5)",
            conversation.id, conversation.bot.value, conversation.title,
            conversation.created_at, conversation.updated_at,
        )  # fmt: skip

    async def save(self, conversation: Conversation) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"UPDATE {T}.conversations SET title=$2, updated_at=$3 WHERE id=$1",
                conversation.id, conversation.title, conversation.updated_at,
            )
            for m in conversation.messages:  # em ordem: a coluna seq (identity) preserva a ordem de inserção
                await conn.execute(
                    f"INSERT INTO {T}.messages (id, conversation_id, role, content, status, error, created_at, actions) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb) ON CONFLICT (id) DO UPDATE "
                    "SET content=EXCLUDED.content, status=EXCLUDED.status, error=EXCLUDED.error, "
                    "actions=EXCLUDED.actions",
                    m.id, conversation.id, m.role.value, m.content, m.status.value, m.error, m.created_at,
                    json.dumps([_action_json(a) for a in m.actions]),
                )  # fmt: skip

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self._pool.fetchrow(f"SELECT * FROM {T}.conversations WHERE id=$1", conversation_id)
        if row is None:
            return None
        rows = await self._pool.fetch(
            f"SELECT * FROM {T}.messages WHERE conversation_id=$1 ORDER BY seq", conversation_id
        )
        messages = [
            Message(
                id=r["id"], role=Role(r["role"]), content=r["content"], status=JobStatus(r["status"]),
                created_at=r["created_at"], error=r["error"],
                actions=[_action(a) for a in json.loads(r["actions"])],
            )  # fmt: skip
            for r in rows
        ]
        return _conversation(row, messages)

    async def list_recent(self, bot: Bot | None, limit: int) -> list[Conversation]:
        rows = await self._pool.fetch(
            f"SELECT * FROM {T}.conversations WHERE ($1::text IS NULL OR bot=$1) "
            "ORDER BY updated_at DESC LIMIT $2",
            bot.value if bot else None, limit,
        )
        return [_conversation(r, []) for r in rows]

    async def fail_interrupted(self) -> int:
        result = await self._pool.execute(
            f"UPDATE {T}.messages SET status='failed', error='Interrompido por reinício do servidor.' "
            "WHERE status IN ('pending','running')"
        )
        return int(result.split()[-1])
