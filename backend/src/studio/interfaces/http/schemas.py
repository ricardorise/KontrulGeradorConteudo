from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from studio.conversation.domain.conversation import ActionOutcome, Conversation, Message
from studio.guidance.domain.guideline import Guideline
from studio.discovery.domain.news_search import NewsItem, NewsSearch
from studio.scripting.domain.config import ScriptProfile
from studio.scripting.domain.script import BrollSuggestion, Cut, Paragraph, Script
from studio.publishing.domain.publication import DESCRIPTION_MAX, PRIVACIES, TITLE_MAX, Publication
from studio.rendering.application.ports import NarrationSettings
from studio.rendering.application.use_cases import RenderPreview
from studio.rendering.domain.asset import RenderAsset
from studio.rendering.domain.render_job import RenderJob
from studio.shared.domain.bots import Bot
from studio.shared.domain.guidance import GuidelineScope


class NewsItemOut(BaseModel):
    id: UUID
    position: int
    title: str
    summary: str
    details: str | None
    source_url: str | None
    published_at: str | None
    radar: dict = Field(default_factory=dict)

    @classmethod
    def of(cls, i: NewsItem) -> "NewsItemOut":
        return cls(**{f: getattr(i, f) for f in cls.model_fields})


class NewsSearchOut(BaseModel):
    id: UUID
    topic: str
    status: str
    error: str | None
    instructions: str | None
    created_at: datetime
    finished_at: datetime | None
    items: list[NewsItemOut]
    report_context: dict = Field(default_factory=dict)

    @classmethod
    def of(cls, s: NewsSearch) -> "NewsSearchOut":
        return cls(
            id=s.id, topic=s.topic, status=s.status.value, error=s.error, instructions=s.instructions, created_at=s.created_at,
            finished_at=s.finished_at, items=[NewsItemOut.of(i) for i in s.items], report_context=s.report_context,
        )  # fmt: skip


class NewsSearchIn(BaseModel):
    radar_scope: str = Field(default="VR/XR", min_length=1, max_length=100)
    window_hours: int = Field(default=72, ge=1, le=168)
    window_end: datetime | None = None
    topic: str = Field(min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=1000)


class BrollOut(BaseModel):
    id: UUID
    video_url: str
    video_id: str
    start_seconds: int | None
    title: str | None
    description: str
    justification: str | None
    source: str  # lumiere | manual

    @classmethod
    def of(cls, b: BrollSuggestion) -> "BrollOut":
        return cls(**{f: getattr(b, f) for f in cls.model_fields})


class ExcerptOut(BaseModel):
    id: UUID
    start: int
    end: int
    text: str


class CutOut(BaseModel):
    id: UUID
    paragraph_id: UUID
    video_id: str
    video_url: str
    video_title: str | None
    start_seconds: float
    end_seconds: float
    duration: float
    created_at: datetime
    excerpt: ExcerptOut | None

    @classmethod
    def of(cls, c: Cut) -> "CutOut":
        data = {f: getattr(c, f) for f in cls.model_fields if f != "excerpt"}
        ex = c.excerpt
        return cls(**data, excerpt=ExcerptOut(id=ex.id, start=ex.start, end=ex.end, text=ex.text) if ex else None)


class CutIn(BaseModel):
    paragraph_id: UUID
    video_url: str = Field(max_length=300)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    video_title: str | None = Field(default=None, max_length=300)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, gt=0)


class CutExcerptIn(BaseModel):
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, gt=0)


class ParagraphOut(BaseModel):
    id: UUID
    position: int
    text: str
    speaker: str | None = None
    broll: list[BrollOut]

    @classmethod
    def of(cls, p: Paragraph) -> "ParagraphOut":
        return cls(id=p.id, position=p.position, text=p.text, speaker=p.speaker, broll=[BrollOut.of(b) for b in p.broll])


class ScriptConfigOut(BaseModel):
    profile_id: str | None
    profile_name: str | None
    duration_minutes: int | None
    max_chars: int | None
    presenters: list[str]


