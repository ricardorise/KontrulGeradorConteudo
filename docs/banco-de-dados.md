# Banco de dados

PostgreSQL do contêiner `kontrul-postgres-1` (banco `sofia`), em **schema dedicado `content_studio`**. Nenhuma tabela existente do banco é tocada.

## Criar ou atualizar o banco

O "script do banco" são as **migrações SQL** em `backend/migrations/` (aplicadas em ordem alfabética, cada uma numa transação, registradas em `content_studio.schema_migrations`).

**Automático:** o backend aplica o que falta ao subir (`STUDIO_RUN_MIGRATIONS=true`, o padrão).

**Manual / instalação nova / CI:**
```bash
cd backend
STUDIO_DATABASE_URL=postgresql://usuario:senha@host:5432/banco .venv/bin/python -m studio.migrate
```
É idempotente (rodar de novo diz "Banco já está atualizado") e usa um *advisory lock*, então réplicas simultâneas não se atropelam. O usuário do banco precisa poder criar schema e tabelas.

Verificado: aplicar todas as migrações num banco vazio gera as 13 tabelas abaixo, idênticas às de produção.

> Nota: há migrações com o mesmo prefixo numérico (`003_*`, `004_*`, `005_*`) porque foram criadas em paralelo. Elas são independentes e a ordem alfabética as aplica corretamente; use nomes únicos nas próximas.

## Migrações
| Arquivo | O que faz |
|---|---|
| `001_init` | Notícias, roteiros, parágrafos, B-roll, conversas e mensagens |
| `002_guidance_and_actions` | Orientações; instruções por execução; ações do chat (`messages.actions`) |
| `003_lumiere_chat` | Libera a Lumière como bot de chat |
| `003_script_cuts` | Cortes de vídeo por parágrafo |
| `004_news_radar` | Análise do Radar por notícia (`news_items.radar`) |
| `004_paragraph_excerpts` | Trecho do texto ligado a cada corte (FK) |
| `005_radar_contract` | Contexto/contrato da busca Radar (`news_searches.report_context`) |
| `005_renders` | Envios ao ComfyUI |
| `006_render_vignettes` | Vinhetas (`render_assets`) e montagem final |
| `007_render_music` | Áudio de fundo |
| `008_render_background` | Vídeo de background enviado |
| `009_render_volumes` | Volumes, nivelamento, vídeo da fala guardado (remix) |
| `010_asset_loudness` | Nível médio do áudio (detecta faixa muda) |
| `011_music_stage_volumes` | Nível do áudio de fundo por etapa |

## Tabelas (`content_studio`)

```mermaid
erDiagram
    news_searches ||--o{ news_items : tem
    news_items ||--o{ scripts : gera
    scripts ||--o{ script_paragraphs : contém
    script_paragraphs ||--o{ broll_suggestions : "sugestões (Lumière)"
    scripts ||--o{ script_cuts : "cortes do editor"
    script_paragraphs ||--o{ paragraph_excerpts : "trechos de texto"
    paragraph_excerpts ||--o| script_cuts : "âncora (FK única)"
    scripts ||--o{ renders : "envios ao ComfyUI"
    render_assets ||--o{ renders : "abertura/final/trilha/background"
    conversations ||--o{ messages : tem
```

| Tabela | Conteúdo principal |
|---|---|
| `news_searches` | Tema, estado, erro, instruções, `report_context` (contrato do Radar) |
| `news_items` | Título, resumo, `details` (fatos), fonte, data, `radar` (análise) |
| `scripts` | Título, estado do roteiro e do B-roll, erros, instruções |
| `script_paragraphs` | Texto e posição de cada parágrafo |
| `broll_suggestions` | Cenas sugeridas: URL, `video_id`, início, descrição, justificativa |
| `script_cuts` | Cortes do editor: vídeo, início/fim (s), título, `excerpt_id` |
| `paragraph_excerpts` | Trecho (offsets e texto) do parágrafo ligado a um corte; único por corte |
| `render_assets` | Uploads: tipo (`intro/outro/music/background`), arquivo, duração, resolução, áudio, nível dB |
| `renders` | Cada envio: estado, `prompt_id`, lista de edição, saída, volumes por parte, `final_path`, `main_path` |
| `guidelines` | Orientações: escopo, texto, ativa, origem (manual/chat) |
| `conversations`, `messages` | Chat por bot; mensagens com estado e `actions` (jsonb) |
| `schema_migrations` | Migrações aplicadas |

## Arquivos fora do banco
Uploads e vídeos montados ficam em disco, em `STUDIO_MEDIA_DIR` (`assets/`, `renders/`). No deploy, é um volume Docker (`studio-media`). O banco guarda só os caminhos e metadados; **faça backup dos dois**.
