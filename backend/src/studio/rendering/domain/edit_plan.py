import math
import re
from dataclasses import dataclass, field

from studio.rendering.domain.script_view import ScriptForRender


@dataclass(frozen=True)
class EditLine:
    order: int
    paragraph: int
    url: str
    start: int
    end: int
    phrase: str

    @property
    def duration(self) -> int:
        return self.end - self.start

    def render(self) -> str:
        """Formato da lista de edição do workflow: recurso | frase:frase única do roteiro | duração."""
        return f"{self.url}#t={self.start},{self.end} | frase:{self.phrase} | {self.duration}"


@dataclass
class EditPlan:
    roteiro: str
    lines: list[EditLine] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def edit_list(self) -> str:
        return "\n".join(line.render() for line in self.lines)


# O WhisperX alinha o que foi FALADO; dígitos e símbolos viram palavras na voz ("128 GB" → "cento e vinte e oito...").
_UNSPOKEN = re.compile(r"[0-9%$€£&@#+=/\\<>*_~^]")


def _norm(text: str) -> str:
    return " ".join(text.split())


def build_plan(script: ScriptForRender) -> EditPlan:
    """Monta o roteiro e a lista de edição; cada corte precisa de uma frase exata e única do roteiro."""
    plan = EditPlan(roteiro="\n\n".join(script.paragraphs))
    narration = _norm(plan.roteiro)
    if not script.cuts:
        plan.problems.append("Não há cortes na lista. Adicione ao menos um corte antes de enviar.")
        return plan

    ordered = sorted(script.cuts, key=lambda c: (c.paragraph, c.excerpt_start if c.excerpt_start is not None else -1))
    for order, cut in enumerate(ordered, start=1):
        where = f"Corte {order} (parágrafo {cut.paragraph}, {cut.video_id})"
        if not cut.excerpt:
            plan.problems.append(
                f"{where} não tem trecho do texto: o ComfyUI posiciona o B-roll por frase do roteiro. "
                "Remova-o e crie de novo selecionando o trecho no parágrafo."
            )
            continue
        phrase = _norm(cut.excerpt)
        if "|" in phrase:
            plan.problems.append(f"{where}: o trecho contém “|”, que separa os campos da lista. Escolha outro trecho.")
            continue
        if (bad := _UNSPOKEN.search(phrase)):
            plan.problems.append(
                f"{where}: o trecho “{phrase[:60]}” tem número ou símbolo (“{bad.group()}”). Na voz isso é falado por extenso e "
                "o WhisperX não acha a frase. Escolha um trecho só com palavras."
            )
            continue
        found = narration.count(phrase)
        if found != 1:
            plan.problems.append(
                f"{where}: o trecho “{phrase[:60]}” aparece {found}× no roteiro; precisa ser único. "
                "Selecione um trecho mais longo ou diferente."
            )
            continue
        start, end = math.floor(cut.start), math.ceil(cut.end)
        plan.lines.append(
            EditLine(order, cut.paragraph, f"https://www.youtube.com/watch?v={cut.video_id}", start, max(end, start + 1), phrase)
        )
    return plan
