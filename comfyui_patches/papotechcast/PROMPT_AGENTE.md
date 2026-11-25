# Tarefa: tornar tolerante o alinhamento de frases do nó PapoRender (ComfyUI / PapoTechCast)

## Contexto
O workflow "videos do papotechcast" posiciona cada B-roll por **frase do roteiro**
(linha da lista de edição: `URL#t=ini,fim | frase:TEXTO | duração`).
A resolução da frase para um horário fica em
`/mnt/build/projects/ComfyUI/custom_nodes/papotechcast/phrase_alignment.py` (função `resolve`),
chamada de `pipeline.py:245`. Hoje ela compara **sequências exatas de tokens** entre a frase e a
transcrição do WhisperX (`occurrences(sequence, tokens(frase))`).

## O problema (reproduzido com dados reais)
A transcrição nunca é idêntica ao roteiro, então a execução falha no nó 5 (PapoRender) com:
`WhisperX não identificou uma ocorrência única: <frase>. Revise a frase e o áudio...`

Execução real: `/mnt/build/projects/ComfyUI/output/papotechcast/430f7ef87e34/`
(`roteiro.txt`, `alinhamento-whisperx.json`). Exemplo:

- Roteiro: "o Quest três S, o modelo de entrada da casa, caiu de trezentos e quarenta e nove dólares"
- WhisperX: "O Quest 3, seu modelo de entrada da casa, caiu de 349 dólares"

Diferenças: números viram dígitos, "3S" vira "3", e palavras trocam ("o" → "seu").
As 3 frases dessa execução existem **1× no roteiro e 0× na transcrição**, então todas falham:
1. `o Quest três S, o modelo`
2. `Esse tá saindo por trezentos`
3. `Ou seja, quase o dobro do três`

Escrever o roteiro por extenso NÃO resolve: o ASR reescreve os números como dígitos.

## O que fazer
Substituir a comparação exata por um alinhamento **tolerante**, mantendo a interface de `resolve(assets, narration)`
e o restante do pipeline. Requisitos:

1. **Normalizar os dois lados para a mesma forma falada**: minúsculas, sem acento/pontuação,
   números convertidos para palavras pt-BR (`349` → "trezentos e quarenta e nove"; `3S` → "três s").
2. **Buscar a janela da transcrição mais parecida** com a frase (similaridade de sequência de palavras),
   não exigir igualdade.
3. **Desempate por posição**: a narração segue a ordem do roteiro; usar a posição relativa da frase
   no roteiro para escolher entre trechos parecidos.
4. **Confiança mínima e ambiguidade**: rejeitar abaixo de um limite (referência: 0,70) e quando houver
   2º melhor trecho, em outro ponto, praticamente empatado. A mensagem de erro deve informar o que foi
   ouvido e a similaridade, para revisão. **Nunca estimar horário.**
5. **Preservar regras existentes**: a frase continua precisando ser única no roteiro
   ("ausente ou repetida"); horário vem da primeira palavra reconhecida com `score >= 0.5`;
   o cache do WhisperX (`alinhamento-whisperx.json/.sha256`) segue como está.
6. Gravar `alinhamento-frases.json` na pasta da execução (frase, o que foi ouvido, similaridade, horário)
   para conferência. Não alterar o formato de `brolls-alinhados.json`.
7. Só biblioteca padrão (`rapidfuzz` e `num2words` NÃO estão instalados no env do ComfyUI).

## Implementação de referência (já testada)
Já existe uma versão pronta que atende a tudo acima, com testes e dados reais de fixture:

- `comfyui_patches/papotechcast/phrase_alignment.py` (substitui o arquivo do servidor)
- `comfyui_patches/papotechcast/test_phrase_alignment_fuzzy.py` (10 testes, inclui as 3 frases reais)
- `comfyui_patches/papotechcast/fixtures/` (transcrição e roteiro reais)

(no repositório `/mnt/dados/Projects/KontrulTools/KontrulGeradorConteudo`).
Revise o código criticamente: confira os limiares (`MIN_SCORE`, `AMBIGUITY_MARGIN`, `POSITION_WEIGHT`),
o desempenho em narrações longas (varre janelas de vários tamanhos) e se o conversor de números cobre
os casos que vocês usam. Ajuste o que julgar necessário.

## Procedimento
1. Faça **backup** de `phrase_alignment.py` (ex.: `phrase_alignment.py.bak-AAAAMMDD`).
2. Instale a versão nova em `custom_nodes/papotechcast/` e copie o arquivo de testes.
3. Rode no servidor: `python -m unittest test_phrase_alignment test_pipeline test_phrase_alignment_fuzzy`
   (os 14 testes originais devem continuar passando).
4. Valide com a execução real acima, **sem GPU/ElevenLabs**: chame `resolve` apontando para a pasta
   `430f7ef87e34` (o cache do WhisperX já existe) e confira que as 3 frases retornam horários
   coerentes e que `alinhamento-frases.json` mostra o texto ouvido.
5. Reinicie o ComfyUI (`systemctl restart comfyui.service`; o módulo fica em memória, importado em
   `pipeline.py:245`) **somente com a fila vazia** (`GET /queue`).
6. **Não dispare uma renderização completa** sem confirmar com o responsável: ela usa créditos da
   ElevenLabs e a GPU. A narração igual é reaproveitada do cache.

## Critérios de aceite
- As 3 frases acima são resolvidas na execução `430f7ef87e34`, em ordem crescente de horário.
- Frase inexistente no áudio continua falhando com mensagem clara (o que foi ouvido + similaridade).
- Frase repetida no roteiro continua falhando como "ausente ou repetida".
- Testes originais + novos passam; existe backup e instrução de rollback
  (restaurar o `.bak` e reiniciar o serviço).

## Entregáveis
Relatório curto com: o que mudou, saída dos testes, resultado da validação nas 3 frases,
limiares escolhidos e qualquer risco observado.
