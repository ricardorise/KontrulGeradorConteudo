from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AssetKind(StrEnum):
    INTRO = "intro"  # vinheta de abertura: toca inteira antes de a fala começar
    OUTRO = "outro"  # vinheta final: entra depois do fim da fala
    BACKGROUND = "background"  # vídeo de fundo, em loop sob a fala quando não há B-roll
    MUSIC = "music"  # áudio de fundo (trilha) sob a fala; repete até o fim da narração


@dataclass(frozen=True)
class RenderAsset:
    id: UUID
    kind: AssetKind
    filename: str
    stored_name: str
    size_bytes: int
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    created_at: datetime
    mean_volume_db: float | None = None  # nível médio medido no upload; None = não medido

    @property
    def audio_silent(self) -> bool:
        """Tem faixa de áudio, mas ela está em silêncio (ex.: ~ −91 dB): o ajuste de volume não muda nada."""
        return self.has_audio and self.mean_volume_db is not None and self.mean_volume_db < -70
