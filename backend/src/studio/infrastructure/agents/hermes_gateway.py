import asyncio
import logging
import os
import re
import shlex

from studio.shared.application.ports import AgentError
from studio.shared.domain.bots import Bot

log = logging.getLogger(__name__)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def ssh_prefix(ssh_target: str, ssh_key: str | None = None) -> list[str]:
    """Comando ssh base (sem interação) usado para falar com o servidor do Hermes."""
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30"]
    if ssh_key:
        known_hosts = os.path.join(os.path.dirname(ssh_key), "known_hosts")
        ssh += ["-i", ssh_key, "-o", f"UserKnownHostsFile={known_hosts}", "-o", "StrictHostKeyChecking=yes"]
    return [*ssh, ssh_target]


class HermesCliGateway:
    """Adaptador da porta AgentGateway: `hermes -p <bot> -z` dentro do container do Hermes.

    O prompt vai por stdin (sem problemas de aspas/tamanho). Com `ssh_target` o comando roda no
    servidor via SSH (mesmo caminho que o kontrul-api já usa); sem ele, usa o docker local.
    """

    def __init__(
        self,
        *,
        container: str = "hermes",
        ssh_target: str | None = None,
        ssh_key: str | None = None,
        timeout_s: float = 600,
        max_concurrent: int = 3,
    ):
        self._container, self._ssh_target, self._ssh_key = container, ssh_target, ssh_key
        self._timeout_s = timeout_s
        self._slots = asyncio.Semaphore(max_concurrent)

    def command(self, bot: Bot) -> list[str]:
        # Read the official profile on each invocation; no copied or stale Radar rules.
        shell = r"""set -eu
prompt=$(cat)
if [ "$0" = tonton ]; then
    official=$(cat /opt/data/profiles/tonton/SOUL.md /opt/data/profiles/tonton/memories/MEMORY.md)
    prompt=$(printf '%s\n\n%s\n\n%s\n%s' '[PERFIL OFICIAL TONTON E MEMÓRIA ATUAL]' "$official" '[PEDIDO DA APLICAÇÃO — o esquema JSON só adapta a apresentação à tela]' "$prompt")
fi
exec hermes -p "$0" -z "$prompt"
"""
        remote = [
            "docker", "exec", "-i", self._container,
            "sh", "-c", shell, bot.value,
        ]  # fmt: skip
        if not self._ssh_target:
            return remote
        return [*ssh_prefix(self._ssh_target, self._ssh_key), shlex.join(remote)]

    async def ask(self, bot: Bot, prompt: str) -> str:
        async with self._slots:
            log.info("consultando %s (%d chars)", bot.value, len(prompt))
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self.command(bot),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                raise AgentError(f"Não foi possível iniciar a consulta ao {bot.value}: {exc}") from exc
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode()), timeout=self._timeout_s
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise AgentError(f"O {bot.value} não respondeu em {int(self._timeout_s)}s.") from None
            except asyncio.CancelledError:
                proc.kill()
                raise
        if proc.returncode != 0:
            detail = _ANSI.sub("", stderr.decode(errors="replace")).strip()[-400:]
            raise AgentError(f"O {bot.value} falhou (código {proc.returncode}). {detail}".strip())
        text = _ANSI.sub("", stdout.decode(errors="replace")).strip()
        if not text:
            raise AgentError(f"O {bot.value} respondeu vazio.")
        return text
