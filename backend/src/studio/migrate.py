"""Aplica as migrações SQL (backend/migrations/*.sql) no banco e sai.

    STUDIO_DATABASE_URL=postgresql://usuario:senha@host:5432/banco python -m studio.migrate

O backend já faz isso sozinho ao subir (STUDIO_RUN_MIGRATIONS=true, o padrão); este comando serve para
preparar o banco antes, em CI ou numa instalação nova. É idempotente: só aplica o que ainda não foi aplicado.
"""

import asyncio
import os
import sys

from studio.infrastructure.persistence.database import create_pool, run_migrations


async def main() -> int:
    dsn = os.environ.get("STUDIO_DATABASE_URL")
    if not dsn:
        print("Defina STUDIO_DATABASE_URL (ex.: postgresql://usuario:senha@host:5432/banco).", file=sys.stderr)
        return 2
    pool = await create_pool(dsn)
    try:
        applied = await run_migrations(pool)
    finally:
        await pool.close()
    print("Migrações aplicadas: " + ", ".join(applied) if applied else "Banco já está atualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
