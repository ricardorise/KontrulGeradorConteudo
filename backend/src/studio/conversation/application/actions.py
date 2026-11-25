import json
import logging
import re
from typing import Any

from studio.conversation.application.ports import ScreenContext, ScreenSnapshot, StudioGateway
from studio.conversation.domain.conversation import ActionOutcome
from studio.shared.domain.errors import DomainError
from studio.shared.domain.guidance import GuidelineScope
from studio.shared.domain.status import JobStatus

log = logging.getLogger(__name__)

MAX_ACTIONS_PER_REPLY = 3
_ACTION_BLOCK = re.compile(r"<acao>\s*(.*?)\s*</acao>", re.DOTALL | re.IGNORECASE)

PROTOCOL = """[SISTEMA — você está conversando pela tela do Gerador de Conteúdo, que EXECUTA ações]
Quando o pedido do usuário corresponder a uma ação abaixo, NÃO a faça você mesmo (não pesquise notícias, não escreva o roteiro completo, não busque vídeos): responda com uma frase curta confirmando e termine com o bloco da ação. O sistema executa e mostra o resultado na tela. Um bloco por ação, no formato <acao>{JSON}</acao>.

Ações:
- {"action":"search_news","topic":"tema","instructions":"opcional: como o usuário quer esta busca (foco, fontes, período...)"}
- {"action":"generate_script","news_number":N,"instructions":"opcional: tom, tamanho, ângulo, público..."}  (N = número da notícia na lista da tela)
- {"action":"rebuild_broll","instructions":"opcional: que tipo de cena o usuário quer"}  (refaz o B-roll do roteiro aberto)
- {"action":"save_guideline","scope":"news|script|broll|all","text":"regra curta e clara"}

Para pedidos de Radar de Tendências/Notícias ao Tonton, emita search_news preservando o nome do Radar, o escopo e TODAS as instruções do usuário; o executor aplicará o perfil e a memória oficiais do Tonton. Não substitua o Radar por uma lista genérica nem invente parâmetros de pesquisa.

Use save_guideline quando o usuário expressar uma preferência DURÁVEL ("sempre", "a partir de agora", "nunca", "prefiro", "gosto de"): reescreva-a como uma instrução curta no imperativo e escolha o escopo (news = busca de notícias, script = roteiro, broll = cenas de vídeo, all = tudo). Pedidos pontuais ("faça este mais curto") vão em "instructions", não em save_guideline. Pode combinar, p.ex. gerar o roteiro E salvar a preferência.
Se for só conversa, dúvida ou opinião, responda normalmente, sem bloco. Nunca invente números de notícia que não estejam na lista da tela."""


def render_snapshot(snapshot: ScreenSnapshot) -> str:
    lines = ["Estado atual da tela:"]
    if snapshot.news_titles:
        lines.append(f"Notícias listadas (busca: {snapshot.search_topic}):")
        lines += [f"  {i}. {title}" for i, title in enumerate(snapshot.news_titles, 1)]
    else:
        lines.append("Nenhuma lista de notícias aberta.")
    if snapshot.script_paragraphs:
        lines.append(f"Roteiro aberto: {snapshot.script_title or 'sem título'}")
        lines += [f"  [{i}] {text[:160]}" for i, text in enumerate(snapshot.script_paragraphs, 1)]
    else:
        lines.append("Nenhum roteiro aberto.")
    return "\n".join(lines)


def parse_actions(reply: str) -> tuple[str, list[dict[str, Any]]]:
    """Separa o texto de conversa dos blocos <acao>; blocos inválidos são ignorados."""
    actions: list[dict[str, Any]] = []
    for raw in _ACTION_BLOCK.findall(reply):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("bloco de ação inválido ignorado: %.80s", raw)
            continue
        if isinstance(data, dict) and isinstance(data.get("action"), str):
            actions.append(data)
    text = _ACTION_BLOCK.sub("", reply).strip()
    return text, actions[:MAX_ACTIONS_PER_REPLY]


def _text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    value = str(value).strip() if value is not None else ""
    return value or None


class ActionExecutor:
    def __init__(self, studio: StudioGateway):
        self._studio = studio

    async def run(self, requested: list[dict[str, Any]], ctx: ScreenContext) -> list[ActionOutcome]:
        outcomes: list[ActionOutcome] = []
        for data in requested:
            try:
                outcomes.append(await self._run_one(data, ctx))
            except DomainError as exc:
                outcomes.append(ActionOutcome(str(data.get("action")), JobStatus.FAILED, "Ação não executada", str(exc)))
            except Exception:
                log.exception("falha executando ação %s", data.get("action"))
                outcomes.append(
                    ActionOutcome(str(data.get("action")), JobStatus.FAILED, "Ação não executada", "Erro interno.")
                )
        return outcomes

    async def _run_one(self, data: dict[str, Any], ctx: ScreenContext) -> ActionOutcome:
        kind, instructions = data["action"], _text(data, "instructions")
        if kind == "search_news":
            topic = _text(data, "topic")
            return await self._studio.search_news(topic, instructions) if topic else _invalid(kind, "tema ausente")
        if kind == "generate_script":
            try:
                number = int(data.get("news_number"))
            except (TypeError, ValueError):
                return _invalid(kind, "número da notícia ausente")
            return await self._studio.generate_script(ctx, number, instructions)
        if kind == "rebuild_broll":
            return await self._studio.rebuild_broll(ctx, instructions)
        if kind == "save_guideline":
            text = _text(data, "text")
            try:
                scope = GuidelineScope(str(data.get("scope", "all")).lower())
            except ValueError:
                return _invalid(kind, "escopo inválido")
            return await self._studio.remember(scope, text) if text else _invalid(kind, "texto ausente")
        return _invalid(kind, "ação desconhecida")


def _invalid(kind: str, reason: str) -> ActionOutcome:
    return ActionOutcome(kind, JobStatus.FAILED, "Ação não executada", f"Pedido do bot inválido: {reason}.")
