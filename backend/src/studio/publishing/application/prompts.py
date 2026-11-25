from studio.publishing.application.ports import PublicationMaterial
from studio.publishing.domain.publication import Publication, clean_text

CHANNEL = "PapoTech Cast (canal de tecnologia: IA, VR/XR, games, hardware e cultura digital)"


def _context(m: PublicationMaterial) -> str:
    parts = [f"Tema pesquisado: {m.topic}", f"Notícia: {m.news_title}", f"Resumo: {m.news_summary}"]
    if m.news_details:
        parts.append(f"Fatos levantados: {m.news_details[:1500]}")
    parts.append(f"Título do roteiro: {m.script_title or m.news_title}")
    parts.append("Roteiro (narração do vídeo):\n" + "\n\n".join(m.paragraphs)[:6000])
    return "\n".join(parts)


def description_prompt(m: PublicationMaterial, guidelines: list[str] | None = None, instructions: str | None = None) -> str:
    extra = ""
    if guidelines:
        extra += "\n\nOrientações permanentes do editor (siga-as):\n" + "\n".join(f"- {g}" for g in guidelines)
    if instructions:
        extra += f"\n\nPedido do editor para esta descrição (tem prioridade):\n{instructions.strip()}"
    return f"""Escreva a DESCRIÇÃO do vídeo para o YouTube do canal {CHANNEL}.

--- MATERIAL ---
{_context(m)}
--- FIM DO MATERIAL ---{extra}

Regras:
- Primeira linha: um gancho de até 150 caracteres (é o que aparece na busca e no celular).
- Depois, 2 a 4 parágrafos curtos que resumem o vídeo, com as informações mais atrativas e verificáveis do material. Não invente fatos, números ou citações.
- Pode terminar com um convite curto para comentar e se inscrever.
- O roteiro foi escrito para ser FALADO (números, siglas e datas por extenso): na descrição escreva no formato normal de leitura, com algarismos e símbolos (5,49%, US$ 1.059, 19 de novembro, Quest 3S).
- NÃO inclua links, fontes, hashtags nem marcações de tempo: a aplicação acrescenta os links depois.
- No máximo 2500 caracteres, em português do Brasil, sem os caracteres < e >.

Responda SOMENTE com JSON válido (sem markdown):
{{"description":"texto da descrição"}}"""


def title_prompt(m: PublicationMaterial, description: str, instructions: str | None = None, only: str = "all") -> str:
    extra = f"\n\nPedido do editor (tem prioridade):\n{instructions.strip()}" if instructions else ""
    scope = {
        "title": "Altere SOMENTE o título (e as alternativas); devolva as tags atuais sem mudanças.",
        "tags": "Altere SOMENTE as tags; devolva o título atual e as alternativas sem mudanças.",
    }.get(only, "Gere título, alternativas e tags.")
    return f"""Você vai definir o TÍTULO e as TAGS do vídeo no YouTube do canal {CHANNEL}.

Use suas ferramentas de leitura do YouTube Data API (no máximo 3 consultas) para conhecer o canal PapoTech Cast (ID UCq86_sw4NzNUDQ0j_FZRr8g): títulos dos vídeos de melhor desempenho e o estilo que funciona. Não invente métricas.

--- MATERIAL ---
{_context(m)}

Descrição já escrita pelo Jules Verne:
{description}
--- FIM DO MATERIAL ---{extra}

{scope}
Escreva números e siglas em formato normal (algarismos), não por extenso, mesmo que o roteiro os traga por extenso.
Critérios do título: fiel ao conteúdo (sem clickbait enganoso), gancho claro, palavras-chave no começo, idealmente até 70 caracteres e NUNCA mais de 100, sem os caracteres < e >.
Dê 3 alternativas diferentes do título principal. Tags: 8 a 15, sem "#", de busca real (marca, produto, tema).

Responda SOMENTE com JSON válido (sem markdown):
{{"title":"melhor título","alternatives":["alternativa 1","alternativa 2","alternativa 3"],"tags":["tag"],"rationale":"em 1 frase, por que este título"}}"""


def description_revision_prompt(m: PublicationMaterial, p: Publication, instructions: str) -> str:
    return f"""Revise a DESCRIÇÃO do vídeo no YouTube do canal {CHANNEL} conforme o pedido do editor.

Pedido do editor (tem prioridade): {instructions.strip()}

Descrição atual:
{p.description}

Título atual: {p.title}

Material de apoio (não invente nada fora dele):
{_context(m)}

Escreva números e datas em formato normal (algarismos e símbolos), não por extenso. Mantenha o que não foi pedido para mudar. Sem links, fontes nem hashtags (a aplicação os acrescenta), até 2500 caracteres, sem os caracteres < e >.
Responda SOMENTE com JSON válido: {{"description":"descrição revisada"}}"""
