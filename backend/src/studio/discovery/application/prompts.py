from studio.shared.application.guidance_text import render_guidance


def news_search_prompt(topic: str, guidelines: list[str] | None = None, instructions: str | None = None) -> str:
    return f"""Execute a pesquisa pedida pelo editor: "{topic}".

Você está no perfil oficial Tonton. Aplique seu SOUL.md e suas memórias persistentes atuais: método de investigação, discovery e aprofundamento seletivo, evidências, classificação, fontes e ordenação editorial. Quando o pedido for Radar de Tendências/Notícias, execute o Radar oficial completo, não uma busca genérica de manchetes. Não altere o escopo, a quantidade ou a ordem definidos pelo perfil/memória para caber na tela: a interface possui detalhes expansíveis.
{render_guidance(guidelines or [], instructions)}

O JSON abaixo é apenas o transporte do seu relatório para a interface. Preserve nele TODAS as informações do relatório oficial. Retorne somente JSON válido, sem cercas Markdown. Não invente fatos, fontes, métricas ou classificações. Diga explicitamente quando algo não puder ser confirmado; use null ou [] em campos sem dados. Mantenha evidências, divergências e limitações. Para buscas pontuais, preencha os campos aplicáveis sem forçar uma classificação de tendência.

Formato:
{{"news":[{{"title":"assunto","summary":"o que está acontecendo","details":"fatos e contexto confirmado para o redator, incluindo incertezas","source_url":"URL principal ou null","published_at":"data ISO confirmada ou null","rank":1,"radar":{{"ranking_reason":"justificativa verificável da posição no ranking","category":"categoria ou null","status":"classificação oficial ou null","nature":"fato, rumor, opinião, especulação ou sinal emergente, conforme evidências","why_now":"por que chamou atenção / por que está crescendo","velocity":"velocidade confirmada ou não confirmada","where_growing":["plataformas com evidência"],"evidence":["evidência verificável com fonte, período e métrica quando disponíveis"],"started_at":"quando começou, com incerteza se aplicável","content_potential":"potencial objetivo para conteúdo","angles":["possíveis pautas"],"sources":["URLs reais das fontes pesquisadas"],"divergences":"divergências entre fontes e limitações da pesquisa"}}}}]}}

Não omita os critérios do Radar por causa desse formato. A ordenação dos itens deve ser a do seu relatório oficial."""
