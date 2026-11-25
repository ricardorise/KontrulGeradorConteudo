# Funcionalidades

Guia de tudo o que a tela faz, na ordem em que você usa. A interface tem três áreas: **notícias** (esquerda), **roteiro com B-roll** (centro) e **chat com os bots** (direita), mais o botão **Orientações** no topo.

## 1. Busca de notícias (Tonton)

1. Digite um tema no campo do topo e clique em **Buscar notícias**.
2. O **Tonton** pesquisa e devolve de 5 a 8 notícias, cada uma com **título** e **descrição breve**, mais um texto de apoio (`details`) com os fatos levantados — esse texto é o material que o redator usa depois.
3. A busca é assíncrona: a tela mostra "Tonton buscando…" e atualiza sozinha (costuma levar de 20 a 60 s).
4. **Buscas anteriores**: lista das últimas buscas (a lista se atualiza sozinha, inclusive com buscas feitas pelo chat ou em outra aba).

### Modo Radar
Se o tema contiver a palavra **"radar"**, aparecem as configurações do Radar:
- **Escopo** (padrão `VR/XR`), **janela** (24 h, 72 h ou 7 dias) e **fim da janela em UTC** (opcional; vazio usa o momento da execução).
- O Tonton levanta candidatos, o **Youtoba** traz vídeos com tração no YouTube e o resultado é ranqueado por convergência de fontes independentes e aceleração na janela (política `vrxr-cross-sources-v1`).
- Cada notícia ganha **Ver análise, evidências e fontes**: status (ex.: *Emerging*), velocidade, por que chamou atenção, onde cresce, evidências, possíveis pautas, divergências e fontes com link. Publicações fora da janela são descartadas.
- O que não foi confirmado (ex.: Google Trends bloqueado) é informado como limitação; o app não inventa métricas.

## 2. Roteiro (Jules Verne)

- Clique numa notícia para gerar o roteiro. O **Jules Verne** escreve de 6 a 10 parágrafos curtos para narração, usando **só** o material do Tonton (não inventa dados).
- É **idempotente**: clicar de novo na mesma notícia reabre o roteiro existente. **Gerar novo roteiro** cria outro.
- Ao gerar pelo chat com instruções (ex.: "no máximo 5 parágrafos, tom informal"), as instruções valem para aquele roteiro e ficam registradas.
- A tela **segue o roteiro mais novo da notícia**: se outro for criado (pelo chat, outra aba), ela troca sozinha e avisa "Roteiro atualizado".

## 3. B-roll (Lumière)

- Logo após o roteiro, a **Lumière** busca cenas no YouTube, de 1 a 2 por parágrafo, e cada parágrafo aparece com suas cenas **ao lado**.
- Só entram links reais do YouTube (validados); cenas sem horário confirmado vêm apenas com o link do vídeo.
- **Escolher você mesmo o vídeo.** Em cada parágrafo:
  - **+ Adicionar vídeo**: cole um link do YouTube (aceita `&t=90` para começar num instante). O app busca o título e o vídeo já abre no player para você **recortar**.
  - **Trocar vídeo** (em qualquer cartão): substitui o vídeo da sugestão pelo link que você colar, mantendo o lugar, e abre o player para recortar. Cortes já feitos no vídeo antigo continuam válidos.
  - **Remover**: tira o vídeo do parágrafo.
  Os vídeos escolhidos por você ganham o selo **escolhido por você** e **nunca são apagados** por uma nova busca.
- **Rebuscar sem perder o que está bom** (também aceita instruções pelo chat, ex.: "prefira reviews"):
  - **↻ Rebuscar este** (em cada parágrafo): busca de novo só aquele parágrafo.
  - **Escolher parágrafos para rebuscar**: marque vários, depois **Rebuscar selecionados (N)** (há **Marcar todos**).
  - **Rebuscar todos**: refaz o B-roll de todos os parágrafos.
  A busca **não apaga nada antes**: só troca as sugestões automáticas de um parágrafo quando a Lumière traz cenas novas para ele (se não trouxer, as atuais ficam). Ela recebe a lista dos vídeos já usados para não repetir.
