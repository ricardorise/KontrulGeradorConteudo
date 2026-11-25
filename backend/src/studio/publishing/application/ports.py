from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studio.publishing.domain.publication import Link


class PublishError(Exception):
    """Falha ao enviar o vídeo ao YouTube (arquivo, agente publicador ou recusa da API)."""


@dataclass(frozen=True)
class PublicationMaterial:
    """O que os agentes precisam saber do vídeo (anti-corruption layer sobre render, roteiro e notícia)."""

    script_id: UUID
    topic: str
    script_title: str | None
    paragraphs: list[str]
    news_title: str
    news_summary: str
    news_details: str | None
    links: list[Link] = field(default_factory=list)
    video_name: str = "video.mp4"


class PublicationSource(Protocol):
    async def material(self, render_id: UUID) -> PublicationMaterial | None:
        """None quando o envio não existe ou ainda não tem vídeo pronto."""
        ...


@dataclass(frozen=True)
class PublishRequest:
    render_id: UUID
    title: str
    description: str  # já com os blocos de links
    tags: list[str]
    category_id: str
    language: str
    privacy: str
    notify_subscribers: bool


@dataclass(frozen=True)
class PublishResult:
    video_id: str
    raw: str = ""


class YoutubePublisher(Protocol):
    """Porta de saída: envia o vídeo ao canal do YouTube (hoje pelo agente publicador do Hermes)."""

    async def publish(self, request: PublishRequest) -> PublishResult: ...
