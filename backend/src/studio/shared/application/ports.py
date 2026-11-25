from collections.abc import Coroutine
from typing import Any, Protocol

from studio.shared.domain.bots import Bot
from studio.shared.domain.guidance import GuidelineScope


class AgentError(Exception):
    """Falha ao conversar com um bot (indisponível, timeout, saída vazia...)."""


class AgentOutputError(AgentError):
    """O bot respondeu, mas não no formato combinado."""


class AgentGateway(Protocol):
    """Porta de saída: envia um prompt a um bot do Hermes e devolve o texto final."""

    async def ask(self, bot: Bot, prompt: str) -> str: ...


class BackgroundRunner(Protocol):
    """Porta de saída: executa trabalho demorado fora do ciclo da requisição."""

    def submit(self, work: Coroutine[Any, Any, None]) -> None: ...


class GuidelineSource(Protocol):
    """Porta de saída: orientações ativas do editor para um escopo (já inclui as de escopo 'all')."""

    async def texts_for(self, scope: GuidelineScope) -> list[str]: ...