class ScriptOut(BaseModel):
    id: UUID
    news_item_id: UUID
    title: str | None
    status: str
    error: str | None
    broll_status: str
    broll_error: str | None
    instructions: str | None
    config: ScriptConfigOut | None = None
    total_chars: int = 0
    created_at: datetime
    paragraphs: list[ParagraphOut]
    cuts: list[CutOut]

    @classmethod
    def of(cls, s: Script) -> "ScriptOut":
        return cls(
            id=s.id, news_item_id=s.news_item_id, title=s.title, status=s.status.value, error=s.error,
            broll_status=s.broll_status.value, broll_error=s.broll_error, instructions=s.instructions, created_at=s.created_at, total_chars=s.total_chars,
            config=ScriptConfigOut(
                profile_id=s.config.profile_id, profile_name=s.config.profile_name, duration_minutes=s.config.duration_minutes,
                max_chars=s.config.max_chars, presenters=list(s.config.presenters),
            ) if s.config else None,
            paragraphs=[ParagraphOut.of(p) for p in s.paragraphs], cuts=[CutOut.of(c) for c in s.cuts],
        )  # fmt: skip


class ScriptConfigIn(BaseModel):
    """Configuração do roteiro, escolhida antes de gerar."""

    profile_id: str | None = Field(default=None, max_length=60)  # perfil básico (slug) ou cadastrado (uuid)
    duration_minutes: int | None = None  # 5, 8, 12 ou 20 (limite de caracteres correspondente)
    presenters: list[str] = Field(default_factory=list, max_length=2)  # 1 nome (opcional) = um apresentador; 2 = diálogo


class ScriptIn(BaseModel):
    instructions: str | None = Field(default=None, max_length=1000)
    config: ScriptConfigIn | None = None


class ScriptProfileOut(BaseModel):
    id: str
    name: str
    description: str
    instructions: str
    builtin: bool

    @classmethod
    def of(cls, p: "ScriptProfile") -> "ScriptProfileOut":
        return cls(id=p.id, name=p.name, description=p.description, instructions=p.instructions, builtin=p.builtin)


class ScriptProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    instructions: str = Field(min_length=10, max_length=1500)
    description: str = Field(default="", max_length=200)


class DurationOut(BaseModel):
    minutes: int
    max_chars: int


class ScriptOptionsOut(BaseModel):
    profiles: list[ScriptProfileOut]
    durations: list[DurationOut]


class BrollRetryIn(BaseModel):
    instructions: str | None = Field(default=None, max_length=1000)
    paragraph_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)  # vazio/ausente = todos


class BrollIn(BaseModel):
    video_url: str = Field(min_length=1, max_length=300)  # link do YouTube escolhido pelo editor


class ConversationIn(BaseModel):
    bot: Bot


class ScreenContextIn(BaseModel):
    search_id: UUID | None = None
    script_id: UUID | None = None
    publication_id: UUID | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    context: ScreenContextIn = ScreenContextIn()


class ActionOut(BaseModel):
    type: str
    status: str
    label: str
    error: str | None
    refs: dict[str, str]

    @classmethod
    def of(cls, a: ActionOutcome) -> "ActionOut":
        return cls(type=a.type, status=a.status.value, label=a.label, error=a.error, refs=a.refs)


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    status: str
    error: str | None
    created_at: datetime
    actions: list[ActionOut]

    @classmethod
    def of(cls, m: Message) -> "MessageOut":
        return cls(
            id=m.id, role=m.role.value, content=m.content, status=m.status.value, error=m.error,
            created_at=m.created_at, actions=[ActionOut.of(a) for a in m.actions],
        )  # fmt: skip


class ConversationOut(BaseModel):
    id: UUID
    bot: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]

    @classmethod
    def of(cls, c: Conversation) -> "ConversationOut":
        return cls(
            id=c.id, bot=c.bot.value, title=c.title, created_at=c.created_at, updated_at=c.updated_at,
            messages=[MessageOut.of(m) for m in c.messages],
        )  # fmt: skip


class GuidelineIn(BaseModel):
    scope: GuidelineScope
    text: str = Field(min_length=1, max_length=300)


class GuidelineActiveIn(BaseModel):
    active: bool


class GuidelineOut(BaseModel):
    id: UUID
    scope: str
    text: str
    active: bool
    source: str
    created_at: datetime

    @classmethod
    def of(cls, g: Guideline) -> "GuidelineOut":
        return cls(id=g.id, scope=g.scope.value, text=g.text, active=g.active, source=g.source.value, created_at=g.created_at)


