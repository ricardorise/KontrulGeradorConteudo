"""Configuração do roteiro: perfil do roteirista, tempo (limite de caracteres) e apresentadores."""

from dataclasses import dataclass
from uuid import uuid4

from studio.shared.domain.errors import InvalidInput

# minutos do vídeo -> limite de caracteres do roteiro
DURATIONS: dict[int, int] = {5: 630, 8: 800, 12: 1200, 20: 2000}
LENGTH_TOLERANCE = 1.05  # o texto pode passar até 5% do limite; acima disso o roteirista refaz
MAX_PROFILE_NAME = 60
MAX_PROFILE_INSTRUCTIONS = 1500
MAX_PRESENTER_NAME = 40
MAX_THEME = 200
MAX_EXTRA_NEWS = 5  # notícias agregadas além da principal


@dataclass(frozen=True)
class ScriptProfile:
    id: str  # slug nos perfis básicos, uuid nos cadastrados
    name: str
    description: str
    instructions: str  # o que o roteirista deve seguir (vai no prompt)
    builtin: bool = False
    created_at: object = None

    @classmethod
    def create(cls, name: str, instructions: str, description: str = "") -> "ScriptProfile":
        name, instructions, description = name.strip(), instructions.strip(), description.strip()
        if not name or len(name) > MAX_PROFILE_NAME:
            raise InvalidInput(f"Dê um nome ao perfil (até {MAX_PROFILE_NAME} caracteres).")
        if len(instructions) < 10 or len(instructions) > MAX_PROFILE_INSTRUCTIONS:
            raise InvalidInput(f"Descreva como o roteirista deve escrever (10 a {MAX_PROFILE_INSTRUCTIONS} caracteres).")
        if name.lower() in {p.name.lower() for p in BUILTIN_PROFILES}:
            raise InvalidInput("Já existe um perfil básico com esse nome.")
        return cls(id=str(uuid4()), name=name, description=description[:200], instructions=instructions)


BUILTIN_PROFILES: tuple[ScriptProfile, ...] = (
    ScriptProfile(
        "jornalistico", "Jornalístico & Investigativo", "Factual, apurado, com contexto e contraponto.",
        "Tom sério, factual e apurado. Abra com o fato central (lide), contextualize, apresente os dados e as fontes "
        "citadas no material e mostre os diferentes lados. Separe o que está confirmado do que é alegação. "
        "Sem sensacionalismo e sem adjetivos de opinião.",
        builtin=True,
    ),
    ScriptProfile(
        "storytelling", "Storytelling & Curiosidades", "Narrativa envolvente, gancho e curiosidades.",
        "Conte como uma história: gancho forte na abertura, contexto como cenário, tensão ou virada no meio e um "
        "fechamento que amarra a ideia. Destaque curiosidades e detalhes surpreendentes do material, com linguagem "
        "viva, ritmo e frases curtas.",
        builtin=True,
    ),
    ScriptProfile(
        "tech", "Tech & Analítico", "Explicação técnica clara, comparações e implicações.",
        "Explique de forma técnica e clara: o que é, como funciona, números e especificações do material, comparações "
        "com alternativas, prós e contras e o que isso muda para o público. Traduza termos difíceis em uma frase.",
        builtin=True,
    ),
    ScriptProfile(
        "opiniao", "Opinião & Debate Construtivo", "Posicionamento claro, argumentos dos dois lados.",
        "Assuma um ponto de vista claro e deixe explícito que é opinião. Apresente os melhores argumentos de cada lado, "
        "com respeito, sem atacar pessoas ou grupos, e termine convidando o público a debater.",
        builtin=True,
    ),
)


def builtin_profile(profile_id: str) -> ScriptProfile | None:
    return next((p for p in BUILTIN_PROFILES if p.id == profile_id), None)


@dataclass(frozen=True)
class ScriptConfig:
    """Escolhas do editor antes de gerar o roteiro. É guardada junto do roteiro (o que foi usado)."""

    profile_id: str | None = None
    profile_name: str | None = None
    profile_instructions: str | None = None
    duration_minutes: int | None = None
    max_chars: int | None = None
    presenters: tuple[str, ...] = ()  # vazio/um nome = um apresentador; dois nomes = diálogo
    theme: str | None = None  # assunto/tema do vídeo definido pelo editor (principalmente ao agregar notícias)

    @classmethod
    def build(
        cls, profile: ScriptProfile | None = None, duration_minutes: int | None = None, presenters: list[str] | None = None,
        theme: str | None = None,
    ) -> "ScriptConfig":
        if duration_minutes is not None and duration_minutes not in DURATIONS:
            raise InvalidInput("Tempo inválido. Escolha " + ", ".join(f"{m} min" for m in DURATIONS) + ".")
        names = tuple(" ".join(n.split()) for n in (presenters or []))
        if len(names) > 2 or any(not n for n in names) and len(names) == 2:
            raise InvalidInput("Informe o nome dos dois apresentadores.")
        names = tuple(n for n in names if n)
        if any(len(n) > MAX_PRESENTER_NAME for n in names):
            raise InvalidInput(f"Nome de apresentador com até {MAX_PRESENTER_NAME} caracteres.")
        if len(names) == 2 and names[0].lower() == names[1].lower():
            raise InvalidInput("Os dois apresentadores precisam ter nomes diferentes.")
        theme = " ".join((theme or "").split()) or None
        if theme and len(theme) > MAX_THEME:
            raise InvalidInput(f"Assunto/tema com até {MAX_THEME} caracteres.")
        return cls(
            profile.id if profile else None, profile.name if profile else None, profile.instructions if profile else None,
            duration_minutes, DURATIONS[duration_minutes] if duration_minutes else None, names, theme,
        )  # fmt: skip

    @property
    def is_dialogue(self) -> bool:
        return len(self.presenters) == 2

    @property
    def is_empty(self) -> bool:
        return not (self.profile_id or self.duration_minutes or self.presenters or self.theme)

    def fits(self, total_chars: int) -> bool:
        return self.max_chars is None or total_chars <= self.max_chars * LENGTH_TOLERANCE

    def to_json(self) -> dict:
        return {
            "profile_id": self.profile_id, "profile_name": self.profile_name, "profile_instructions": self.profile_instructions,
            "duration_minutes": self.duration_minutes, "max_chars": self.max_chars, "presenters": list(self.presenters), "theme": self.theme,
        }  # fmt: skip

    @classmethod
    def from_json(cls, data: dict | None) -> "ScriptConfig | None":
        if not data:
            return None
        return cls(
            data.get("profile_id"), data.get("profile_name"), data.get("profile_instructions"),
            data.get("duration_minutes"), data.get("max_chars"), tuple(data.get("presenters") or ()), data.get("theme"),
        )  # fmt: skip

    def resolve_speaker(self, raw: object) -> str | None:
        """Nome do apresentador a partir do que o roteirista escreveu (ignora maiúsculas e acentos soltos)."""
        if not self.is_dialogue:
            return None
        key = str(raw or "").strip().lower()
        for name in self.presenters:
            if key == name.lower() or key.startswith(name.lower()) or name.lower().startswith(key) and key:
                return name
        return None


