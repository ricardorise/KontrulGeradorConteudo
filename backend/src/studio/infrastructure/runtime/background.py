import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger(__name__)


class AsyncioBackgroundRunner:
    """Adaptador da porta BackgroundRunner usando tarefas do event loop."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("tarefa em segundo plano falhou", exc_info=task.exception())

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