class NarrationIO(BaseModel):
    """Voz da narração (nó PapoNarration). Limites iguais aos de GET /object_info/PapoNarration."""

    provedor: str = Field(default="ElevenLabs", pattern="^(VoiceStudio|ElevenLabs)$")
    voz_elevenlabs: str = Field(default="", max_length=120)  # vazio = voz padrão do servidor
    modelo_elevenlabs: str = Field(default="eleven_multilingual_v2", pattern="^(eleven_multilingual_v2|eleven_flash_v2_5)$")
    velocidade_elevenlabs: float = Field(default=1.08, ge=0.7, le=1.2)
    estabilidade_elevenlabs: float = Field(default=0.30, ge=0, le=1)
    similaridade_elevenlabs: float = Field(default=0.73, ge=0, le=1)
    estilo_elevenlabs: float = Field(default=0.74, ge=0, le=1)
    idioma_elevenlabs: str = Field(default="pt", min_length=2, max_length=12)

    def to_domain(self) -> NarrationSettings:
        return NarrationSettings(**self.model_dump())

    @classmethod
    def of(cls, n: NarrationSettings) -> "NarrationIO":
        return cls(**asdict(n))


class RenderIn(BaseModel):
    narration: NarrationIO | None = None  # None = mantém a voz do workflow
    background: str | None = Field(default=None, max_length=300)
    intro_asset_id: UUID | None = None  # vinheta de abertura (a fala só começa depois dela)
    outro_asset_id: UUID | None = None  # vinheta final
    music_asset_id: UUID | None = None  # áudio de fundo (trilha)
    music_volume: float | None = Field(default=None, ge=0, le=1)  # nível do áudio de fundo na fala
    music_intro_volume: float | None = Field(default=None, ge=0, le=1)  # ... na abertura (vazio = igual ao da fala)
    music_outro_volume: float | None = Field(default=None, ge=0, le=1)  # ... no final
    background_asset_id: UUID | None = None  # vídeo de background enviado (substitui o caminho do servidor)
    intro_volume: float = Field(default=1.0, ge=0, le=1.5)
    outro_volume: float = Field(default=1.0, ge=0, le=1.5)
    background_volume: float = Field(default=0.0, ge=0, le=1.5)  # áudio do vídeo de background (0 = sem som)
    normalize_vignettes: bool = True  # nivela o loudness das vinhetas com a fala antes do ajuste


class RenderRemixIn(BaseModel):
    intro_asset_id: UUID | None = None
    outro_asset_id: UUID | None = None
    music_asset_id: UUID | None = None
    music_volume: float | None = Field(default=None, ge=0, le=1)
    music_intro_volume: float | None = Field(default=None, ge=0, le=1)
    music_outro_volume: float | None = Field(default=None, ge=0, le=1)
    intro_volume: float = Field(default=1.0, ge=0, le=1.5)
    outro_volume: float = Field(default=1.0, ge=0, le=1.5)
    normalize_vignettes: bool = True


class EditLineOut(BaseModel):
    order: int
    paragraph: int
    text: str
    phrase: str


class RenderPreviewOut(BaseModel):
    background: str
    roteiro_chars: int
    edit_list: str
    lines: list[EditLineOut]
    problems: list[str]
    can_send: bool
    music_volume: float
    background_volume_supported: bool
    narration: NarrationIO  # valores atuais do nó PapoNarration (ponto de partida da tela)

    @classmethod
    def of(cls, preview: "RenderPreview") -> "RenderPreviewOut":
        plan = preview.plan
        return cls(
            background=preview.background, roteiro_chars=len(plan.roteiro), edit_list=plan.edit_list,
            lines=[EditLineOut(order=l.order, paragraph=l.paragraph, text=l.render(), phrase=l.phrase) for l in plan.lines],
            problems=plan.problems, can_send=not plan.problems, music_volume=preview.music_volume,
            background_volume_supported=preview.background_volume_supported,
            narration=NarrationIO.of(preview.narration),
        )  # fmt: skip


