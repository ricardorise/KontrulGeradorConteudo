# Kontrul · Gerador de Conteúdo

Estúdio web para transformar **um tema em vídeo**, conversando com a equipe de agentes do Hermes e renderizando no ComfyUI:

**tema → notícias (Tonton) → roteiro (Jules Verne) → B-roll (Lumière) → cortes no player → vídeo final (ComfyUI + ffmpeg)**

Tudo fica salvo no PostgreSQL (`kontrul-postgres-1`, schema `content_studio`).

## O que ele faz

- **Busca de notícias** por tema, com título, descrição e análise de fontes. Modo **Radar** (escopo, janela de 24 h–7 dias) que cruza Tonton, Youtoba e tendências.
- **Roteiro** de narração gerado a partir da notícia, com instruções pontuais ("mais curto", "tom informal").
- **B-roll** do YouTube ao lado de cada parágrafo.
- **Editor de cortes**: player do YouTube com timeline, intervalo por alças, duplo clique para registrar, vínculo do corte com um **trecho do texto** (âncora) e exportação em CSV/JSON.
- **Envio ao ComfyUI** (workflow "videos do papotechcast"): lista de edição validada, **upload de background, vinheta de abertura, vinheta final e áudio de fundo**, níveis de volume por etapa, acompanhamento, download do MP4 e **Remixar** (refaz só a montagem, sem GPU).
- **Chat com os bots** (Tonton, Jules Verne, Lumière, Baru) que **executa ações na tela** (buscar, gerar roteiro, refazer B-roll, salvar orientação).
- **Orientações**: preferências persistentes aplicadas aos próximos pedidos aos bots.

Guia completo: [docs/funcionalidades.md](docs/funcionalidades.md).

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/funcionalidades.md](docs/funcionalidades.md) | Todos os recursos, passo a passo, regras e limites |
| [docs/arquitetura.md](docs/arquitetura.md) | Hexagonal + DDD, contextos, fluxos, decisões |
| [docs/api.md](docs/api.md) | Rotas HTTP, corpos e códigos de erro |
| [docs/banco-de-dados.md](docs/banco-de-dados.md) | Tabelas, migrações e como criar o banco |
| [docs/integracoes.md](docs/integracoes.md) | Hermes, ComfyUI (workflow, uploads, alinhamento), ffmpeg |
| [docs/operacao.md](docs/operacao.md) | Variáveis, execução local, deploy, testes, problemas comuns |
| [comfyui_patches/](comfyui_patches/papotechcast) | Alinhador de frases tolerante e prompts para o agente do ComfyUI |

## Estrutura

```
backend/    Python · FastAPI · asyncpg — hexagonal + DDD (src/studio, migrations, scripts, tests)
frontend/   React + TypeScript + Vite (features: news, script, chat, render, guidance)
docs/       documentação
prompts/    prompts de apoio aos agentes
comfyui_patches/   correções do nó do ComfyUI (referência) e fixtures reais
docker-compose.yml, .env.example   deploy
```

## Começando

```bash
# banco: as migrações rodam sozinhas ao subir o backend (ou: python -m studio.migrate)
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env             # preencha STUDIO_DATABASE_URL, STUDIO_HERMES_SSH, STUDIO_COMFY_URL
set -a; . ./.env; set +a
.venv/bin/uvicorn studio.bootstrap:create_app --factory --port 8100

cd ../frontend && npm install && npm run dev     # http://localhost:5173
```

O PostgreSQL só existe na rede Docker do servidor, então em desenvolvimento use um túnel SSH — detalhes e deploy com Docker Compose em [docs/operacao.md](docs/operacao.md).

## Testes

```bash
cd backend  && .venv/bin/pytest                  # unitários, adaptadores e ffmpeg real
cd frontend && npm test && npx tsc --noEmit
```

## Segurança

Não versione `.env`. Defina `STUDIO_API_KEY` se a porta for exposta na rede: o Hermes roda com aprovação automática de ferramentas. Veja [docs/operacao.md](docs/operacao.md#limitações-conhecidas).
