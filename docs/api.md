# API HTTP

Base: `/api`. Documentação interativa gerada pelo FastAPI em `/docs` (Swagger) e `/openapi.json` quando o backend está no ar.

- **Autenticação:** se `STUDIO_API_KEY` estiver definida, todas as rotas `/api` exigem o header `X-API-Key`. (No deploy, o nginx injeta o header; o navegador nunca vê a chave.)
- **Erros:** `{"detail": "mensagem"}` — `404` não encontrado, `409` conflito, `422` validação/regra de negócio, `401` chave inválida.
- **Trabalho assíncrono:** rotas que iniciam algo demorado respondem `202` com o registro em `running`; consulte-o até o estado final (`done` ou `failed`). Estados: `pending | running | done | failed`.
- `GET /health` (fora de `/api`) responde `{"status":"ok"}`.

## Notícias
| Método e rota | Descrição |
|---|---|
| `POST /news-searches` | Inicia busca. Corpo: `{topic, instructions?, radar_scope?, window_hours?, window_end?}` (parâmetros do Radar só valem quando o tema contém "radar") |
| `GET /news-searches?limit=` | Buscas recentes (com itens) |
| `GET /news-searches/{id}` | Busca com `items[]`: `title, summary, details, source_url, published_at, radar{…}` |

## Roteiro e B-roll
| Método e rota | Descrição |
|---|---|
| `POST /news-items/{id}/script[?force=true]` | Gera o roteiro (idempotente). Corpo opcional `{instructions?, config?: {profile_id, duration_minutes (5/8/12/20), presenters (0–2 nomes)}}` gera um novo |
| `GET /scripts?limit=` | Histórico de roteiros (assunto, busca de origem, perfil/tempo/apresentadores, vídeos prontos, estado da publicação) |
| `GET /script-options` | Perfis (básicos + cadastrados) e tempos (`minutes`, `max_chars`) |
| `POST /script-profiles` | Cadastra perfil: `{name, instructions, description?}` (`409` se o nome já existe) |
| `DELETE /script-profiles/{id}` | Apaga perfil cadastrado (os básicos não podem) |
| `GET /news-items/{id}/script` | Roteiro mais recente da notícia (ou `null`); não cria nada |
| `GET /scripts/{id}` | Roteiro: `status, broll_status, paragraphs[{text, broll[{video_url, source: lumiere|manual, …}]}], cuts[]` |
| `POST /scripts/{id}/broll` | Rebusca o B-roll. Corpo opcional `{instructions?, paragraph_ids?[]}`; sem `paragraph_ids` refaz todos, com eles só esses. Não apaga o que já existe nem os vídeos escolhidos pelo editor |
| `POST /scripts/{id}/paragraphs/{paragraph_id}/broll` | Insere um vídeo escolhido pelo editor: `{video_url}` (link do YouTube; o título é buscado no oEmbed). `409` se já está no parágrafo, `422` se o link é inválido |
| `PUT /scripts/{id}/broll/{broll_id}` | Troca o vídeo de uma sugestão por outro link (`{video_url}`), mantendo id e posição; passa a `source=manual` |
| `DELETE /scripts/{id}/broll/{broll_id}` | Remove o vídeo do parágrafo |

## Cortes
| Método e rota | Descrição |
|---|---|
| `POST /scripts/{id}/cuts` | Corpo: `{paragraph_id, video_url, start_seconds, end_seconds, video_title?, text_start?, text_end?}`. `text_*` são offsets de caracteres do parágrafo (trecho-âncora). `409` se o trecho sobrepõe outro corte do parágrafo |
| `PATCH /scripts/{id}/cuts/{cut_id}/excerpt` | Troca o trecho de texto do corte (`{text_start, text_end}`; corpo vazio remove) |
| `DELETE /scripts/{id}/cuts/{cut_id}` | Remove o corte (e seu trecho) |

## Envio ao ComfyUI
| Método e rota | Descrição |
|---|---|
| `GET /scripts/{id}/render-preview[?background=]` | O que seria enviado: `background, roteiro_chars, edit_list, lines[], problems[], can_send, music_volume, background_volume_supported` |
| `POST /scripts/{id}/renders` | Envia. Corpo: `{narration? (provedor, voz_elevenlabs, modelo_elevenlabs, velocidade 0,7–1,2, estabilidade/similaridade/estilo 0–1, idioma), background?, background_asset_id?, intro_asset_id?, outro_asset_id?, music_asset_id?, music_volume?, music_intro_volume?, music_outro_volume?, intro_volume?, outro_volume?, background_volume?, normalize_vignettes?}`. `422` lista os problemas que impedem o envio |
| `GET /scripts/{id}/renders?limit=` | Envios do roteiro (mais recentes primeiro) |
| `GET /renders/{id}` | Estado: `status, stage (comfyui/composing/done), queued, error, has_video, can_remix, music_baked, …` |
| `POST /renders/{id}/remix` | Refaz só a montagem final. Corpo: `{intro_asset_id?, outro_asset_id?, music_asset_id?, music_volume?, music_intro_volume?, music_outro_volume?, intro_volume?, outro_volume?, normalize_vignettes?}` |
| `POST /renders/{id}/publication` | Prepara a publicação (202): Jules Verne escreve a descrição, Youtoba título/tags. Idempotente; corpo opcional `{force}` cria novo rascunho |
| `GET /renders/{id}/publication` | Última publicação do vídeo (ou `null`) |
| `GET /publications/{id}` | Resumo: `status (drafting/ready/publishing/published/failed), title, title_alternatives, description, tags, links, full_description, privacy, problems, can_publish, video_url, error, error_stage` |
| `PATCH /publications/{id}` | Edição manual atômica: `{title?, description?, tags?, links?, privacy? (private/unlisted), notify_subscribers?}` |
| `POST /publications/{id}/revise` | `{target: title/description/tags/all, instructions}` (202) |
| `POST /publications/{id}/regenerate` | Gera tudo de novo (202) |
| `POST /publications/{id}/publish` | Envia ao YouTube (202). Exige `{confirm: true}`; sem isso, `422` |
| `GET /renders/{id}/video[?download=true]` | O MP4 (arquivo local com suporte a `Range`, ou repasse do ComfyUI) |

Níveis: trilha `0–1`; volumes de vinhetas e background `0–1,5`.

## Vinhetas, background e trilha (uploads)
| Método e rota | Descrição |
|---|---|
| `POST /render-assets` | `multipart/form-data`: `kind` (`intro`, `outro`, `background`, `music`) e `file`. Valida formato, duração e áudio; mede o nível do áudio |
| `GET /render-assets[?kind=]` | Lista (inclui `duration, width, height, has_audio, audio_silent, mean_volume_db`) |
| `DELETE /render-assets/{id}` | Apaga o arquivo e o registro |

## Chat
| Método e rota | Descrição |
|---|---|
| `POST /conversations` | `{bot}` — `tonton`, `julesverne`, `lumiere` ou `baru` |
| `GET /conversations?bot=&limit=` | Conversas recentes |
| `GET /conversations/{id}` | Conversa com mensagens e `actions[]` executadas |
| `POST /conversations/{id}/messages` | `{content, context:{search_id?, script_id?}}`; responde `202` e a resposta chega por polling. `409` se ainda há resposta pendente |

## Orientações
| Método e rota | Descrição |
|---|---|
| `GET /guidelines` | Todas |
| `POST /guidelines` | `{scope: news|script|broll|all, text}` (duplicadas são reaproveitadas; máx. 30 ativas) |
| `PATCH /guidelines/{id}` | `{active}` |
| `DELETE /guidelines/{id}` | Apaga |
