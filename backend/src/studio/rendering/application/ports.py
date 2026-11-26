from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from studio.rendering.domain.render_job import RenderOutput
from studio.rendering.domain.script_view import ScriptForRender


class RenderError(Exception):
    """Falha ao falar com o ComfyUI ou execução rejeitada/falha."""


@dataclass(frozen=True)
class NarrationSettings:
    """Entradas do nó PapoNarration (voz ElevenLabs). A chave da ElevenLabs fica só no servidor do ComfyUI."""

    provedor: str = "ElevenLabs"
    voz_elevenlabs: str = ""  # vazio = voz padrão do servidor
    modelo_elevenlabs: str = "eleven_multilingual_v2"
    velocidade_elevenlabs: float = 1.08
    estabilidade_elevenlabs: float = 0.30
    similaridade_elevenlabs: float = 0.73
    estilo_elevenlabs: float = 0.74
    idioma_elevenlabs: str = "pt"

    PROVIDERS = ("VoiceStudio", "ElevenLabs")
    MODELS = ("eleven_multilingual_v2", "eleven_flash_v2_5")
    LIMITS = {
        "velocidade_elevenlabs": (0.7, 1.2),
        "estabilidade_elevenlabs": (0.0, 1.0),
        "similaridade_elevenlabs": (0.0, 1.0),
        "estilo_elevenlabs": (0.0, 1.0),
    }

    def problems(self) -> list[str]:
        found = []
        if self.provedor not in self.PROVIDERS:
            found.append(f"Provedor de voz inválido: {self.provedor}.")
        if self.modelo_elevenlabs not in self.MODELS:
            found.append(f"Modelo de voz inválido: {self.modelo_elevenlabs}.")
        for name, (low, high) in self.LIMITS.items():
            if not low <= getattr(self, name) <= high:
                found.append(f"{name} deve ficar entre {low} e {high}.")
        if not self.idioma_elevenlabs.strip():
            found.append("Informe o idioma da voz (ex.: pt).")
        return found


@dataclass(frozen=True)
class RenderSubmission:
    roteiro: str
    background: str
    edit_list: str
    music: str | None = None  # caminho da trilha dentro da pasta input do ComfyUI
    music_volume: float | None = None
    background_volume: float | None = None  # volume_fundo: áudio do vídeo de background
    narration: NarrationSettings | None = None  # None preserva a voz do workflow


@dataclass(frozen=True)
class RenderProgress:
    state: Literal["queued", "running", "done", "failed", "lost"]  # lost: o ComfyUI não conhece mais o prompt
    output: RenderOutput | None = None
    error: str | None = None


@dataclass
class OutputStream:
    chunks: AsyncIterator[bytes]
    content_length: int | None = None


class VideoRenderer(Protocol):
    """Porta de saída: renderizador de vídeo (ComfyUI com o workflow do PapoTechCast)."""

    def default_background(self) -> str: ...

    def default_music_volume(self) -> float: ...

    def supports_background_volume(self) -> bool: ...

    def default_narration(self) -> NarrationSettings: ...

    async def upload_input(self, path: Path, subfolder: str, name: str) -> str:
        """Envia um arquivo à pasta input do ComfyUI e devolve o caminho relativo (subpasta/nome)."""
        ...

    async def submit(self, submission: RenderSubmission) -> str: ...

    async def progress(self, prompt_id: str) -> RenderProgress: ...

    async def open_output(self, output: RenderOutput) -> OutputStream: ...


class ScriptSourceReader(Protocol):
    async def get(self, script_id: UUID) -> ScriptForRender | None: ...


class MediaError(Exception):
    """Arquivo de vídeo inválido ou falha ao montar o vídeo final."""


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_video: bool
    has_audio: bool


class MediaProbe(Protocol):
    async def probe(self, path: Path) -> MediaInfo: ...

    async def mean_volume(self, path: Path) -> float | None:
        """Nível médio do áudio em dB (None se não der para medir)."""
        ...


class MediaStore(Protocol):
    """Armazenamento local de vinhetas enviadas e de vídeos montados."""

    async def save_upload(self, name: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int: ...

    def asset_path(self, stored_name: str) -> Path: ...

    def has_asset(self, stored_name: str) -> bool:
        """O arquivo existe neste ambiente? (o banco é compartilhado, os arquivos não)"""
        ...

    def result_path(self, job_id: UUID) -> Path: ...

    def relative(self, path: Path) -> str:
        """Caminho guardado no banco: relativo à pasta de mídia (o banco é compartilhado entre ambientes)."""
        ...

    def resolve(self, stored: str) -> Path:
        """Caminho real de um valor guardado (aceita também os absolutos de registros antigos)."""
        ...

    def temp_path(self, job_id: UUID) -> Path: ...

    def main_path(self, job_id: UUID) -> Path: ...

    async def write_stream(self, path: Path, chunks: AsyncIterator[bytes]) -> None: ...

    def remove(self, path: Path) -> None: ...


class VideoComposer(Protocol):
    """Monta abertura + vídeo principal + final num único MP4 (vinhetas mantêm o próprio áudio)."""

    async def compose(
        self, main: Path, intro: Path | None, outro: Path | None, dest: Path,
        music: Path | None = None, music_volume: float = 0.08,
        intro_volume: float = 1.0, outro_volume: float = 1.0, normalize: bool = True,
        music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> None:  # fmt: skip
        """`music`, se houver, toca em loop do início da abertura até o fim do vídeo, com fade-out final."""
        ...