class RenderOut(BaseModel):
    id: UUID
    script_id: UUID
    status: str
    queued: bool
    prompt_id: str | None
    background: str
    edit_list: str
    error: str | None
    has_video: bool
    video_name: str | None
    stage: str
    intro_asset_id: UUID | None
    outro_asset_id: UUID | None
    music_asset_id: UUID | None
    music_volume: float | None
    music_intro_volume: float | None
    music_outro_volume: float | None
    background_asset_id: UUID | None
    intro_volume: float
    outro_volume: float
    background_volume: float
    normalize_vignettes: bool
    can_remix: bool
    music_baked: bool
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def of(cls, j: RenderJob) -> "RenderOut":
        return cls(
            id=j.id, script_id=j.script_id, status=j.status.value, queued=j.queued, prompt_id=j.prompt_id,
            background=j.background, edit_list=j.edit_list, error=j.error, has_video=j.output is not None,
            video_name=j.output.filename if j.output else None, stage=j.stage,
            intro_asset_id=j.intro_asset_id, outro_asset_id=j.outro_asset_id,
            music_asset_id=j.music_asset_id, music_volume=j.music_volume,
            music_intro_volume=j.music_intro_volume, music_outro_volume=j.music_outro_volume,
            background_asset_id=j.background_asset_id, intro_volume=j.intro_volume, outro_volume=j.outro_volume,
            background_volume=j.background_volume, normalize_vignettes=j.normalize_vignettes,
            can_remix=j.can_remix, music_baked=j.music_is_baked, created_at=j.created_at, finished_at=j.finished_at,
        )  # fmt: skip


class RenderAssetOut(BaseModel):
    id: UUID
    kind: str
    filename: str
    size_bytes: int
    duration: float
    width: int
    height: int
    has_audio: bool
    audio_silent: bool
    mean_volume_db: float | None
    available: bool  # o arquivo existe neste ambiente
    created_at: datetime

    @classmethod
    def of(cls, a: RenderAsset, available: bool = True) -> "RenderAssetOut":
        return cls(
            id=a.id, kind=a.kind.value, filename=a.filename, size_bytes=a.size_bytes, duration=a.duration,
            width=a.width, height=a.height, has_audio=a.has_audio, audio_silent=a.audio_silent,
            mean_volume_db=a.mean_volume_db, available=available, created_at=a.created_at,
        )  # fmt: skip


class LinkIO(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=500)
    kind: str = Field(default="source", pattern="^(source|broll)$")


class PublicationOut(BaseModel):
    id: UUID
    render_id: UUID
    script_id: UUID
    status: str
    title: str
    title_alternatives: list[str]
    description: str
    tags: list[str]
    links: list[LinkIO]
    full_description: str  # exatamente o texto que irá ao YouTube
    description_chars: int
    privacy: str
    allowed_privacies: list[str]
    category_id: str
    language: str
    notify_subscribers: bool
    rationale: str | None
    error: str | None
    error_stage: str | None
    problems: list[str]
    can_publish: bool
    video_id: str | None
    video_url: str | None
    limits: dict[str, int]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    @classmethod
    def of(cls, p: Publication) -> "PublicationOut":
        problems = p.problems() if p.status.value == "ready" else []
        return cls(
            id=p.id, render_id=p.render_id, script_id=p.script_id, status=p.status.value, title=p.title,
            title_alternatives=p.title_alternatives, description=p.description, tags=p.tags,
            links=[LinkIO(label=l.label, url=l.url, kind=l.kind) for l in p.links], full_description=p.full_description,
            description_chars=len(p.full_description), privacy=p.privacy, allowed_privacies=list(PRIVACIES),
            category_id=p.category_id, language=p.language, notify_subscribers=p.notify_subscribers,
            rationale=p.rationale, error=p.error, error_stage=p.error_stage, problems=problems,
            can_publish=p.status.value == "ready" and not problems, video_id=p.video_id, video_url=p.video_url,
            limits={"title": TITLE_MAX, "description": DESCRIPTION_MAX}, created_at=p.created_at,
            updated_at=p.updated_at, published_at=p.published_at,
        )  # fmt: skip


class PreparePublicationIn(BaseModel):
    force: bool = False  # cria um novo rascunho mesmo havendo um para este vídeo


class PublicationEditIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    tags: list[str] | None = Field(default=None, max_length=60)
    links: list[LinkIO] | None = Field(default=None, max_length=60)
    privacy: str | None = None
    notify_subscribers: bool | None = None


class PublicationReviseIn(BaseModel):
    target: str = Field(default="all", pattern="^(title|description|tags|all)$")
    instructions: str = Field(min_length=3, max_length=1000)


class PublicationPublishIn(BaseModel):
    confirm: bool = False  # precisa ser true: a publicação só ocorre por decisão explícita do editor