- Limitação conhecida: o YouTube pode bloquear o IP do servidor para ler transcrições; nesse caso as cenas vêm sem horário ou o B-roll fica como falho e pode ser refeito.

## 4. Cortes: player, timeline e trecho do texto

Clique na miniatura de um vídeo do B-roll para abrir o **player do YouTube com a timeline**:

| Ação | Como |
|---|---|
| Mover o vídeo | Clique ou arraste na barra (a linha vermelha é a posição atual) |
| Ajustar o intervalo | Arraste as duas alças da faixa azul; setas do teclado ajustam 0,5 s (Shift = 5 s) |
| Usar a posição atual | Botões **[ início = agora** e **fim = agora ]** |
| Ver o trecho | **▶ Prévia** toca só o intervalo escolhido |
| Registrar o corte | **Duplo clique na faixa azul** ou **+ Adicionar corte** |

Regras: mínimo de 0,5 s, precisão de 0,1 s, sem corte duplicado.

### Vínculo com o texto (âncora)
- Antes de registrar, **selecione com o mouse um trecho do parágrafo** (destacado em amarelo). O corte é gravado com a URL do YouTube, o intervalo **e** o trecho de texto — esse trecho marca onde o corte entra na narração.
- Cortes diferentes **não podem usar trechos que se sobrepõem** no mesmo parágrafo (trechos lado a lado são aceitos).
- Cortes antigos sem trecho ou com trecho errado: selecione o texto e clique no **✎** do chip do corte para trocar o vínculo sem refazer o intervalo.
- Os cortes aparecem como chips ✂ no parágrafo e na **Lista de cortes**, com **Copiar**, **Baixar CSV** e **Baixar JSON** (URL, intervalo, duração e trecho).

## 5. Enviar para o ComfyUI (gerar o vídeo)

Botão **Enviar para o ComfyUI (gerar vídeo)** no fim da Lista de cortes. O diálogo mostra o que será enviado e bloqueia o envio com explicações quando algo impede.

### Lista de edição
Cada corte vira uma linha no formato do workflow:
`https://www.youtube.com/watch?v=ID#t=ini,fim | frase:TEXTO | duração`

O envio é bloqueado quando um corte:
- **não tem trecho de texto** (o ComfyUI posiciona o B-roll por frase do roteiro);
- tem trecho com **número ou símbolo** (`128 GB`, `349`, `%`…): na voz isso é falado por extenso e o alinhamento não acha a frase — escolha um trecho só com palavras;
- tem trecho que aparece **mais de uma vez** no roteiro;
- tem o caractere `|` no trecho.

### Mídias e níveis de áudio
Tudo é enviado por upload na própria tela (as escolhas ficam lembradas):

| Bloco | O que é | Detalhes |
|---|---|---|
| **Vídeo de background** | Fundo em loop sob a fala | Upload (até 2 GB) ou caminho já existente no servidor. Só sobe ao ComfyUI se ele ainda não tiver o mesmo arquivo. |
| **Vinheta de abertura** | Toca inteira antes da fala | A fala só começa depois dela. Até 10 min. |
| **Vinheta final** | Entra depois do fim da fala | Até 10 min. |
| **Áudio de fundo** | Uma única trilha (MP3, WAV, M4A, AAC, OGG, OPUS, FLAC) | Repete em loop, com fade-out de 2 s no fim. |

- **Áudio de fundo — três níveis**: *na abertura*, *na fala* e *no final*, com transição suave (≈0,6 s). Sem vinhetas, só existe o nível da fala (a trilha é mixada dentro do ComfyUI).
- **Som original das vinhetas**: volume de 0 a 150 % (recolhido em "Som original da vinheta") e **Nivelar o volume das vinhetas com a fala** (padrão ligado). O app detecta arquivos com faixa de áudio muda e avisa.
- **Volume do áudio do background**: 0 a 150 % (padrão 0 = sem som), enviado ao ComfyUI como `volume_fundo`.

