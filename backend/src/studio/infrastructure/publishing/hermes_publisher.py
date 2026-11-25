import asyncio
import json
import logging
import shlex
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from uuid import UUID

from studio.infrastructure.agents.hermes_gateway import ssh_prefix
from studio.publishing.application.ports import PublishError, PublishRequest, PublishResult
from studio.rendering.application.use_cases import VideoSource
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentError, AgentGateway
from studio.shared.domain.bots import Bot

log = logging.getLogger(__name__)
CHUNK = 1 << 20


def publish_prompt(request: PublishRequest, agent_path: str) -> str:
    params = {
        "local_path": agent_path,
        "title": request.title,
        "description": request.description,
        "tags": request.tags,
        "category_id": request.category_id,
        "default_language": request.language,
        "privacy_status": request.privacy,
        "notify_subscribers": request.notify_subscribers,
    }
    return f"""Publique AGORA este vídeo no canal PapoTech Cast. O editor já revisou e CONFIRMOU a publicação na tela: não peça confirmação.

Use a ferramenta de upload de vídeo do YouTube (yt_upload_video) com EXATAMENTE estes parâmetros, sem alterar nenhum texto:
{json.dumps(params, ensure_ascii=False, indent=2)}

Se a ferramenta, a credencial ou a política recusar, NÃO tente contornar: informe o motivo exato. Nunca invente um video_id.
Responda SOMENTE com JSON válido (sem markdown):
{{"published": true, "video_id": "ID do vídeo devolvido pela API", "privacy": "private|unlisted", "error": null}}
ou, se não publicou: {{"published": false, "video_id": null, "privacy": null, "error": "motivo"}}"""


class HermesYoutubePublisher:
    """Adaptador da porta YoutubePublisher.

    1) leva o MP4 final para a pasta que o agente publicador pode ler (ssh, em streaming); 2) pede ao agente
    publicador (perfil do Hermes com a ferramenta youtube_publish) que envie ao canal; 3) apaga a cópia.
    """

    def __init__(
        self,
        agents: AgentGateway,
        open_video: Callable[[UUID], Awaitable[VideoSource]],
        *,
        ssh_target: str | None,
        ssh_key: str | None,
        host_dir: str,
        agent_dir: str,
        bot: Bot = Bot.SNIPER,
        push_timeout_s: float = 1800,
    ):  # fmt: skip
        self._agents, self._open_video = agents, open_video
        self._ssh_target, self._ssh_key = ssh_target, ssh_key
        self._host_dir, self._agent_dir, self._bot = host_dir.rstrip("/"), agent_dir.rstrip("/"), bot
        self._push_timeout = push_timeout_s

    async def publish(self, request: PublishRequest) -> PublishResult:
        if not self._ssh_target:
            raise PublishError("Defina STUDIO_HERMES_SSH: o app precisa de SSH para entregar o vídeo ao agente publicador.")
        name = f"studio-{request.render_id}.mp4"
        try:
            source = await self._open_video(request.render_id)
        except Exception as exc:  # noqa: BLE001 - qualquer falha ao abrir o vídeo vira mensagem ao editor
            raise PublishError(f"Não consegui abrir o vídeo para enviar: {exc}") from exc
        try:
            await self._push(source, name)
            raw = await self._agents.ask(self._bot, publish_prompt(request, f"{self._agent_dir}/{name}"))
        except AgentError as exc:
            raise PublishError(
                f"O agente publicador não confirmou o envio ({exc}). Confira no YouTube Studio se o vídeo chegou "
                "antes de publicar de novo."
            ) from exc
        finally:
            await self._remove(name)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> PublishResult:
        try:
            data = extract_json_object(raw, "published")
        except Exception as exc:  # noqa: BLE001
            raise PublishError(
                "Resposta do agente publicador sem o resultado. Confira no YouTube Studio antes de tentar de novo."
            ) from exc
        video_id = data.get("video_id")
        if data.get("published") is True and isinstance(video_id, str) and video_id.strip():
            return PublishResult(video_id.strip(), raw)
        raise PublishError(f"O YouTube/agente recusou o envio: {data.get('error') or 'sem detalhes'}")

    async def _ssh(self, command: str, stdin: bool = False) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *ssh_prefix(self._ssh_target or "", self._ssh_key), command,
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip

    async def _push(self, source: VideoSource, name: str) -> None:
        directory, target = shlex.quote(self._host_dir), shlex.quote(f"{self._host_dir}/{name}")
        proc = await self._ssh(f"mkdir -p {directory} && cat > {target}.part && mv {target}.part {target}", stdin=True)
        try:
            async for chunk in self._chunks(source):
                proc.stdin.write(chunk)  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
            _, err = await asyncio.wait_for(proc.communicate(), timeout=self._push_timeout)
        except BaseException:
            proc.kill()
            raise
        if proc.returncode != 0:
            raise PublishError(f"Não consegui entregar o vídeo ao servidor do Hermes: {err.decode(errors='replace')[-300:]}")

    @staticmethod
    async def _chunks(source: VideoSource) -> AsyncIterator[bytes]:
        if source.path is not None:
            with open(Path(source.path), "rb") as handle:
                while block := await asyncio.to_thread(handle.read, CHUNK):
                    yield block
        elif source.stream is not None:
            async for block in source.stream.chunks:
                yield block
        else:
            raise PublishError("O vídeo não está disponível.")

    async def _remove(self, name: str) -> None:
        try:
            target = shlex.quote(f"{self._host_dir}/{name}")
            proc = await self._ssh(f"rm -f {target} {target}.part")
            await asyncio.wait_for(proc.communicate(), timeout=60)
        except Exception:  # noqa: BLE001 - limpeza é "melhor esforço"
            log.warning("não consegui apagar a cópia temporária %s", name)
