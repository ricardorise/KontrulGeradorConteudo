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
| `POST /news-items/{id}/script[?force=true]` | Gera o roteiro (idempotente). Corpo opcional `{instructions}` gera um novo |
| `GET /news-items/{id}/script` | Roteiro mais recente da notícia (ou `null`); não cria nada |
| `GET /scripts/{id}` | Roteiro: `status, broll_status, paragraphs[{text, broll[]}], cuts[]` |
| `POST /scripts/{id}/broll` | Refaz só o B-roll. Corpo opcional `{instructions}` |

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
| `POST /scripts/{id}/renders` | Envia. Corpo: `{background?, background_asset_id?, intro_asset_id?, outro_asset_id?, music_asset_id?, music_volume?, music_intro_volume?, music_outro_volume?, intro_volume?, outro_volume?, background_volume?, normalize_vignettes?}`. `422` lista os problemas que impedem o envio |
| `GET /scripts/{id}/renders?limit=` | Envios do roteiro (mais recentes primeiro) |
| `GET /renders/{id}` | Estado: `status, stage (comfyui/composing/done), queued, error, has_video, can_remix, music_baked, …` |
| `POST /renders/{id}/remix` | Refaz só a montagem final. Corpo: `{intro_asset_id?, outro_asset_id?, music_asset_id?, music_volume?, music_intro_volume?, music_outro_volume?, intro_volume?, outro_volume?, normalize_vignettes?}` |
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
