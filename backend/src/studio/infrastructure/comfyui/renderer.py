import json
import logging
from pathlib import Path
from typing import Any

import httpx

from studio.infrastructure.comfyui.workflow import (
    default_background,
    default_music_volume,
    supports_background_volume,
    extract_video_output,
    fill_workflow,
)
from studio.rendering.application.ports import OutputStream, RenderError, RenderProgress, RenderSubmission
from studio.rendering.domain.render_job import RenderOutput

log = logging.getLogger(__name__)
DEFAULT_WORKFLOW = Path(__file__).parent / "workflows" / "papotechcast_api.json"


class ComfyUiRenderer:
    """Adaptador da porta VideoRenderer: POST /prompt, GET /history/{id}, GET /view."""

    def __init__(
        self,
        base_url: str,
        workflow_path: str | None = None,
        timeout_s: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._template: dict[str, Any] = json.loads(Path(workflow_path or DEFAULT_WORKFLOW).read_text(encoding="utf-8"))
        self._timeout, self._transport = timeout_s, transport

    def default_background(self) -> str:
        return default_background(self._template)

    def default_music_volume(self) -> float:
        return default_music_volume(self._template)

    def supports_background_volume(self) -> bool:
        return supports_background_volume(self._template)

    async def upload_input(self, path: Path, subfolder: str, name: str) -> str:
        """POST /upload/image (type=input): coloca o arquivo na pasta input, onde o workflow lê os recursos.

        Se o ComfyUI já tem um arquivo de mesmo nome e tamanho (HEAD /view), não reenvia — importante para backgrounds grandes.
        """
        try:
            async with self._client() as http:
                relative = "/".join(p for p in (subfolder, name) if p)
                head = await http.request("HEAD", "/view", params={"filename": name, "subfolder": subfolder, "type": "input"})
                if head.status_code == 200 and head.headers.get("content-length") == str(path.stat().st_size):
                    return relative
                with open(path, "rb") as handle:
                    response = await http.post(
                        "/upload/image",
                        data={"subfolder": subfolder, "type": "input", "overwrite": "true"},
                        files={"image": (name, handle, "application/octet-stream")},
                        timeout=httpx.Timeout(self._timeout, read=1800, write=1800),
                    )
        except (httpx.HTTPError, OSError) as exc:
            raise RenderError(f"Não consegui enviar {name} ao ComfyUI: {exc}") from exc
        if response.status_code != 200:
            raise RenderError(f"O ComfyUI recusou o upload de {name} (HTTP {response.status_code}).")
        saved = response.json()
        return "/".join(p for p in (saved.get("subfolder") or subfolder, saved.get("name") or name) if p)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=self._timeout, transport=self._transport)

    async def submit(self, submission: RenderSubmission) -> str:
        payload = {"prompt": fill_workflow(self._template, submission)}
        try:
            async with self._client() as http:
                response = await http.post("/prompt", json=payload)
        except httpx.HTTPError as exc:
            raise RenderError(f"ComfyUI indisponível em {self._base}: {exc}") from exc
        if response.status_code != 200:
            raise RenderError(_describe_rejection(response))
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RenderError("O ComfyUI aceitou o envio mas não devolveu o prompt_id.")
        log.info("workflow enviado ao ComfyUI: prompt_id=%s", prompt_id)
        return str(prompt_id)

    async def progress(self, prompt_id: str) -> RenderProgress:
        try:
            async with self._client() as http:
                history = (await http.get(f"/history/{prompt_id}")).json()
                entry = history.get(prompt_id)
                if entry is None:  # ainda não terminou: está na fila ou rodando?
                    queue = (await http.get("/queue")).json()
                    running = any(len(i) > 1 and i[1] == prompt_id for i in queue.get("queue_running", []))
                    if running:
                        return RenderProgress("running")
                    pending = any(len(i) > 1 and i[1] == prompt_id for i in queue.get("queue_pending", []))
                    return RenderProgress("queued" if pending else "lost")
        except (httpx.HTTPError, ValueError) as exc:
            raise RenderError(f"Falha ao consultar o ComfyUI: {exc}") from exc

        status = entry.get("status", {})
        if status.get("status_str") == "error":
            return RenderProgress("failed", error=_execution_error(status))
        if status.get("completed"):
            output = extract_video_output(entry.get("outputs", {}))
            if output is None:
                return RenderProgress("failed", error="A execução terminou, mas não achei o MP4 na saída do workflow.")
            return RenderProgress("done", output=output)
        return RenderProgress("running")

    async def open_output(self, output: RenderOutput) -> OutputStream:
        client = self._client()
        client.timeout = httpx.Timeout(self._timeout, read=None)
        params = {"filename": output.filename, "subfolder": output.subfolder, "type": output.type}
        try:
            response = await client.send(client.build_request("GET", "/view", params=params), stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            raise RenderError(f"ComfyUI indisponível: {exc}") from exc
        if response.status_code != 200:
            await response.aclose()
            await client.aclose()
            raise RenderError(f"O ComfyUI não encontrou o arquivo {output.subfolder}/{output.filename}.")

        async def chunks():
            try:
                async for chunk in response.aiter_bytes(1 << 20):
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        length = response.headers.get("content-length")
        return OutputStream(chunks(), int(length) if length and length.isdigit() else None)


def _describe_rejection(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"O ComfyUI recusou o envio (HTTP {response.status_code})."
    error = body.get("error")
    message = error.get("message") if isinstance(error, dict) else str(error or "")
    details = []
    for node_id, info in (body.get("node_errors") or {}).items():
        for err in info.get("errors", []):
            details.append(f"nó {node_id} ({info.get('class_type')}): {err.get('message')} {err.get('details', '')}".strip())
    return "O ComfyUI recusou o workflow: " + "; ".join(filter(None, [message, *details]))


def _execution_error(status: dict) -> str:
    for kind, data in status.get("messages", []):
        if kind == "execution_error":
            node = f"nó {data.get('node_id')} ({data.get('node_type')})"
            return f"Erro no ComfyUI em {node}: {data.get('exception_message', '').strip()}"
    return "A execução falhou no ComfyUI."
