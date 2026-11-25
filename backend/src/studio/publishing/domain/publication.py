import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import Conflict, InvalidInput

TITLE_MAX = 100
DESCRIPTION_MAX = 5000
MAX_TAGS = 20
TAGS_MAX_CHARS = 450  # o limite do YouTube é 500 contando separadores
# A política do Hermes recusa "público": um humano torna o vídeo público no YouTube Studio.
PRIVACIES = ("private", "unlisted")
_ANGLE = re.compile(r"[<>]")  # o YouTube rejeita < e > em título e descrição
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class PublicationStatus(StrEnum):
    DRAFTING = "drafting"  # o Jules Verne / Youtoba estão trabalhando (geração ou revisão)
    READY = "ready"  # pronto para revisar e publicar
    PUBLISHING = "publishing"  # enviando ao YouTube
    PUBLISHED = "published"
    FAILED = "failed"  # só a geração inicial; falhas de revisão/publicação voltam a READY com `error`


@dataclass(frozen=True)
class Link:
    label: str
    url: str
    kind: str = "source"  # source = fonte da notícia | broll = vídeo usado nas cenas


def clean_text(value: str) -> str:
    return _ANGLE.sub(" ", value).strip()


def normalize_tags(raw: list[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    total = 0
    for tag in raw:
        tag = _ANGLE.sub("", str(tag)).strip().lstrip("#").strip().replace(",", " ")
        tag = " ".join(tag.split())
        if not tag or tag.lower() in seen or len(tag) > 100:
            continue
        if len(tags) >= MAX_TAGS or total + len(tag) + 1 > TAGS_MAX_CHARS:
            break
        seen.add(tag.lower())
        tags.append(tag)
        total += len(tag) + 1
    return tags


def clip_title(title: str) -> str:
    title = " ".join(clean_text(title).split())
    if len(title) <= TITLE_MAX:
        return title
    cut = title[:TITLE_MAX].rsplit(" ", 1)[0]
    return cut if len(cut) >= 40 else title[:TITLE_MAX]


def compose_description(body: str, links: list[Link]) -> str:
    """Texto final enviado ao YouTube: descrição + blocos de links (fontes e créditos das cenas)."""
    parts = [body.strip()]
    sources = [l for l in links if l.kind == "source"]
    scenes = [l for l in links if l.kind == "broll"]
    if sources:
        parts.append("Fontes:\n" + "\n".join(f"• {l.label} — {l.url}" for l in sources))
    if scenes:
        parts.append("Vídeos usados nas cenas:\n" + "\n".join(f"• {l.label} — {l.url}" for l in scenes))
    return "\n\n".join(p for p in parts if p)


@dataclass
class Publication:
    """Agregado: rascunho de publicação do vídeo renderizado no canal do YouTube."""

    id: UUID
    render_id: UUID
    script_id: UUID
    status: PublicationStatus
    created_at: datetime
    updated_at: datetime
    title: str = ""
    title_alternatives: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    privacy: str = "private"
    category_id: str = "28"  # Ciência e Tecnologia
    language: str = "pt"
    notify_subscribers: bool = False
    rationale: str | None = None
    error: str | None = None
    error_stage: str | None = None  # generation | revision | publish
    video_id: str | None = None
    video_url: str | None = None
    published_at: datetime | None = None

    @classmethod
    def start(cls, render_id: UUID, script_id: UUID, links: list[Link]) -> "Publication":
        now = utcnow()
        return cls(uuid4(), render_id, script_id, PublicationStatus.DRAFTING, now, now, links=links)

    @property
    def full_description(self) -> str:
        return compose_description(self.description, self.links)

    def _touch(self) -> None:
        self.updated_at = utcnow()

    def _require_editable(self) -> None:
        if self.status is PublicationStatus.DRAFTING:
            raise Conflict("O rascunho está sendo gerado ou revisado; aguarde terminar.")
        if self.status is PublicationStatus.PUBLISHING:
            raise Conflict("O vídeo está sendo enviado ao YouTube.")
        if self.status is PublicationStatus.PUBLISHED:
            raise Conflict("Este vídeo já foi publicado; altere-o no YouTube Studio.")
        if self.status is PublicationStatus.FAILED:
            raise Conflict("A geração falhou; use \"Gerar de novo\".")

    # ---- geração e revisão pelos agentes ----
    def begin_generation(self) -> None:
        if self.status in (PublicationStatus.PUBLISHING, PublicationStatus.PUBLISHED, PublicationStatus.DRAFTING):
            raise Conflict("Não é possível gerar de novo agora.")
        self.status, self.error, self.error_stage = PublicationStatus.DRAFTING, None, None
        self._touch()

    def apply_generated(
        self, title: str, alternatives: list[str], description: str, tags: list[str], rationale: str | None
    ) -> None:  # fmt: skip
        title = clip_title(title)
        if not title or not description.strip():
            raise InvalidInput("Título ou descrição vazios.")
        self.title = title
        self.title_alternatives = [t for t in dict.fromkeys(clip_title(a) for a in alternatives) if t and t != title][:5]
        self.description = clean_text(description)
        self.tags, self.rationale = normalize_tags(tags), rationale
        self.status, self.error, self.error_stage = PublicationStatus.READY, None, None
        self._touch()

    def begin_revision(self) -> None:
        self._require_editable()
        self.status, self.error, self.error_stage = PublicationStatus.DRAFTING, None, None
        self._touch()

    def apply_revision(
        self, title: str | None = None, alternatives: list[str] | None = None, description: str | None = None,
        tags: list[str] | None = None, rationale: str | None = None,
    ) -> None:  # fmt: skip
        if title is not None:
            self.title = clip_title(title) or self.title
            if alternatives is not None:
                self.title_alternatives = [t for t in dict.fromkeys(clip_title(a) for a in alternatives) if t and t != self.title][:5]
        if description is not None and description.strip():
            self.description = clean_text(description)
        if tags is not None:
            self.tags = normalize_tags(tags)
        if rationale:
            self.rationale = rationale
        self.status, self.error, self.error_stage = PublicationStatus.READY, None, None
        self._touch()

    def fail(self, error: str, stage: str) -> None:
        """Geração inicial falha => FAILED; revisão/publicação falham => volta a READY mantendo o rascunho."""
        self.error, self.error_stage = error, stage
        self.status = PublicationStatus.FAILED if stage == "generation" else PublicationStatus.READY
        self._touch()

    # ---- edição manual ----
    def edit(
        self, title: str | None = None, description: str | None = None, tags: list[str] | None = None,
        links: list[Link] | None = None, privacy: str | None = None, notify_subscribers: bool | None = None,
    ) -> None:  # fmt: skip
        self._require_editable()
        before = (self.title, self.description, self.tags, self.links, self.privacy, self.notify_subscribers)
        try:
            self._apply_edit(title, description, tags, links, privacy, notify_subscribers)
        except InvalidInput:
            self.title, self.description, self.tags, self.links, self.privacy, self.notify_subscribers = before  # atômico
            raise
        self.error, self.error_stage = None, None
        self._touch()

    def _apply_edit(
        self, title: str | None, description: str | None, tags: list[str] | None, links: list[Link] | None,
        privacy: str | None, notify_subscribers: bool | None,
    ) -> None:  # fmt: skip
        if title is not None:
            clean = " ".join(clean_text(title).split())
            if not clean:
                raise InvalidInput("O título não pode ficar vazio.")
            if len(clean) > TITLE_MAX:
                raise InvalidInput(f"O título deve ter no máximo {TITLE_MAX} caracteres (tem {len(clean)}).")
            self.title = clean
        if description is not None:
            self.description = clean_text(description)
        if tags is not None:
            self.tags = normalize_tags(tags)
        if links is not None:
            self.links = [l for l in links if l.url.startswith(("http://", "https://"))]
        if privacy is not None:
            if privacy not in PRIVACIES:
                raise InvalidInput("Privacidade inválida. A política do Hermes só permite 'private' ou 'unlisted'; "
                                   "para tornar público, use o YouTube Studio depois.")
            self.privacy = privacy
        if notify_subscribers is not None:
            self.notify_subscribers = notify_subscribers
        if len(self.full_description) > DESCRIPTION_MAX:
            raise InvalidInput(
                f"A descrição (com os links) passa de {DESCRIPTION_MAX} caracteres ({len(self.full_description)}). Encurte-a ou remova links."
            )

    # ---- publicação ----
    def problems(self) -> list[str]:
        out = []
        if not self.title.strip():
            out.append("Falta o título.")
        if not self.description.strip():
            out.append("Falta a descrição.")
        if len(self.full_description) > DESCRIPTION_MAX:
            out.append(f"A descrição passa de {DESCRIPTION_MAX} caracteres.")
        if self.privacy not in PRIVACIES:
            out.append("Privacidade inválida.")
        return out

    def begin_publish(self) -> None:
        self._require_editable()
        problems = self.problems()
        if problems:
            raise InvalidInput(" ".join(problems))
        self.status, self.error, self.error_stage = PublicationStatus.PUBLISHING, None, None
        self._touch()

    def mark_published(self, video_id: str) -> None:
        if not _VIDEO_ID.match(video_id):
            raise InvalidInput("Identificador de vídeo inválido devolvido pelo publicador.")
        self.video_id, self.video_url = video_id, f"https://youtu.be/{video_id}"
        self.status, self.error, self.error_stage = PublicationStatus.PUBLISHED, None, None
        self.published_at = utcnow()
        self._touch()
