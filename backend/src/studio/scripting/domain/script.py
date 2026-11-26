import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from studio.scripting.domain.config import ScriptConfig
from studio.shared.domain.clock import utcnow
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CLOCK = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")


def parse_youtube_url(url: str) -> tuple[str, int | None] | None:
    """Devolve (video_id, início em segundos) se for um link válido de vídeo do YouTube."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in _YOUTUBE_HOSTS:
        return None
    query = parse_qs(parsed.query)
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
        video_id = parsed.path.split("/")[2] if parsed.path.count("/") >= 2 else ""
    else:
        video_id = (query.get("v") or [""])[0]
    if not _VIDEO_ID.match(video_id):
        return None
    fragment = parse_qs(parsed.fragment)
    raw_start = (query.get("t") or query.get("start") or fragment.get("t") or fragment.get("start") or [""])[0]
    return video_id, _seconds(raw_start)


def _seconds(raw: str) -> int | None:
    raw = str(raw).strip().lower()
    if re.fullmatch(r"\d+(?::[0-5]\d){1,2}", raw):
        total = 0
        for part in raw.split(":"):
            total = total * 60 + int(part)
        return total
    match = _CLOCK.match(raw) if raw else None
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class BrollSuggestion:
    id: UUID
    video_url: str
    video_id: str
    description: str
    start_seconds: int | None = None
    title: str | None = None
    justification: str | None = None
    source: str = "lumiere"  # "lumiere" (automática) ou "manual" (escolhida pelo editor)

    @property
    def is_manual(self) -> bool:
        return self.source == "manual"

    @classmethod
    def manual(
        cls, url: str, title: str | None = None, description: str | None = None, keep_id: UUID | None = None
    ) -> "BrollSuggestion":
        """Vídeo escolhido pelo editor (colado como link do YouTube)."""
        parsed = parse_youtube_url(url)
        if parsed is None:
            raise InvalidInput("Cole um link válido de vídeo do YouTube (youtube.com/watch?v=… ou youtu.be/…).")
        video_id, start = parsed
        title = (title or "").strip() or None
        return cls(
            id=keep_id or uuid4(), video_url=f"https://youtu.be/{video_id}" + (f"?t={start}" if start is not None else ""),
            video_id=video_id, description=(description or "").strip() or title or "Vídeo escolhido por você",
            start_seconds=start, title=title, justification="Escolhido manualmente", source="manual",
        )  # fmt: skip

    @classmethod
    def from_scene(
        cls, url: str, description: str, title: str | None = None, justification: str | None = None,
        start_seconds: object = None
    ) -> "BrollSuggestion | None":
        parsed = parse_youtube_url(url)
        if parsed is None or not description.strip():
            return None
        video_id, start = parsed
        # An explicit structured timestamp takes precedence; invalid values never erase a valid URL timestamp.
        explicit = _seconds(str(start_seconds)) if not isinstance(start_seconds, bool) else None
        if explicit is not None:
            start = explicit
        link = f"https://youtu.be/{video_id}" + (f"?t={start}" if start is not None else "")
        return cls(
            id=uuid4(),
            video_url=link,
            video_id=video_id,
            start_seconds=start,
            title=title or None,
            description=description.strip(),
            justification=justification or None,
        )


MIN_CUT_SECONDS = 0.5
MAX_CUTS = 100
MAX_BROLL_PER_PARAGRAPH = 12


@dataclass(frozen=True)
class Excerpt:
    """Trecho [start, end) do texto de um parágrafo (offsets em caracteres) vinculado a um corte."""

    id: UUID
    paragraph_id: UUID
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Cut:
    """Trecho [início, fim] de um vídeo do YouTube escolhido para ilustrar um parágrafo."""

    id: UUID
    paragraph_id: UUID
    video_id: str
    video_url: str
    start_seconds: float
    end_seconds: float
    created_at: datetime
    video_title: str | None = None
    excerpt: Excerpt | None = None

    @property
    def duration(self) -> float:
        return round(self.end_seconds - self.start_seconds, 1)


@dataclass
class Paragraph:
    id: UUID
    position: int
    text: str
    broll: list[BrollSuggestion] = field(default_factory=list)
    speaker: str | None = None  # apresentador que fala o parágrafo (roteiro com dois apresentadores)


@dataclass
class Script:
    """Agregado: roteiro de uma notícia (Jules Verne) com B-roll por parágrafo (Lumière)."""

    id: UUID
    news_item_id: UUID
    status: JobStatus
    created_at: datetime
    broll_status: JobStatus = JobStatus.PENDING
    title: str | None = None
    error: str | None = None
    broll_error: str | None = None
    finished_at: datetime | None = None
    instructions: str | None = None
    config: ScriptConfig | None = None  # perfil, tempo e apresentadores usados neste roteiro
    extra_news_item_ids: list[UUID] = field(default_factory=list)  # notícias agregadas (merge) além da principal
    paragraphs: list[Paragraph] = field(default_factory=list)
    cuts: list[Cut] = field(default_factory=list)

    @classmethod
    def start(
        cls, news_item_id: UUID, instructions: str | None = None, config: ScriptConfig | None = None,
        extra_news_item_ids: list[UUID] | None = None,
    ) -> "Script":
        return cls(
            id=uuid4(), news_item_id=news_item_id, status=JobStatus.RUNNING, created_at=utcnow(),
            instructions=(instructions or "").strip() or None, config=config if config and not config.is_empty else None,
            extra_news_item_ids=list(extra_news_item_ids or []),
        )

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.paragraphs)

    def complete(self, title: str | None, texts: list[str], speakers: list[str | None] | None = None) -> None:
        pairs = [(t.strip(), speakers[i] if speakers and i < len(speakers) else None) for i, t in enumerate(texts) if t and t.strip()]
        if not pairs:
            raise InvalidInput("O roteiro não tem parágrafos.")
        self.title = title
        self.paragraphs = [Paragraph(id=uuid4(), position=i, text=t, speaker=s) for i, (t, s) in enumerate(pairs)]
        self.status = JobStatus.DONE
        self.error = None
        self.finished_at = utcnow()

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.finished_at = utcnow()

    def add_cut(
        self,
        paragraph_id: UUID,
        video_url: str,
        start: float,
        end: float,
        video_title: str | None = None,
        text_range: tuple[int, int] | None = None,
    ) -> Cut:
        paragraph = next((p for p in self.paragraphs if p.id == paragraph_id), None)
        if paragraph is None:
            raise NotFound("Parágrafo não pertence a este roteiro.")
        excerpt = self._excerpt_for(paragraph, text_range)
        parsed = parse_youtube_url(video_url)
        if parsed is None:
            raise InvalidInput("Link do YouTube inválido.")
        start, end = round(float(start), 1), round(float(end), 1)
        if start < 0 or end <= start:
            raise InvalidInput("O fim do corte deve ser maior que o início.")
        if end - start < MIN_CUT_SECONDS:
            raise InvalidInput(f"O corte deve ter pelo menos {MIN_CUT_SECONDS}s.")
        if len(self.cuts) >= MAX_CUTS:
            raise Conflict(f"Limite de {MAX_CUTS} cortes por roteiro.")
        video_id, _ = parsed
        if any(c.paragraph_id == paragraph_id and c.video_id == video_id and c.start_seconds == start
               and c.end_seconds == end for c in self.cuts):
            raise Conflict("Este corte já está na lista.")
        cut = Cut(
            id=uuid4(), paragraph_id=paragraph_id, video_id=video_id, video_url=f"https://youtu.be/{video_id}",
            start_seconds=start, end_seconds=end, created_at=utcnow(), video_title=(video_title or "").strip() or None,
            excerpt=excerpt,
        )  # fmt: skip
        self.cuts.append(cut)
        return cut

    def _excerpt_for(
        self, paragraph: Paragraph, text_range: tuple[int, int] | None, ignore_cut: UUID | None = None
    ) -> Excerpt | None:
        """Valida o trecho de texto escolhido; trechos de cortes diferentes não podem se sobrepor."""
        if text_range is None:
            return None
        start, end = text_range
        if not (0 <= start < end <= len(paragraph.text)):
            raise InvalidInput("O trecho de texto está fora do parágrafo.")
        text = paragraph.text[start:end]
        if not text.strip():
            raise InvalidInput("O trecho de texto selecionado está vazio.")
        for other in self.cuts:
            if other.id == ignore_cut:
                continue
            ex = other.excerpt
            if ex and ex.paragraph_id == paragraph.id and start < ex.end and ex.start < end:
                raise Conflict(f"Esse trecho do texto já está ligado a outro corte: “{ex.text.strip()[:60]}”.")
        return Excerpt(id=uuid4(), paragraph_id=paragraph.id, start=start, end=end, text=text)

    def set_cut_excerpt(self, cut_id: UUID, text_range: tuple[int, int] | None) -> Cut:
        """Troca (ou remove, com None) o trecho de texto de um corte já existente."""
        index = next((i for i, c in enumerate(self.cuts) if c.id == cut_id), None)
        if index is None:
            raise NotFound("Corte não encontrado.")
        cut = self.cuts[index]
        paragraph = next(p for p in self.paragraphs if p.id == cut.paragraph_id)
        updated = replace(cut, excerpt=self._excerpt_for(paragraph, text_range, ignore_cut=cut_id))
        self.cuts[index] = updated
        return updated

    def remove_cut(self, cut_id: UUID) -> None:
        if not any(c.id == cut_id for c in self.cuts):
            raise NotFound("Corte não encontrado.")
        self.cuts = [c for c in self.cuts if c.id != cut_id]

    # ---- B-roll escolhido pelo editor ----
    def _paragraph(self, paragraph_id: UUID) -> Paragraph:
        found = next((p for p in self.paragraphs if p.id == paragraph_id), None)
        if found is None:
            raise NotFound("Parágrafo não pertence a este roteiro.")
        return found

    def add_manual_broll(self, paragraph_id: UUID, url: str, title: str | None = None) -> BrollSuggestion:
        paragraph = self._paragraph(paragraph_id)
        suggestion = BrollSuggestion.manual(url, title)
        if any(b.video_url == suggestion.video_url for b in paragraph.broll):
            raise Conflict("Este vídeo já está neste parágrafo.")
        if len(paragraph.broll) >= MAX_BROLL_PER_PARAGRAPH:
            raise Conflict(f"Limite de {MAX_BROLL_PER_PARAGRAPH} vídeos por parágrafo.")
        paragraph.broll.append(suggestion)
        return suggestion

    def _find_broll(self, broll_id: UUID) -> tuple[Paragraph, int]:
        for paragraph in self.paragraphs:
            for index, item in enumerate(paragraph.broll):
                if item.id == broll_id:
                    return paragraph, index
        raise NotFound("Vídeo não encontrado neste roteiro.")

    def replace_broll(self, broll_id: UUID, url: str, title: str | None = None) -> BrollSuggestion:
        """Troca o vídeo de uma sugestão (mantém o lugar e o id); passa a contar como escolhida pelo editor."""
        paragraph, index = self._find_broll(broll_id)
        suggestion = BrollSuggestion.manual(url, title, keep_id=broll_id)
        if any(b.video_url == suggestion.video_url and b.id != broll_id for b in paragraph.broll):
            raise Conflict("Este vídeo já está neste parágrafo.")
        paragraph.broll[index] = suggestion
        return suggestion

    def remove_broll(self, broll_id: UUID) -> None:
        paragraph, index = self._find_broll(broll_id)
        del paragraph.broll[index]

    def used_video_ids(self) -> list[str]:
        return sorted({b.video_id for p in self.paragraphs for b in p.broll})

    def begin_broll(self, paragraph_ids: set[UUID] | None = None) -> list[Paragraph]:
        """Inicia a (re)busca; devolve os parágrafos-alvo (todos ou só os escolhidos).

        Não apaga nada: as sugestões atuais só são trocadas quando houver cenas novas.
        """
        if self.status is not JobStatus.DONE:
            raise Conflict("O roteiro ainda não está pronto para buscar B-roll.")
        if self.broll_status is JobStatus.RUNNING:
            raise Conflict("A busca de B-roll já está em andamento.")
        targets = list(self.paragraphs)
        if paragraph_ids is not None:
            unknown = paragraph_ids - {p.id for p in self.paragraphs}
            if unknown or not paragraph_ids:
                raise InvalidInput("Escolha ao menos um parágrafo deste roteiro para rebuscar.")
            targets = [p for p in self.paragraphs if p.id in paragraph_ids]
        self.broll_status = JobStatus.RUNNING
        self.broll_error = None
        return targets

    def complete_broll(self, scenes: dict[int, list[BrollSuggestion]], targets: set[int] | None = None) -> None:
        """Aplica as cenas novas aos parágrafos-alvo: as escolhidas pelo editor ficam; as automáticas são trocadas
        quando há cena nova (sem cena nova, as atuais permanecem)."""
        for paragraph in self.paragraphs:
            if targets is not None and paragraph.position not in targets:
                continue
            fresh = scenes.get(paragraph.position)
            if fresh:
                paragraph.broll = [b for b in paragraph.broll if b.is_manual] + fresh
        self.broll_status = JobStatus.DONE

    def fail_broll(self, error: str) -> None:
        self.broll_status = JobStatus.FAILED
        self.broll_error = error