### Acompanhamento e resultado
- Estados: *na fila* → *renderizando* → (se há vinhetas/trilha de montagem) *montando o vídeo final* → *pronto*. Você também vê o progresso no próprio ComfyUI.
- Ao terminar aparecem o **player** e **Baixar MP4**. O histórico de envios do roteiro fica salvo.
- Se o app reiniciar no meio, o acompanhamento é retomado.

### Remixar
**Remixar com estes volumes e vinhetas** refaz **só a montagem final** (vinhetas, níveis, trilha) reaproveitando o vídeo da fala que o ComfyUI já gerou: leva segundos e não usa GPU nem ElevenLabs. O volume do background não muda no remix (exige novo envio). Se a trilha foi embutida pelo ComfyUI (envio sem vinhetas), ela não pode ser trocada.

## 6. Publicação no YouTube

Com o vídeo pronto (diálogo do ComfyUI), o botão **Preparar publicação no YouTube** abre a página de resumo no centro da tela (o chat continua ao lado).

1. **Jules Verne** escreve a melhor descrição a partir do roteiro; **Youtoba** cria o melhor título (com 3 alternativas e a justificativa) e as tags.
2. A página mostra o **resumo completo**: título (contador /100), descrição, tags, **links que irão na descrição** (fontes da notícia/Radar e os vídeos usados nas cenas, montados pelo app, nunca inventados), visibilidade e o **texto final** exatamente como irá ao YouTube (limite de 5000 caracteres).
3. **Alterações**: edite os campos e **Salvar edições**; ou peça uma revisão ("Revisar", escolhendo título/descrição/tags/tudo); ou **peça pelo chat** (ex.: "deixe o título mais curto", "descrição mais informal", "troque as tags", "deixe como não listado"). A mesma página atualiza sozinha.
4. **Publicar no YouTube** pede confirmação e envia o MP4 ao canal. Só existe pelo botão: o chat nunca publica.
5. Visibilidade: **privado** (padrão) ou **não listado**. Tornar público é feito no YouTube Studio após conferir o vídeo (política do Hermes).

> **Quem publica:** o Youtoba tem acesso **somente leitura** ao YouTube, então a publicação é feita pelo agente **Sniper** (ferramenta `youtube_publish`). É configurável com `STUDIO_PUBLISHER_BOT`.

## 7. Chat com os bots

O painel da direita tem abas para **Tonton**, **Jules Verne**, **Lumière** e **Baru** (supervisor). As conversas ficam salvas e voltam ao abrir a aba.

Além de conversar, o chat **executa ações na tela**. Quando o pedido corresponde a uma tarefa, o bot responde e o app executa:

| Ação | Exemplo de pedido |
|---|---|
| Buscar notícias | "busque notícias sobre Apple Vision Pro, só das últimas semanas" |
| Gerar roteiro | "gere o roteiro da notícia 2 com no máximo 5 parágrafos" |
| Refazer B-roll | "refaça o B-roll com cenas de review" |
| Salvar orientação | "a partir de agora, roteiros em tom informal" |
| Editar publicação (página aberta) | "título mais curto", "deixe como não listado" |
| Revisar publicação | "reescreva a descrição em tom informal", "gere outras tags" |

Um chip verde/vermelho mostra o que foi executado, e a tela segue o resultado. O bot enxerga o que está na tela (lista de notícias e roteiro aberto), por isso "a notícia 3" funciona. Se for só conversa, ele responde sem executar nada.

## 8. Orientações (o app "aprende")

Botão **Orientações** no topo. São preferências **persistentes** aplicadas automaticamente aos prompts seguintes do Tonton, Jules Verne e Lumière, conforme o escopo (`notícias`, `roteiro`, `B-roll`, `tudo`):
- Criadas ali ou **pedindo no chat** ("sempre…", "a partir de agora…", "nunca…").
- Cada uma pode ser ligada/desligada ou apagada; no máximo 30 ativas, 300 caracteres cada.
- Não é treino de modelo: é memória de preferências injetada nos prompts. Roteiros já gerados não mudam.

## 9. Atualização automática

A tela nunca fica parada: busca, roteiro e conversa continuam sendo consultados devagar mesmo depois de prontos, pausam com a aba oculta e atualizam na hora ao voltar o foco.
