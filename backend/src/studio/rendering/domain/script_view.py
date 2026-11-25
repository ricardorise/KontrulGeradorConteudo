from dataclasses import dataclass, field


@dataclass(frozen=True)
class CutForRender:
    paragraph: int  # posição 1-based do parágrafo
    video_id: str
    start: float
    end: float
    excerpt: str | None = None
    excerpt_start: int | None = None


@dataclass(frozen=True)
class ScriptForRender:
    """Visão do roteiro que o contexto de renderização precisa (anti-corruption layer)."""

    title: str | None
    paragraphs: list[str]
    cuts: list[CutForRender] = field(default_factory=list)
