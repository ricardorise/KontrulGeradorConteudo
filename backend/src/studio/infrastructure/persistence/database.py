import logging
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)
SCHEMA = "content_studio"


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=8)


def _migrations_dir() -> Path:
    # Dockerfile copia ./migrations para /app/migrations; em dev ela fica ao lado de src/.
    for candidate in (Path.cwd() / "migrations", Path(__file__).resolve().parents[4] / "migrations"):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Pasta de migrações não encontrada.")


async def run_migrations(pool: asyncpg.Pool) -> list[str]:
    """Aplica migrations/*.sql ainda não registradas, em ordem, cada uma em uma transação."""
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock(727401)")  # evita corrida entre réplicas
        try:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r["name"] for r in await conn.fetch(f"SELECT name FROM {SCHEMA}.schema_migrations")}
            for path in sorted(_migrations_dir().glob("*.sql")):
                if path.name in done:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text())
                    await conn.execute(f"INSERT INTO {SCHEMA}.schema_migrations (name) VALUES ($1)", path.name)
                applied.append(path.name)
                log.info("migração aplicada: %s", path.name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(727401)")
    return applied
