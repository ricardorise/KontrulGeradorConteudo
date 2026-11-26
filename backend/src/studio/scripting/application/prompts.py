from studio.scripting.application.ports import NewsSource
from studio.scripting.domain.config import ScriptConfig
from studio.shared.application.guidance_text import render_guidance


def _config_block(config: ScriptConfig | None) -> str:
    if config is None or config.is_empty:
        return ""
    parts = []
    if config.profile_name:
        parts.append(f"PERFIL DO ROTEIRISTA — {config.profile_name}:\n{config.profile_instructions}")
    if config.max_chars:
        parts.append(
            f"TEMPO DO VÍDEO — {config.duration_minutes} minutos: a soma de TODOS os parágrafos (só o texto falado"
            f"{', sem os nomes' if config.is_dialogue else ''}) deve ter NO MÁXIMO {config.max_chars} caracteres, "
            f"contando espaços. Mire entre {int(config.max_chars * 0.85)} e {config.max_chars}; nunca passe do limite. "
            "Ajuste a quantidade de parágrafos a esse tamanho (parágrafos curtos)."
        )
    if config.is_dialogue:
        a, b = config.presenters
        parts.append(
            f"APRESENTADORES — dois: {a} e {b}. Escreva como conversa natural entre eles (um puxa o assunto, o outro "
            f"complementa, comenta e pergunta), com a fala de cada um em parágrafos separados, alternando quando fizer sentido. "
            f'Cada parágrafo é um objeto {{"speaker":"{a}" ou "{b}","text":"fala"}}. Não escreva o nome dentro do texto.'
        )
    elif config.presenters:
        parts.append(f"APRESENTADOR — um só: {config.presenters[0]}. Escreva em primeira pessoa para ele ler sozinho.")
    return "\n\nCONFIGURAÇÃO DO ROTEIRO (definida pelo editor, siga à risca):\n" + "\n\n".join(parts)


def script_prompt(
    news: NewsSource, guidelines: list[str] | None = None, instructions: str | None = None, config: ScriptConfig | None = None
) -> str:
    material = [f"Tema pesquisado: {news.topic}", f"Título: {news.title}", f"Resumo: {news.summary}"]
    if news.details:
        material.append(f"Fatos levantados: {news.details}")
    if news.source_url:
        material.append(f"Fonte: {news.source_url}")
    paragraph_rule = "Entre 6 e 10 parágrafos curtos" if not (config and config.max_chars) else "Parágrafos curtos"
    if config and config.is_dialogue:
        a, b = config.presenters
        example = f'{{"title":"título do vídeo","paragraphs":[{{"speaker":"{a}","text":"fala 1"}},{{"speaker":"{b}","text":"fala 2"}}]}}'
    else:
        example = '{"title":"título do vídeo","paragraphs":["parágrafo 1","parágrafo 2"]}'
    return f"""Escreva o roteiro de narração de um vídeo curto do PapoTech Cast sobre a notícia abaixo, usando APENAS o material recebido (não invente dados, números ou citações).

--- MATERIAL ---
{chr(10).join(material)}
--- FIM DO MATERIAL ---

Estrutura padrão: gancho de abertura, desenvolvimento e fechamento. {paragraph_rule}, escritos para serem falados, em português do Brasil (as orientações do editor abaixo podem mudar tom, tamanho ou ângulo).{_config_block(config)}{render_guidance(guidelines or [], instructions)}

Responda SOMENTE com JSON válido (sem markdown, sem texto antes ou depois):
{example}"""


def shorten_prompt(original: str, total_chars: int, config: ScriptConfig) -> str:
    return (
        f"{original}\n\nATENÇÃO: sua versão anterior ficou com {total_chars} caracteres e o limite é {config.max_chars}. "
        f"Reescreva MAIS CURTA, com no máximo {config.max_chars} caracteres no total, mantendo o formato JSON."
    )


def broll_prompt(
    title: str | None,
    paragraphs: list[str],
    guidelines: list[str] | None = None,
    instructions: str | None = None,
    indexes: list[int] | None = None,
    avoid_video_ids: list[str] | None = None,
) -> str:
    """`indexes` = números originais dos parágrafos quando só alguns são (re)buscados; `avoid_video_ids` = vídeos a não repetir."""
    numbers = indexes if indexes is not None else list(range(len(paragraphs)))
    numbered = "\n".join(f"[{n}] {text}" for n, text in zip(numbers, paragraphs, strict=True))
    extra = ""
    if indexes is not None:
        extra += (
            "\n\nBusque cenas SOMENTE para os parágrafos listados acima (os demais já estão resolvidos). "
            "Mantenha os números entre colchetes como índice do parágrafo."
        )
    if avoid_video_ids:
        links = ", ".join(f"https://youtu.be/{v}" for v in avoid_video_ids[:60])
        extra += f"\n\nNÃO repita estes vídeos (já usados ou recusados pelo editor): {links}"
    return f"""Encontre cenas de B-roll no YouTube para ilustrar cada parágrafo do roteiro abaixo{f' ("{title}")' if title else ''}.

--- ROTEIRO ---
{numbered}
--- FIM DO ROTEIRO ---{render_guidance(guidelines or [], instructions)}{extra}

Você é Lumière, pesquisadora de B-rolls para o PapoTechCast.
Encontre 1 a 2 cenas relevantes por parágrafo. Procure o trecho específico que ilustra a ideia, mesmo que esteja no meio de um vídeo longo. Omita parágrafos sem cenas úteis.

Para cada cena:
- Use somente URLs reais encontradas na busca. Nunca invente vídeos, horários ou evidências.
- Identifique o início relevante NO VÍDEO DE ORIGEM. Esse horário não é o momento de inserção no vídeo final.
- Confirme o trecho com ferramentas disponíveis: inspeção visual, capítulos ou transcrição com timestamps. A transcrição confirma a fala, mas não prova sozinha o que aparece na imagem; descreva apenas o que a evidência permite.
- Retorne start_seconds como inteiro em segundos e o mesmo horário na URL: https://www.youtube.com/watch?v=VIDEO_ID&t=326s. O clique deve abrir diretamente no trecho relevante.
- Não use zero como padrão: start_seconds=0 somente se o conteúdo relevante realmente começar no início.
- Na descrição, explique o recorte sugerido; se puder confirmar o fim, informe o intervalo de origem em MM:SS–MM:SS. Não trate essa descrição como um corte já executado.
- Na justificativa, indique por que a cena serve ao parágrafo e como o horário foi confirmado.
- Priorize resultados com trecho confirmado. Se não houver acesso suficiente para confirmar o instante, use start_seconds=null, URL SEM timestamp e justificativa explícita "timestamp não confirmado". Nunca estime um horário para preencher o campo.
- Preserve o índice original do parágrafo, começando em zero.

Responda SOMENTE com JSON válido, sem Markdown ou comentários:
{{"scenes":[{{"paragraph":0,"url":"https://www.youtube.com/watch?v=VIDEO_ID&t=326s","start_seconds":326,"title":"Título real do vídeo encontrado","description":"Descrição do trecho relevante","justification":"Relação com o parágrafo e evidência do horário"}}]}}
Os valores acima exemplificam o formato; não os reutilize como resultado de busca.

"paragraph" é o número entre colchetes do parágrafo ilustrado."""
